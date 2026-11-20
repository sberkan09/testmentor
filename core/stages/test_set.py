"""Test case set of one cluster (docs/tasarim.md, Test durumu üretimi).

Dependencies: member requirements (ids and texts), their verification methods (the generation
prompt tells the model which members need tests; paket 2 decision), the cluster's retrieved
passage ids and the project card. Context: the set's pinned test cases, which go to the prompt
as fixed and so key the output cache, but do not stale the set when edited.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from core.nodes import (
    PROJECT_CARD_KEY,
    NodeKind,
    NodeRef,
    ProjectCardContent,
    RetrievalContent,
    TestCaseContent,
    TestSetContent,
)
from core.prompts import (
    ContentCard,
    append_tail,
    generation_messages,
    incremental_section,
    merge_section,
    pinned_section,
    repair_section,
)
from core.schemas import MergeDecision, Requirement, case_set_model, incremental_model
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register
from core.stages.calls import CallFailed, CallLog, call, result
from core.stages.test_generation import (
    BASIS_PARAM,
    apply_incremental,
    apply_merge,
    basis_of,
    choose_mode,
    delta,
    filter_covers,
    merge_sources,
    need,
    prune_removed,
    read_basis,
    renumber,
    split_units,
    uncovered,
)

if TYPE_CHECKING:
    from core.graph import ProjectState
    from core.llm import Complete

CARD = NodeRef(kind=NodeKind.PROJECT_CARD, key=PROJECT_CARD_KEY)


def keys(state: ProjectState) -> Iterable[str]:
    """One per cluster, keyed by cluster id."""
    return state.keys_of(NodeKind.CLUSTER)


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """Member requirements in id order, their methods in the same order, the cluster's retrieval,
    then the project card."""
    members = state.members(key)
    return (
        *(NodeRef(kind=NodeKind.REQUIREMENT, key=m) for m in members),
        *(NodeRef(kind=NodeKind.METHOD, key=m) for m in members),
        NodeRef(kind=NodeKind.RETRIEVAL, key=key),
        CARD,
    )


def context(state: ProjectState, key: str) -> Any:
    """Pinned test cases of the set as plain JSON, in case key order."""
    pinned = []
    for r in state.test_cases(key):
        node = state.node(r)
        if node.pinned and node.content is not None:
            pinned.append({"key": r.key, "content": node.content.model_dump(mode="json")})
    return pinned


async def produce(ctx: ProduceContext, complete: Complete) -> ProduceOutcome:
    """See `core.stages.test_generation` for the helpers and docs/tasarim.md (Test durumu
    üretimi) for the rules. Per cluster:
    1. Mode by `choose_mode(..., max_unit_size=settings.max_unit_size)`. Members not in
       `need` get no tests. Pinned cases count as coverage: a requirement they cover needs no
       generated case and causes no repair. With nothing left to cover and a full mode the set
       is produced without a call (only pinned cases).
       Existing cases are read in `TestSetContent.case_keys` order, not key order.
    2. Prompt: `generation_messages` (layers 1–5, byte-identical to paket 1) plus, in this order
       after layer 5: `pinned_section`; for incremental `incremental_section`; for merge
       `merge_section`. Schema: case set / `incremental_model` / `MergeDecision`.
       Full mode on more than `settings.max_unit_size` members: `split_units`, one call per
       part (each part's own layers 5, same tails), concurrently; cases concatenated in part
       order then `renumber`ed.
       Layer 4: `ctx.passages(retrieval passage ids)`; passage ids without `ctx.passages`
       fail the node (no silent "(none)").
       Incremental: `prune_removed` first; when the delta is only removals the call still
       happens (design call count) unless `settings.prune_removals` (D8 arm: no call).
       `settings.regeneration == "full"` (D8 arm) never chooses incremental.
    3. `filter_covers` against `need`; one repair call when `settings.repair` and something is
       uncovered (pinned and generated cases together). The repair prompt is the same in every
       mode: layers 1–5, `pinned_section`, `repair_section(uncovered)`; schema case set (no
       incremental or merge section, so the prompt names one output shape). For a split
       cluster the repair is one call over the uncovered requirements' layer 5 only. Repaired
       cases are filtered and appended with `next_ids`.
    4. Schema error on any call: one retry with `schema_retry_section(error)` appended; a
       second error fails the node (no partial set is written).
    5. Result: `TestSetContent()` with `cases` = the complete unpinned set; produced_by mode
       (`full`, `incremental`, `merge`), model, prompt version, params and
       `params["basis"] = basis_of(...)`. Requirements still uncovered after the repair do not
       fail the node; they are reported in stats (`uncovered`) and show as uncovered matrix
       rows.
    Stats per ref: `mode`, `calls`, `units`, `dropped_ids`, `dropped_cases`, `uncovered`,
    `covered_before_repair`, `pinned_update_attempts`."""
    results, failed, stats = [], {}, {}
    for ref in ctx.refs:
        job = _SetJob(ctx, complete, ref)
        try:
            results.append((ref, await job.run()))
        except _NodeFailed as exc:
            failed[ref] = str(exc)[:500]
        stats[ref] = job.stats()
    return ProduceOutcome(results=tuple(results), failed=failed, stats=stats)


class _NodeFailed(Exception):
    pass


class _SetJob:
    """Production of one test set (see `produce`)."""

    def __init__(self, ctx: ProduceContext, complete: Complete, ref: NodeRef) -> None:
        self.ctx, self.complete, self.ref = ctx, complete, ref
        self.state = ctx.state
        self.settings = ctx.settings
        self.cluster = ref.key
        self.log = CallLog()
        self.mode = "full"
        self.units = 0
        self.dropped_ids = 0
        self.dropped_cases = 0
        self.uncovered: list[str] = []
        self.covered_before_repair: list[str] = []
        self.pinned_update_attempts = 0
        self.pruned = False

        state, cluster = self.state, self.cluster
        self.members = state.members(cluster)
        self.need = need(state, cluster, self.settings.test_method)
        self.pinned: list[TestCaseContent] = []
        self.pinned_ids: set[str] = set()
        self.existing: list[TestCaseContent] = []
        node = state.node(ref)
        order = node.content.case_keys if isinstance(node.content, TestSetContent) else ()
        present = {r.key: r for r in state.test_cases(cluster)}
        keys = [k for k in order if k in present] + sorted(k for k in present if k not in order)
        for k in keys:
            case_node = state.node(present[k])
            if not isinstance(case_node.content, TestCaseContent):
                continue
            if case_node.pinned:
                self.pinned.append(case_node.content)
                self.pinned_ids.add(k.split(":", 1)[1])  # the key decides collisions
            else:
                self.existing.append(case_node.content)
        types, priorities = self.settings.test_types, self.settings.priorities
        self.case_schema = case_set_model(types, priorities)
        self.delta_schema = incremental_model(types, priorities)

    def stats(self) -> dict[str, Any]:
        return {
            **self.log.stats(),
            "mode": self.mode,
            "units": self.units,
            "dropped_ids": self.dropped_ids,
            "dropped_cases": self.dropped_cases,
            "uncovered": self.uncovered,
            "covered_before_repair": self.covered_before_repair,
            "pinned_update_attempts": self.pinned_update_attempts,
            "pruned": self.pruned,
        }

    # Prompt ---------------------------------------------------------------------------------

    def _passages(self) -> list[str]:
        ret = self.state.node(NodeRef(kind=NodeKind.RETRIEVAL, key=self.cluster)).content
        ids = ret.passage_ids if isinstance(ret, RetrievalContent) else ()
        if not ids:
            return []
        if self.ctx.passages is None:
            raise _NodeFailed("retrieval has passage ids but no passage source was given")
        return list(self.ctx.passages(ids))

    def _base(self, reqs: Sequence[str]) -> list[dict[str, str]]:
        """Layers 1–5 for `reqs` (paket 1 `generation_messages`) and the pinned section."""
        state = self.state
        card = state.node(CARD).content
        assert isinstance(card, ProjectCardContent)
        rows = [
            Requirement(
                id=m, text=state.requirement(m).text, language=state.requirement(m).language
            )
            for m in reqs
        ]
        methods = {}
        for m in reqs:
            content = state.node(NodeRef(kind=NodeKind.METHOD, key=m)).content
            if content is not None:
                methods[m] = list(content.methods)  # type: ignore[union-attr]
        msgs = generation_messages(
            ContentCard(card),
            rows,
            methods,
            schema=self.case_schema.model_json_schema(),
            examples=self.settings.examples,
            test_method=self.settings.test_method,
            types=self.settings.test_types,
            priorities=self.settings.priorities,
            passages=self.passages,
        )
        return append_tail(msgs, pinned_section(self.pinned))

    async def _call(self, unit: str, messages, schema) -> Any:
        try:
            return await call(
                self.complete,
                self.log,
                stage=NodeKind.TEST_SET,
                unit=f"{self.cluster}/{unit}",
                messages=messages,
                schema=schema,
                params=self.settings.llm[NodeKind.TEST_SET],
            )
        except CallFailed as exc:
            raise _NodeFailed(f"schema: {exc}") from exc

    def _filter(self, cases: Iterable[Any]) -> list[TestCaseContent]:
        out = filter_covers(cases, self.need)
        self.dropped_ids += out.dropped_ids
        self.dropped_cases += out.dropped_cases
        return list(out.cases)

    # Modes ----------------------------------------------------------------------------------

    async def run(self):
        self.passages = self._passages()
        self.mode = choose_mode(
            self.state,
            self.cluster,
            self.ctx.hint,
            self.ctx.sources,
            max_unit_size=self.settings.max_unit_size,
            allow_incremental=self.settings.regeneration == "incremental",
        )
        if not self.need:
            cases: list[TestCaseContent] = []  # nothing may be covered
        elif self.mode == "full":
            cases = await self._full()
        elif self.mode == "incremental":
            cases = await self._incremental()
        else:
            cases = await self._merge()
        cases = await self._repair(cases)
        basis = basis_of(self.state, self.cluster)
        return result(
            self.state,
            self.ref,
            TestSetContent(),
            mode=self.mode,
            extra_params={BASIS_PARAM: basis.model_dump(mode="json")},
            cases=cases,
        )

    async def _full(self) -> list[TestCaseContent]:
        pinned_cover = {r for c in self.pinned for r in c.covers}
        if not [m for m in self.need if m not in pinned_cover]:
            return []
        size = self.settings.max_unit_size
        units = split_units(self.members, size) if len(self.members) > size else [self.members]
        need = set(self.need)
        units = [u for u in units if need.intersection(u)]
        self.units = len(units)
        replies = await asyncio.gather(
            *(
                self._call(
                    f"full/{i}" if len(units) > 1 else "full", self._base(u), self.case_schema
                )
                for i, u in enumerate(units)
            )
        )
        cases = self._filter(c for reply in replies for c in reply["test_cases"])
        return renumber(cases, self.pinned_ids)

    async def _incremental(self) -> list[TestCaseContent]:
        self.units = 1
        old = read_basis(self.state.node(self.ref))
        assert old is not None  # choose_mode checked it
        d = delta(old, basis_of(self.state, self.cluster))
        # A member that left, or stayed but lost the test method, takes its covers along.
        lost = set(d.removed) | {m for m in self.members if m not in set(self.need)}
        kept, trimmed = prune_removed(self.existing, lost)
        if d.only_removed and self.settings.prune_removals:
            self.pruned = True  # D8: no call; kept cases are the set
            return kept
        touched = set(d.changed) | set(d.removed)
        full = [c for c in kept if c.id in trimmed or touched.intersection(c.covers)]
        summary = [c for c in kept if c not in full]
        section = incremental_section(
            full=full,
            summary=summary,
            added=d.added,
            changed=d.changed,
            removed=d.removed,
            schema=self.delta_schema.model_json_schema(),
        )
        reply = await self._call(
            "incremental", append_tail(self._base(self.members), section), self.delta_schema
        )
        cases, ignored = apply_incremental(
            kept, self._filter(reply["add"]), self._filter(reply["update"]), self.pinned_ids
        )
        self.pinned_update_attempts = ignored
        return cases

    async def _merge(self) -> list[TestCaseContent]:
        self.units = 1
        assert self.ctx.hint is not None
        merged = merge_sources(
            {s: self.ctx.sources[s] for s in self.ctx.hint.sources}, self.pinned_ids
        )
        section = merge_section(merged, schema=MergeDecision.model_json_schema())
        reply = await self._call(
            "merge", append_tail(self._base(self.members), section), MergeDecision
        )
        kept = apply_merge(merged, reply["drop"])
        return self._filter(c.model_dump(mode="json", exclude={"kind"}) for c in kept)

    async def _repair(self, cases: list[TestCaseContent]) -> list[TestCaseContent]:
        missing = uncovered([*self.pinned, *cases], self.need)
        self.covered_before_repair = sorted(set(self.need) - set(missing))
        if missing and self.settings.repair:
            split = len(self.members) > self.settings.max_unit_size
            base = self._base(missing if split else self.members)
            reply = await self._call(
                "repair", append_tail(base, repair_section(missing)), self.case_schema
            )
            new = self._filter(reply["test_cases"])
            taken = self.pinned_ids | {c.id for c in cases}
            cases = cases + renumber(new, taken)
            missing = uncovered([*self.pinned, *cases], self.need)
        self.uncovered = missing
        return cases


SPEC = register(
    StageSpec(
        kind=NodeKind.TEST_SET,
        uses_llm=True,
        keys=keys,
        dependencies=dependencies,
        context=context,
        produce=produce,
        batched=False,
    )
)
