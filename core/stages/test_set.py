"""Test case set of one cluster (docs/tasarim.md, Test durumu üretimi).

Dependencies: member requirements (ids and texts), their verification methods (the generation
prompt tells the model which members need tests; paket 2 decision), the cluster's retrieved
passage ids and the project card. Context: the set's pinned test cases, which go to the prompt
as fixed and so key the output cache, but do not stale the set when edited.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from core.nodes import PROJECT_CARD_KEY, NodeKind, NodeRef
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register

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
       happens (design call count; D8 measures pruning without a call).
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
    raise NotImplementedError("paket 3 adım 4")


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
