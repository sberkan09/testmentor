"""Knowledge base search for one cluster. The query is the member texts only; the cluster name is
not part of it (docs/tasarim.md, İndeks)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import KB_INDEX_KEY, NodeKind, NodeRef
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState
    from core.llm import Complete

INDEX = NodeRef(kind=NodeKind.KB_INDEX, key=KB_INDEX_KEY)


def keys(state: ProjectState) -> Iterable[str]:
    """One per cluster, keyed by cluster id."""
    return state.keys_of(NodeKind.CLUSTER)


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """Member requirements in id order, then the knowledge base index node."""
    return (*(NodeRef(kind=NodeKind.REQUIREMENT, key=m) for m in state.members(key)), INDEX)


async def produce(ctx: ProduceContext, complete: Complete) -> ProduceOutcome:
    """`ctx.retrieve(members)`; `RetrievalContent(passage_ids)` in the returned order,
    duplicates removed. Missing `ctx.retrieve` gives an empty list (no knowledge base)."""
    raise NotImplementedError("paket 3 adım 4")


SPEC = register(
    StageSpec(
        kind=NodeKind.RETRIEVAL,
        uses_llm=False,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
        produce=produce,
        batched=False,
    )
)
