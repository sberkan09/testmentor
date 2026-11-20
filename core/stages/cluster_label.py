"""Model-written cluster name and rationale. The rename event writes a pinned edited version."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import NodeKind, NodeRef
from core.stages.base import StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState


def keys(state: ProjectState) -> Iterable[str]:
    """One per cluster, keyed by cluster id."""
    raise NotImplementedError


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """Member requirements in id order (ids and texts), then the project card."""
    raise NotImplementedError


SPEC = register(
    StageSpec(
        kind=NodeKind.CLUSTER_LABEL,
        uses_llm=True,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
    )
)
