"""The agglomerative tree over all embeddings. Clusters depend on membership, not on this tree:
a stale tree is shown, and re-cutting happens only on an explicit command (MembershipChanged)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

import numpy as np

from core.clustering import build_tree
from core.events import MembershipChanged
from core.nodes import (
    CLUSTERING_KEY,
    ClusterContent,
    ClusteringContent,
    EmbeddingContent,
    NodeKind,
    NodeRef,
)
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register
from core.stages.calls import result

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
    state = ctx.state
    ids = state.keys_of(NodeKind.REQUIREMENT)
    vectors = []
    for rid in ids:
        emb = state.node(NodeRef(kind=NodeKind.EMBEDDING, key=rid)).content
        if not isinstance(emb, EmbeddingContent):
            return ProduceOutcome(failed={r: f"no embedding for {rid}" for r in ctx.refs})
        vectors.append(emb.vector)
    tree = build_tree(ids, vectors, ctx.settings.clustering.linkage)
    content = ClusteringContent(
        ids=tree.ids,
        linkage=tuple(tuple(float(x) for x in row) for row in tree.linkage_matrix.tolist()),
    )
    return ProduceOutcome(
        results=tuple((r, result(state, r, content, mode="algorithm")) for r in ctx.refs)
    )


def cut(
    ids: Sequence[str], vectors: Sequence[Sequence[float]], settings: ClusteringSettings
) -> list[tuple[str, ...]]:
    """Clusters as sorted id tuples ordered by first id. Agglomerative: `build_tree` with
    `settings.linkage`, `ClusterTree.cut(distance_threshold, max_cluster_size)`. HDBSCAN
    (D6): cosine distances, `min_cluster_size`; every noise point becomes its own cluster; then
    the same `max_cluster_size` chunking. Deterministic for the same input."""
    n = len(ids)
    if n == 0:
        return []
    if settings.method == "agglomerative":
        tree = build_tree(ids, vectors, settings.linkage)
        groups = tree.cut(settings.distance_threshold, settings.max_cluster_size)
        return [tuple(g) for g in groups]
    order = sorted(range(n), key=lambda i: ids[i])
    sorted_ids = [ids[i] for i in order]
    labels = _hdbscan_labels([vectors[i] for i in order], settings.min_cluster_size)
    by_label: dict[int, list[str]] = {}
    singles: list[list[str]] = []
    for rid, label in zip(sorted_ids, labels, strict=True):
        if label < 0:
            singles.append([rid])
        else:
            by_label.setdefault(label, []).append(rid)
    size = settings.max_cluster_size
    out = [
        tuple(g[i : i + size])
        for g in [*by_label.values(), *singles]
        for i in range(0, len(g), size)
    ]
    return sorted(out, key=lambda c: c[0])


def _hdbscan_labels(vectors: Sequence[Sequence[float]], min_cluster_size: int) -> list[int]:
    """HDBSCAN over precomputed cosine distances; -1 is noise. Fewer points than
    `min_cluster_size` are all noise."""
    if len(vectors) < max(2, min_cluster_size):
        return [-1] * len(vectors)
    from scipy.spatial.distance import pdist, squareform
    from sklearn.cluster import HDBSCAN

    x = np.asarray(vectors, dtype=float)
    dist = squareform(np.clip(pdist(x, metric="cosine"), 0.0, 2.0))
    model = HDBSCAN(min_cluster_size=min_cluster_size, metric="precomputed", copy=True)
    return [int(v) for v in model.fit_predict(dist)]


def initial_membership(
    ids: Sequence[str],
    vectors: Sequence[Sequence[float]],
    settings: ClusteringSettings,
    new_id: Callable[[], str],
) -> dict[str, tuple[str, ...]]:
    """First cut at import, before `new_project` (which needs every requirement placed): `cut`,
    then one `new_id()` per cluster in cluster order."""
    return {new_id(): group for group in cut(ids, vectors, settings)}


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
    from scipy.optimize import linear_sum_assignment

    old_keys = list(state.keys_of(NodeKind.CLUSTER))
    pinned: dict[str, set[str]] = {}
    free_of: dict[str, set[str]] = {}
    for c in old_keys:
        content = state.node(NodeRef(kind=NodeKind.CLUSTER, key=c)).content
        assert isinstance(content, ClusterContent)
        pinned[c] = set(content.pinned_members)
        free_of[c] = set(content.members) - pinned[c]
    all_pinned = set().union(*pinned.values()) if pinned else set()
    free = [r for r in state.keys_of(NodeKind.REQUIREMENT) if r not in all_pinned]
    groups = cut(free, [vectors[r] for r in free], settings) if free else []

    # Maximum total overlap; among equal totals prefer smaller old keys, then groups with the
    # smaller first id (`groups` and `old_keys` are already in that order).
    ng, nc = len(groups), len(old_keys)
    match: dict[int, str] = {}
    if ng and nc:
        scale = float(ng * nc + 1)
        cost = np.zeros((ng, nc))
        for g, members in enumerate(groups):
            for c, key in enumerate(old_keys):
                overlap = len(free_of[key].intersection(members))
                cost[g, c] = -overlap * scale + (c * ng + g) / (ng * nc)
        rows, cols = linear_sum_assignment(cost)
        match = {int(g): old_keys[int(c)] for g, c in zip(rows, cols, strict=True)}

    clusters: dict[str, set[str]] = {c: set(p) for c, p in pinned.items() if p}
    for g, members in enumerate(groups):
        key = match.get(g)
        if key is not None and len(free_of[key].intersection(members)) * 2 > len(free_of[key]):
            clusters.setdefault(key, set()).update(members)
        else:
            clusters[new_id()] = set(members)
    return MembershipChanged(clusters={k: tuple(sorted(v)) for k, v in clusters.items()})


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
