"""Test case set of one cluster (docs/tasarim.md, Test durumu üretimi).

Dependencies: member requirements (ids and texts), their verification methods (the generation
prompt tells the model which members need tests; paket 2 decision), the cluster's retrieved
passage ids and the project card. Context: the set's pinned test cases, which go to the prompt
as fixed and so key the output cache, but do not stale the set when edited.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from core.nodes import PROJECT_CARD_KEY, NodeKind, NodeRef
from core.stages.base import StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState

CARD = NodeRef(kind=NodeKind.PROJECT_CARD, key=PROJECT_CARD_KEY)


def keys(state: ProjectState) -> Iterable[str]:
    """One per cluster, keyed by cluster id."""
    return state.keys_of(NodeKind.CLUSTER)


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """Member requirements in id order, their methods in the same order, the cluster's retrieval,
    then the project card."""
    members = state.members(key)
    return (
        *(NodeRef(kind=NodeKind.REQUIREMENT, key=m) for m in members),
        *(NodeRef(kind=NodeKind.METHOD, key=m) for m in members),
        NodeRef(kind=NodeKind.RETRIEVAL, key=key),
        CARD,
    )


def context(state: ProjectState, key: str) -> Any:
    """Pinned test cases of the set as plain JSON, in case key order."""
    pinned = []
    for r in state.test_cases(key):
        node = state.node(r)
        if node.pinned and node.content is not None:
            pinned.append({"key": r.key, "content": node.content.model_dump(mode="json")})
    return pinned


SPEC = register(
    StageSpec(
        kind=NodeKind.TEST_SET,
        uses_llm=True,
        keys=keys,
        dependencies=dependencies,
        context=context,
    )
)
