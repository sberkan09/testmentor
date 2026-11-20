"""Stage registry (docs/tasarim.md, Kod düzeni).

A stage declares the derived node kind it produces, which nodes of that kind should exist, what
each node depends on and what context it is produced with. The graph, the invalidation engine,
the orchestrator and the UI's state language read only these declarations, so a later module
arrives as one more registration. Producers (prompts, model calls) are not part of the
declaration; paket 3 adds them.

Dependencies vs context (docs/tasarim.md, Veri modeli kuralları): dependencies enter
`input_hash` and decide staleness; context (pinned test cases, an extra instruction) enters
only the output cache key. Production mode (incremental, merge, repair) enters neither.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.nodes import NodeKind, NodeRef

if TYPE_CHECKING:
    from core.graph import ProjectState


def no_context(state: ProjectState, key: str) -> Any:
    return None


@dataclass(frozen=True)
class StageSpec:
    kind: NodeKind
    uses_llm: bool
    keys: Callable[[ProjectState], Iterable[str]]
    """Keys of the nodes of this kind that should exist in the current state."""
    dependencies: Callable[[ProjectState, str], Sequence[NodeRef]]
    """Upstream nodes in a deterministic order; their identities enter `input_hash`."""
    context: Callable[[ProjectState, str], Any] = no_context
    """Plain JSON that enters only `cache_key`."""
    identity_by_input: bool = False
    """Dependents see this node through its expected `input_hash` instead of its content hash.
    For deterministic, non-model stages whose outputs are not byte-stable (embedding vectors)."""


_REGISTRY: dict[NodeKind, StageSpec] = {}


def register(spec: StageSpec) -> StageSpec:
    if spec.kind in _REGISTRY:
        raise ValueError(f"stage already registered: {spec.kind}")
    _REGISTRY[spec.kind] = spec
    return spec


def get(kind: NodeKind) -> StageSpec:
    return _REGISTRY[kind]


def all_specs() -> tuple[StageSpec, ...]:
    """Registered stages in topological order (the order of `NodeKind`)."""
    order = list(NodeKind)
    return tuple(sorted(_REGISTRY.values(), key=lambda s: order.index(s.kind)))
