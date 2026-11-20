"""The agglomerative tree over all embeddings. Clusters depend on membership, not on this tree:
a stale tree is shown, and re-cutting happens only on an explicit command (MembershipChanged)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from core.events import MembershipChanged
from core.nodes import CLUSTERING_KEY, NodeKind, NodeRef
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register

if TYPE_CHECKING:
    from core.graph import ProjectState
    from core.llm import Complete
    from core.settings import ClusteringSettings


def keys(state: ProjectState) -> Iterable[str]:
    """`CLUSTERING_KEY` when the project has requirements, otherwise none."""
    return (CLUSTERING_KEY,) if state.keys_of(NodeKind.REQUIREMENT) else ()


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """Every embedding, in requirement id order. Linkage and threshold are in the stage config."""
    return tuple(
        NodeRef(kind=NodeKind.EMBEDDING, key=r) for r in state.keys_of(NodeKind.REQUIREMENT)
    )


async def produce(ctx: ProduceContext, complete: Complete) -> ProduceOutcome:
    """`core.clustering.build_tree` over the embedding vectors in requirement id
    order with `settings.clustering.linkage`; `ClusteringContent(ids, linkage)`. The tree does
    not change membership: re-cutting is `recut`, on an explicit command."""
    raise NotImplementedError("paket 3 adım 4")


def cut(
    ids: Sequence[str], vectors: Sequence[Sequence[float]], settings: ClusteringSettings
) -> list[tuple[str, ...]]:
    """Clusters as sorted id tuples ordered by first id. Agglomerative: `build_tree` with
    `settings.linkage`, `ClusterTree.cut(distance_threshold, max_cluster_size)`. HDBSCAN
    (D6): cosine distances, `min_cluster_size`; every noise point becomes its own cluster; then
    the same `max_cluster_size` chunking. Deterministic for the same input."""
    raise NotImplementedError("paket 3 adım 4")


def initial_membership(
    ids: Sequence[str],
    vectors: Sequence[Sequence[float]],
    settings: ClusteringSettings,
    new_id: Callable[[], str],
) -> dict[str, tuple[str, ...]]:
    """First cut at import, before `new_project` (which needs every requirement placed): `cut`,
    then one `new_id()` per cluster in cluster order."""
    raise NotImplementedError("paket 3 adım 4")


def recut(
    state: ProjectState,
    vectors: Mapping[str, Sequence[float]],
    settings: ClusteringSettings,
    new_id: Callable[[], str],
) -> MembershipChanged:
    """A new cut on an explicit command (granularity slider, re-cluster).

    1. Pinned assignments (`ClusterContent.pinned_members`) stay in their cluster; only the
       other requirements are cut (`cut` over their vectors). A cluster left with pinned
       members only keeps its key with those members.
    2. Each new group is matched one to one with an old cluster by the number of shared
       (unpinned) members, maximum total overlap (`scipy.optimize.linear_sum_assignment`; ties
       to the smaller old key, then the group with the smaller first id).
    3. A group takes the old key only if more than half of that old cluster's unpinned members
       are in it (an old key is never given to a group of other requirements); otherwise it
       gets `new_id()`, called in group order. A group matched to an old cluster that keeps
       pinned members is merged into that cluster.
    The result places every requirement exactly once (`apply` checks it)."""
    raise NotImplementedError("paket 3 adım 4")


SPEC = register(
    StageSpec(
        kind=NodeKind.CLUSTERING,
        uses_llm=False,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
        produce=produce,
        batched=False,
    )
)
