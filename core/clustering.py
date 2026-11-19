"""Hierarchical (agglomerative) clustering over cosine distance. The tree is kept so the cut level
can change without recomputation (docs/tasarim.md, Öbekleme)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist


@dataclass(frozen=True)
class ClusterTree:
    ids: tuple[str, ...]
    linkage_matrix: np.ndarray

    def cut(
        self, distance_threshold: float, max_cluster_size: int | None = None
    ) -> list[list[str]]:
        """Clusters as id lists, each sorted, ordered by their first id (deterministic)."""
        n = len(self.ids)
        if n == 0:
            return []
        if n == 1:
            return [[self.ids[0]]]
        labels = fcluster(self.linkage_matrix, t=distance_threshold, criterion="distance")
        groups: dict[int, list[str]] = {}
        for rid, label in zip(self.ids, labels, strict=True):
            groups.setdefault(int(label), []).append(rid)
        clusters = [sorted(g) for g in groups.values()]
        if max_cluster_size:
            clusters = [
                part
                for c in clusters
                for part in (
                    c[i : i + max_cluster_size] for i in range(0, len(c), max_cluster_size)
                )
            ]
        return sorted(clusters, key=lambda c: c[0])


def build_tree(
    ids: Sequence[str], vectors: Sequence[Sequence[float]], method: str = "average"
) -> ClusterTree:
    order = sorted(range(len(ids)), key=lambda i: ids[i])
    sorted_ids = tuple(ids[i] for i in order)
    x = np.asarray([vectors[i] for i in order], dtype=float)
    if len(sorted_ids) < 2:
        return ClusterTree(sorted_ids, np.zeros((0, 4)))
    dist = np.clip(pdist(x, metric="cosine"), 0.0, 2.0)
    return ClusterTree(sorted_ids, linkage(dist, method=method))
