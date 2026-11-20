"""Stage registry (docs/tasarim.md, Kod düzeni).

A stage declares the derived node kind it produces, which nodes of that kind should exist, what
each node depends on and what context it is produced with. The graph, the invalidation engine,
the orchestrator and the UI's state language read only these declarations, so a later module
arrives as one more registration. Paket 3 adds the producer: an async function that turns the
current state into results for `settle` / `settle_many`, calling the model only through the
injected `core.llm.Complete`.

Dependencies vs context (docs/tasarim.md, Veri modeli kuralları): dependencies enter
`input_hash` and decide staleness; context (pinned test cases, an extra instruction) enters
only the output cache key. Production mode (incremental, merge, repair) enters neither.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from core.nodes import NodeKind, NodeRef, RequirementContent, Result, TestCaseContent

if TYPE_CHECKING:
    from core.graph import ProjectState
    from core.invalidation import Hint
    from core.llm import Complete
    from core.settings import StageSettings


def no_context(state: ProjectState, key: str) -> Any:
    return None


# Production (paket 3) ---------------------------------------------------------------------------


class Embed(Protocol):
    """Embedding service (`services/embedder.py`); one vector per text, same order."""

    async def __call__(self, texts: Sequence[str]) -> list[list[float]]: ...


class Retrieve(Protocol):
    """Knowledge base search for one cluster (paket 7). The query is the member texts only;
    returns passage ids in rank order. Paket 3 ships `none` (empty) and, in eval, `gold`."""

    async def __call__(self, members: Sequence[RequirementContent]) -> list[str]: ...


class PassageSource(Protocol):
    """Passage ids to texts, same order (paket 7)."""

    def __call__(self, ids: Sequence[str]) -> list[str]: ...


@dataclass(frozen=True)
class ProduceContext:
    """Everything a producer reads. `state` is the snapshot the job started from: results carry
    its expected hash and cache key, so `settle` rejects them if the node changed meanwhile."""

    state: ProjectState
    refs: tuple[NodeRef, ...]
    """One node, or several for a batched stage (`StageSpec.batched`)."""
    settings: StageSettings
    hint: Hint | None = None
    """From `Invalidation.hints`; advisory. The test set producer checks it (see
    `core.stages.test_generation.choose_mode`)."""
    sources: Mapping[NodeRef, Sequence[TestCaseContent]] = field(default_factory=dict)
    """Merge: the cases of the removed source sets, read by the caller from store history."""
    embed: Embed | None = None
    retrieve: Retrieve | None = None
    passages: PassageSource | None = None


@dataclass(frozen=True)
class ProduceOutcome:
    results: tuple[tuple[NodeRef, Result], ...] = ()
    failed: Mapping[NodeRef, str] = field(default_factory=dict)
    """Nodes that could not be produced (schema invalid after the retry, missing from a batch
    reply after the single retry). The caller marks them failed (`mark_failed`)."""
    stats: Mapping[NodeRef, Mapping[str, Any]] = field(default_factory=dict)
    """Per-node measurements for eval: mode, calls, dropped covers, uncovered requirements,
    pinned update attempts, units. Never part of a hash."""


Producer = Callable[[ProduceContext, "Complete"], Awaitable[ProduceOutcome]]


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
    produce: Producer | None = None
    """None only for a stage that is declared but not produced yet."""
    batched: bool = False
    """The producer accepts several ready nodes in one call (embedding, method, matrix)."""


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
