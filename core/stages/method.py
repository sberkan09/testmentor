"""Verification method of one requirement. Cluster edits never stale it."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import NodeKind, NodeRef
from core.stages.base import StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState


def keys(state: ProjectState) -> Iterable[str]:
    """One per requirement, keyed by requirement id."""
    raise NotImplementedError


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """The requirement, then the project card."""
    raise NotImplementedError


SPEC = register(
    StageSpec(
        kind=NodeKind.METHOD,
        uses_llm=True,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
    )
)
