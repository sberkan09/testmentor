"""Verification method of one requirement. Cluster edits never stale it."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import PROJECT_CARD_KEY, NodeKind, NodeRef
from core.stages.base import StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState

CARD = NodeRef(kind=NodeKind.PROJECT_CARD, key=PROJECT_CARD_KEY)


def keys(state: ProjectState) -> Iterable[str]:
    """One per requirement, keyed by requirement id."""
    return state.keys_of(NodeKind.REQUIREMENT)


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """The requirement, then the project card."""
    return (NodeRef(kind=NodeKind.REQUIREMENT, key=key), CARD)


SPEC = register(
    StageSpec(
        kind=NodeKind.METHOD,
        uses_llm=True,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
    )
)
