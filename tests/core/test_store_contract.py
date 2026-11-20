"""Contract every `NodeStore` must pass. Paket 5 adds the Postgres factory to STORES."""

import pytest

from core.events import ClusterRenamed, RequirementMoved
from core.nodes import ClusterLabelContent, Node, NodeKind, ProducedBy, Result, Status, ref
from core.store import InMemoryStore, VersionConflict

STORES = [pytest.param(InMemoryStore, id="memory")]

LBL = ref(NodeKind.CLUSTER_LABEL, "A")


def label(name: str, version: int) -> Node:
    return Node(ref=LBL, content=ClusterLabelContent(name=name), input_hash="h", version=version)


@pytest.fixture(params=STORES)
def store(request):
    return request.param()


def test_put_and_get(store):
    store.put_node("P", label("Ad", 1), expected_version=0)
    assert store.get_node("P", LBL) == label("Ad", 1)
    assert store.get_node("P", ref(NodeKind.CLUSTER_LABEL, "B")) is None


def test_compare_and_set(store):
    store.put_node("P", label("Ad", 1), expected_version=0)
    with pytest.raises(VersionConflict) as exc:
        store.put_node("P", label("Başka", 1), expected_version=0)
    assert exc.value.current == label("Ad", 1)
    with pytest.raises(VersionConflict):
        store.put_node("P", label("Atlayan", 3), expected_version=1)  # version must be +1
    store.put_node("P", label("Yeni", 2), expected_version=1)
    assert store.get_node("P", LBL).content.name == "Yeni"


def test_history_survives_removal(store):
    store.put_node("P", label("v1", 1), expected_version=0)
    store.put_node("P", label("v2", 2), expected_version=1)
    store.remove_node("P", LBL, expected_version=2)
    assert store.get_node("P", LBL) is None
    assert LBL not in store.load("P")
    assert [n.content.name for n in store.history("P", LBL)] == ["v1", "v2"]
    with pytest.raises(VersionConflict):
        store.remove_node("P", LBL, expected_version=2)


def test_status_is_not_a_version(store):
    store.put_node("P", label("Ad", 1), expected_version=0)
    store.set_status("P", LBL, Status.STALE)
    node = store.get_node("P", LBL)
    assert node.status == Status.STALE
    assert node.version == 1
    assert len(store.history("P", LBL)) == 1


def test_recreate_after_removal_starts_at_one(store):
    store.put_node("P", label("v1", 1), expected_version=0)
    store.remove_node("P", LBL, expected_version=1)
    with pytest.raises(VersionConflict):
        store.put_node("P", label("yanlış", 2), expected_version=1)
    store.put_node("P", label("yeniden", 1), expected_version=0)
    store.put_node("P", label("yeniden 2", 2), expected_version=1)
    assert [n.content.name for n in store.history("P", LBL)] == ["v1", "yeniden", "yeniden 2"]


def test_projects_are_isolated(store):
    store.put_node("P", label("Ad", 1), expected_version=0)
    assert store.get_node("Q", LBL) is None
    assert store.load("Q") == {}
    assert store.load("P") == {LBL: label("Ad", 1)}
    store.put_node("Q", label("Q adı", 1), expected_version=0)  # same ref, own version line
    assert store.get_node("P", LBL).content.name == "Ad"


def test_output_cache(store):
    result = Result(
        input_hash="h",
        cache_key="k",
        content=ClusterLabelContent(name="Ad"),
        produced_by=ProducedBy(mode="full", model="llm"),
    )
    assert store.get("P", "k") is None
    store.put("P", "k", result)
    assert store.get("P", "k") == result
    assert store.get("Q", "k") is None


def test_event_log(store):
    e1 = RequirementMoved(requirement="R2", to_cluster="B")
    e2 = ClusterRenamed(cluster="A", name="Ad")
    assert store.append_event("P", e1, actor="ayse") == 1
    assert store.append_event("P", e2, actor="mehmet") == 2
    assert store.append_event("Q", e1, actor="ayse") == 1
    records = store.events("P")
    assert [(r.seq, r.actor, r.event) for r in records] == [(1, "ayse", e1), (2, "mehmet", e2)]
    assert [r.seq for r in store.events("P", after=1)] == [2]
