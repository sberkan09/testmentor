"""Matrix row of one requirement (SQL join in paket 4; no model call)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import MatrixRowContent, MethodContent, NodeKind, NodeRef
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register
from core.stages.calls import result

if TYPE_CHECKING:
    from core.graph import ProjectState
    from core.llm import Complete


def keys(state: ProjectState) -> Iterable[str]:
    """One per requirement, keyed by requirement id."""
    return state.keys_of(NodeKind.REQUIREMENT)


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """The requirement (so that two rows never share a cache key), its method, then every test
    case whose `covers` contains the requirement, in case key order."""
    return (
        NodeRef(kind=NodeKind.REQUIREMENT, key=key),
        NodeRef(kind=NodeKind.METHOD, key=key),
        *state.cases_covering(key),
    )


async def produce(ctx: ProduceContext, complete: Complete) -> ProduceOutcome:
    """Batched, no model call. Per requirement: its METHOD methods (empty if the method
    has no content), the keys of the test cases covering it (`state.cases_covering`), and
    `covered` = any case covers it."""
    state = ctx.state
    out = []
    for r in ctx.refs:
        method = state.node(NodeRef(kind=NodeKind.METHOD, key=r.key)).content
        keys = tuple(c.key for c in state.cases_covering(r.key))
        content = MatrixRowContent(
            requirement_id=r.key,
            methods=method.methods if isinstance(method, MethodContent) else (),
            test_case_keys=keys,
            covered=bool(keys),
        )
        out.append((r, result(state, r, content, mode="algorithm")))
    return ProduceOutcome(results=tuple(out))


SPEC = register(
    StageSpec(
        kind=NodeKind.MATRIX_ROW,
        uses_llm=False,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
        produce=produce,
        batched=True,
    )
)
