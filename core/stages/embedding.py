"""Embedding of one requirement (embedding model, not a model call in the bayatlama count)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import NodeKind, NodeRef
from core.stages.base import StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState


def keys(state: ProjectState) -> Iterable[str]:
    """One per requirement, keyed by requirement id."""
    return state.keys_of(NodeKind.REQUIREMENT)


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """The requirement. The model version is in the stage config."""
    return (NodeRef(kind=NodeKind.REQUIREMENT, key=key),)


SPEC = register(
    StageSpec(
        kind=NodeKind.EMBEDDING,
        uses_llm=False,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=True,
    )
)
