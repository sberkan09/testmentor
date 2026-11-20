"""Matrix row of one requirement (SQL join in paket 4; no model call)."""

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
    """The requirement's method, then every test case whose `covers` contains the requirement, in
    case key order."""
    return (NodeRef(kind=NodeKind.METHOD, key=key), *state.cases_covering(key))


SPEC = register(
    StageSpec(
        kind=NodeKind.MATRIX_ROW,
        uses_llm=False,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
    )
)
