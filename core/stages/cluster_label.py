"""Model-written cluster name and rationale. The rename event writes a pinned edited version."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import PROJECT_CARD_KEY, NodeKind, NodeRef
from core.stages.base import StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState

CARD = NodeRef(kind=NodeKind.PROJECT_CARD, key=PROJECT_CARD_KEY)


def keys(state: ProjectState) -> Iterable[str]:
    """One per cluster, keyed by cluster id."""
    return state.keys_of(NodeKind.CLUSTER)


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """Member requirements in id order (ids and texts), then the project card."""
    return (*(NodeRef(kind=NodeKind.REQUIREMENT, key=m) for m in state.members(key)), CARD)


SPEC = register(
    StageSpec(
        kind=NodeKind.CLUSTER_LABEL,
        uses_llm=True,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
    )
)
