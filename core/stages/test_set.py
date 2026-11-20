"""Test case set of one cluster (docs/tasarim.md, Test durumu üretimi).

Dependencies: member requirements (ids and texts), their verification methods (the generation
prompt tells the model which members need tests; paket 2 decision), the cluster's retrieved
passage ids and the project card. Context: the set's pinned test cases, which go to the prompt
as fixed and so key the output cache, but do not stale the set when edited.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from core.nodes import NodeKind, NodeRef
from core.stages.base import StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState


def keys(state: ProjectState) -> Iterable[str]:
    """One per cluster, keyed by cluster id."""
    raise NotImplementedError


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """Member requirements in id order, their methods in the same order, the cluster's retrieval,
    then the project card."""
    raise NotImplementedError


def context(state: ProjectState, key: str) -> Any:
    """Pinned test cases of the set as plain JSON, in case key order."""
    raise NotImplementedError


SPEC = register(
    StageSpec(
        kind=NodeKind.TEST_SET,
        uses_llm=True,
        keys=keys,
        dependencies=dependencies,
        context=context,
    )
)
