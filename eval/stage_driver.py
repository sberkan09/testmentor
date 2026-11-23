"""Wave driver for measurement (paket 3). Paket 5 replaces it with the real job queue.

Each wave: `analyze(state).ready` → group by stage (a batched stage gets one job with all its
ready nodes, the others one job per node) → run every job concurrently → `settle_many` → mark
the failed nodes failed. Repeats until nothing is ready.

A job that raises (an `LLMError`, an HTTP 400, a bug) fails only its own nodes; the error is kept
in `Driven.errors` and the run goes on, so one bad request does not stop a paid experiment arm.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from core import stages
from core.graph import ProjectState
from core.invalidation import Hint, analyze, mark_failed, settle_many
from core.llm import Complete
from core.nodes import NodeKind, NodeRef, Result, TestCaseContent
from core.settings import StageSettings
from core.stages.base import Embed, PassageSource, ProduceContext, ProduceOutcome, Retrieve


@dataclass
class Driven:
    state: ProjectState
    outcomes: list[ProduceOutcome] = field(default_factory=list)
    errors: dict[NodeRef, str] = field(default_factory=dict)
    """Failed nodes and why (producer failures, raised errors, rejected results)."""
    waves: int = 0

    def stats(self) -> dict[NodeRef, Mapping[str, Any]]:
        return {r: s for o in self.outcomes for r, s in o.stats.items()}


async def drive(
    state: ProjectState,
    complete: Complete,
    *,
    settings: StageSettings,
    skip: Iterable[NodeKind] = (),
    hints: Mapping[NodeRef, Hint] | None = None,
    sources: Mapping[NodeRef, Sequence[TestCaseContent]] | None = None,
    embed: Embed | None = None,
    retrieve: Retrieve | None = None,
    passages: PassageSource | None = None,
    max_waves: int = 50,
) -> Driven:
    """Produce every ready node (kinds in `skip` are left stale) until nothing is ready."""
    skip = frozenset(skip)
    hints = dict(hints or {})
    out = Driven(state)
    for _ in range(max_waves):
        ready = [r for r in analyze(out.state).ready if r.kind not in skip]
        if not ready:
            return out
        out.waves += 1
        jobs: list[tuple[tuple[NodeRef, ...], Any]] = []
        by_kind: dict[NodeKind, list[NodeRef]] = {}
        for r in ready:
            by_kind.setdefault(r.kind, []).append(r)
        for kind, refs in by_kind.items():
            spec = stages.get(kind)
            if spec.produce is None:
                raise RuntimeError(f"stage {kind} has no producer")
            groups = [tuple(refs)] if spec.batched else [(r,) for r in refs]
            for g in groups:
                ctx = ProduceContext(
                    state=out.state,
                    refs=g,
                    settings=settings,
                    hint=hints.get(g[0]) if len(g) == 1 else None,
                    sources=sources or {},
                    embed=embed,
                    retrieve=retrieve,
                    passages=passages,
                )
                jobs.append((g, spec.produce(ctx, complete)))
        done = await asyncio.gather(*(_guard(refs, job) for refs, job in jobs))
        results: list[tuple[NodeRef, Result]] = []
        failed: dict[NodeRef, str] = {}
        for outcome in done:
            out.outcomes.append(outcome)
            results += outcome.results
            failed |= dict(outcome.failed)
        settled = settle_many(out.state, results)
        state = settled.state
        for r in settled.rejected:
            failed[r] = "result rejected by settle (inputs changed during the wave)"
        for r, why in failed.items():
            out.errors[r] = why
            state = mark_failed(state, r)
        out.state = state
    raise RuntimeError(f"drive did not converge in {max_waves} waves")


async def _guard(refs: tuple[NodeRef, ...], job: Any) -> ProduceOutcome:
    try:
        return await job
    except Exception as exc:  # noqa: BLE001 - one job's failure must not stop the others
        why = f"{type(exc).__name__}: {exc}"[:2000]
        return ProduceOutcome(failed={r: why for r in refs})
