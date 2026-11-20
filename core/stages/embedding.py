"""Embedding of one requirement (embedding model, not a model call in the bayatlama count)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import EmbeddingContent, NodeKind, NodeRef
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register
from core.stages.calls import result

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
    refs = sorted(ctx.refs, key=lambda r: r.key)
    if ctx.embed is None:
        return ProduceOutcome(failed={r: "no embedding service" for r in refs})
    vectors = await ctx.embed([ctx.state.requirement(r.key).text for r in refs])
    if len(vectors) != len(refs):
        msg = f"embedding returned {len(vectors)} vectors for {len(refs)} texts"
        return ProduceOutcome(failed={r: msg for r in refs})
    return ProduceOutcome(
        results=tuple(
            (
                r,
                result(
                    ctx.state,
                    r,
                    EmbeddingContent(vector=tuple(float(x) for x in v)),
                    mode="algorithm",
                ),
            )
            for r, v in zip(refs, vectors, strict=True)
        )
    )


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
