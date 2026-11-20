"""Knowledge base search for one cluster. The query is the member texts only; the cluster name is
not part of it (docs/tasarim.md, İndeks)."""

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
    """Member requirements in id order, then the knowledge base index node."""
    raise NotImplementedError


SPEC = register(
    StageSpec(
        kind=NodeKind.RETRIEVAL,
        uses_llm=False,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
    )
)
