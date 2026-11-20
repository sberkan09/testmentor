"""Verification method of one requirement. Cluster edits never stale it."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import PROJECT_CARD_KEY, NodeKind, NodeRef
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register

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
    raise NotImplementedError("paket 3 adım 4")


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
