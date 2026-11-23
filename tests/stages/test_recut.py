"""First cut at import and re-cut on command (docs/tasarim.md, Öbekleme; paket 2 note: an
existing cluster key is never given to other requirements)."""

from __future__ import annotations

import itertools

from core.events import RequirementMoved
from core.invalidation import apply
from core.nodes import ClusterContent, NodeKind, ref
from core.settings import ClusteringSettings
from core.stages.clustering import cut, initial_membership, recut
from tests.core.helpers import produce_all
from tests.stages.helpers import REQS, project

AXES = {
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
    "xy": (0.5, 0.866, 0.0),  # cosine distance 0.5 to x
    "-z": (0.0, 0.0, -1.0),  # distance ~1 to x and xy: farther than x is from xy
}
SETTINGS = ClusteringSettings()


def vectors(groups: dict[str, str]) -> dict[str, list[float]]:
    """Requirement → a vector near the axis of its group (tiny per-id offset)."""
    out = {}
    for i, (rid, axis) in enumerate(sorted(groups.items())):
        out[rid] = [v + 0.001 * (i + 1) for v in AXES[axis]]
    return out


def ids():
    counter = itertools.count(1)
    return lambda: f"K{next(counter)}"


def state_with(clusters):
    return produce_all(project(REQS, clusters))


def test_cut_and_initial_membership():
    v = vectors({"R1": "x", "R2": "x", "R3": "y", "R4": "y", "R5": "z", "R6": "z"})
    order = sorted(v)
    assert cut(order, [v[r] for r in order], SETTINGS) == [("R1", "R2"), ("R3", "R4"), ("R5", "R6")]
    mem = initial_membership(order, [v[r] for r in order], SETTINGS, ids())
    assert mem == {"K1": ("R1", "R2"), "K2": ("R3", "R4"), "K3": ("R5", "R6")}


def test_cut_respects_max_cluster_size():
    v = vectors({r: "x" for r in REQS})
    order = sorted(v)
    small = SETTINGS.model_copy(update={"max_cluster_size": 4})
    assert [len(c) for c in cut(order, [v[r] for r in order], small)] == [4, 2]


def test_hdbscan_puts_noise_in_singletons():
    # With three orthogonal axes every inter-group distance is ~0.99 and R6 sits as close to
    # R4/R5 as the groups sit to each other, so HDBSCAN may join it to them. Here the groups are
    # 0.5 apart and R6 is ~1 from both: an unambiguous outlier.
    v = vectors({"R1": "x", "R2": "x", "R3": "x", "R4": "xy", "R5": "xy", "R6": "-z"})
    order = sorted(v)
    hd = SETTINGS.model_copy(update={"method": "hdbscan", "min_cluster_size": 2})
    clusters = cut(order, [v[r] for r in order], hd)
    assert sorted(m for c in clusters for m in c) == order
    assert ("R6",) in clusters


def test_recut_keeps_keys_with_majority_overlap():
    state = state_with({"A": ("R1", "R2", "R3"), "B": ("R4", "R5", "R6")})
    v = vectors({"R1": "x", "R2": "x", "R3": "x", "R4": "x", "R5": "y", "R6": "y"})
    event = recut(state, v, SETTINGS, ids())
    assert event.clusters == {"A": ("R1", "R2", "R3", "R4"), "B": ("R5", "R6")}
    apply(state, event)  # accepted


def test_recut_gives_new_keys_without_majority():
    state = state_with({"A": ("R1", "R2", "R3", "R4"), "B": ("R5", "R6")})
    v = vectors({"R1": "x", "R2": "x", "R3": "y", "R4": "y", "R5": "z", "R6": "z"})
    event = recut(state, v, SETTINGS, ids())
    assert event.clusters == {"B": ("R5", "R6"), "K1": ("R1", "R2"), "K2": ("R3", "R4")}


def test_recut_never_reuses_a_key_for_other_requirements():
    state = state_with({"A": ("R1", "R2"), "B": ("R3", "R4"), "C": ("R5", "R6")})
    v = vectors({"R1": "x", "R3": "x", "R5": "x", "R2": "y", "R4": "y", "R6": "y"})
    event = recut(state, v, SETTINGS, ids())
    assert set(event.clusters) == {"K1", "K2"}


def test_recut_keeps_pinned_assignments():
    state = state_with({"A": ("R1", "R2"), "B": ("R3", "R4"), "C": ("R5", "R6")})
    state, _ = apply(state, RequirementMoved(requirement="R3", to_cluster="A"))  # pinned in A
    v = vectors({"R1": "x", "R2": "x", "R3": "y", "R4": "y", "R5": "z", "R6": "z"})
    event = recut(state, v, SETTINGS, ids())
    assert "R3" in event.clusters["A"]
    new, _ = apply(state, event)
    content = new.node(ref(NodeKind.CLUSTER, "A")).content
    assert isinstance(content, ClusterContent) and "R3" in content.pinned_members
