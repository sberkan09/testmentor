"""The agglomerative tree over all embeddings. Clusters depend on membership, not on this tree:
a stale tree is shown, and re-cutting happens only on an explicit command (MembershipChanged)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import CLUSTERING_KEY, NodeKind, NodeRef
from core.stages.base import StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState


def keys(state: ProjectState) -> Iterable[str]:
    """`CLUSTERING_KEY` when the project has requirements, otherwise none."""
    return (CLUSTERING_KEY,) if state.keys_of(NodeKind.REQUIREMENT) else ()


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """Every embedding, in requirement id order. Linkage and threshold are in the stage config."""
    return tuple(
        NodeRef(kind=NodeKind.EMBEDDING, key=r) for r in state.keys_of(NodeKind.REQUIREMENT)
    )


SPEC = register(
    StageSpec(
        kind=NodeKind.CLUSTERING,
        uses_llm=False,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
    )
)
