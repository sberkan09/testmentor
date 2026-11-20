"""Embedding of one requirement (embedding model, not a model call in the bayatlama count)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import NodeKind, NodeRef
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState
    from core.llm import Complete


def keys(state: ProjectState) -> Iterable[str]:
    """One per requirement, keyed by requirement id."""
    return state.keys_of(NodeKind.REQUIREMENT)


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """The requirement. The model version is in the stage config."""
    return (NodeRef(kind=NodeKind.REQUIREMENT, key=key),)


async def produce(ctx: ProduceContext, complete: Complete) -> ProduceOutcome:
    """Batched. Embeds the requirement texts of `ctx.refs` in one `ctx.embed` call
    (no model call in the bayatlama count); one `EmbeddingContent` per ref. Missing `ctx.embed`
    or a wrong vector count fails every ref."""
    raise NotImplementedError("paket 3 adım 4")


SPEC = register(
    StageSpec(
        kind=NodeKind.EMBEDDING,
        uses_llm=False,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=True,
        produce=produce,
        batched=True,
    )
)
