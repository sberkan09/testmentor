"""Verification method of one requirement. Cluster edits never stale it."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from core.nodes import PROJECT_CARD_KEY, MethodContent, NodeKind, NodeRef, ProjectCardContent
from core.prompts import ContentCard, classification_messages
from core.schemas import Requirement, method_batch_model
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register
from core.stages.calls import CallFailed, CallLog, call, result

if TYPE_CHECKING:
    from core.graph import ProjectState
    from core.llm import Complete

CARD = NodeRef(kind=NodeKind.PROJECT_CARD, key=PROJECT_CARD_KEY)


def keys(state: ProjectState) -> Iterable[str]:
    """One per requirement, keyed by requirement id."""
    return state.keys_of(NodeKind.REQUIREMENT)


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """The requirement, then the project card."""
    return (NodeRef(kind=NodeKind.REQUIREMENT, key=key), CARD)


async def produce(ctx: ProduceContext, complete: Complete) -> ProduceOutcome:
    """Batched. Stale refs in id order, in batches of `settings.method_batch_size`, one
    `classification_messages` call per batch (schema `method_batch_model` over the card's
    method names). A decision for an id outside the batch is ignored; methods sorted and
    de-duplicated. Ids missing from a reply are retried once in a single call of their own;
    still missing → failed. Schema error: one retry with `schema_retry_section`, then the
    whole batch failed. Batches run concurrently."""
    state, settings = ctx.state, ctx.settings
    refs = sorted(ctx.refs, key=lambda r: r.key)
    card = state.node(CARD).content
    if not isinstance(card, ProjectCardContent) or not card.methods:
        return ProduceOutcome(failed={r: "project card has no methods" for r in refs})
    schema = method_batch_model(tuple(m.name for m in card.methods))
    json_schema = schema.model_json_schema()
    params = settings.llm[NodeKind.METHOD]
    size = settings.method_batch_size
    batches = [refs[i : i + size] for i in range(0, len(refs), size)]

    async def ask(batch: Sequence[NodeRef], unit: str, log: CallLog) -> dict[str, Any]:
        reqs = [
            Requirement(
                id=r.key,
                text=state.requirement(r.key).text,
                language=state.requirement(r.key).language,
            )
            for r in batch
        ]
        out = await call(
            complete,
            log,
            stage=NodeKind.METHOD,
            unit=unit,
            messages=classification_messages(ContentCard(card), reqs, schema=json_schema),
            schema=schema,
            params=params,
        )
        wanted = {r.key for r in batch}
        found: dict[str, Any] = {}
        for d in out["decisions"]:
            if d["requirement_id"] in wanted and d["requirement_id"] not in found:
                found[d["requirement_id"]] = d
        return found

    async def run(i: int, batch: Sequence[NodeRef]):
        log = CallLog()
        try:
            found = await ask(batch, f"methods/{i}", log)
            missing = [r for r in batch if r.key not in found]
            if missing:
                found |= await ask(missing, f"methods/{i}/missing", log)
        except CallFailed as exc:
            return [], {r: f"schema: {exc}"[:500] for r in batch}, log
        results, failed = [], {}
        for r in batch:
            d = found.get(r.key)
            if d is None:
                failed[r] = "no decision in the reply after the retry"
                continue
            content = MethodContent(
                methods=tuple(sorted(set(d["methods"]))), rationale=d["rationale"]
            )
            results.append((r, result(state, r, content, mode="full")))
        return results, failed, log

    outs = await asyncio.gather(*(run(i, b) for i, b in enumerate(batches)))
    results = tuple(x for res, _, _ in outs for x in res)
    failed = {r: m for _, f, _ in outs for r, m in f.items()}
    stats = {
        r: {**log.stats(), "batch": i}
        for i, (b, (_, _, log)) in enumerate(zip(batches, outs, strict=True))
        for r in b
    }
    return ProduceOutcome(results=results, failed=failed, stats=stats)


SPEC = register(
    StageSpec(
        kind=NodeKind.METHOD,
        uses_llm=True,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
        produce=produce,
        batched=True,
    )
)
