"""Regression tests for the independent paket 2 review (session_011u662jZq7JAYJUrGuXYW6N)."""

import random

import pytest

from core.events import (
    ClusterDeleted,
    ClusterRenamed,
    ClustersMerged,
    KbDocumentAdded,
    MethodEdited,
    NodeKept,
    NodePinned,
    NodeUnpinned,
    RequirementMoved,
    RequirementTextChanged,
    TestCaseEdited,
)
from core.graph import ProjectState, cache_key, expected_hash, new_project
from core.invalidation import analyze, apply, mark_running, settle, settle_many
from core.nodes import (
    CHILD_KINDS,
    SOURCE_KINDS,
    NodeKind,
    RequirementContent,
    StageConfig,
    Status,
    ref,
)
from core.store import InMemoryStore
from tests.core.helpers import (
    CONFIGS,
    EMB,
    LABEL,
    METHOD,
    MX,
    REQ_TEXTS,
    SET,
    TC,
    TREE,
    case,
    fake_result,
    fresh_project,
    produce_all,
)


def _same_config_project():
    """METHOD and CLUSTER_LABEL share one config; cluster A has a single member."""
    same = StageConfig(prompt_version="p1", model="llm")
    configs = CONFIGS | {NodeKind.METHOD: same, NodeKind.CLUSTER_LABEL: same}
    state = new_project(
        "P",
        requirements=[RequirementContent(id="R1", text="x"), RequirementContent(id="R2", text="y")],
        clusters={"A": ("R1",), "B": ("R2",)},
        card="Kart",
        index_version="v1",
        stage_configs=configs,
    )
    return state


def test_two_stages_with_same_inputs_and_config_do_not_share_keys():
    """Bulgu 1: the node kind enters the hash, so a cached method never lands on a label."""
    state = _same_config_project()
    assert expected_hash(state, METHOD("R1")) != expected_hash(state, LABEL("A"))
    assert cache_key(state, METHOD("R1")) != cache_key(state, LABEL("A"))

    cache = InMemoryStore()
    state = produce_all(state, cache)
    state, inv = apply(state, KbDocumentAdded(document_id="d2", index_version="v2"), cache=cache)
    assert state.node(LABEL("A")).content.kind == "cluster_label"


def test_result_of_wrong_kind_is_rejected(project):
    state, _ = project
    method = fake_result(state, METHOD("R1"))
    forged = method.model_copy(
        update={
            "input_hash": expected_hash(state, LABEL("A")),
            "cache_key": cache_key(state, LABEL("A")),
        }
    )
    assert not settle(state, LABEL("A"), forged).accepted


def test_pinning_a_running_node_cancels_it():
    """Bulgu 2: a pinned running node must not stay running and block its dependents."""
    state, _ = fresh_project()
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    state = produce_all_but(state, SET("A"))
    state = mark_running(state, SET("A"))
    state, inv = apply(state, NodePinned(node=SET("A")))

    assert inv.cancel == {SET("A")}
    node = state.node(SET("A"))
    assert node.status == Status.STALE and node.pinned
    a = analyze(state)
    assert SET("A") in a.pinned_warnings
    assert MX("R1") not in a.to_verify  # the pinned set no longer blocks


def test_placeholder_cannot_be_pinned_or_kept():
    """Bulgu 3."""
    state = _same_config_project()
    with pytest.raises(ValueError):
        apply(state, NodePinned(node=METHOD("R1")))
    with pytest.raises(ValueError):
        apply(state, NodeKept(node=METHOD("R1")))


def test_context_change_cancels_running_set_and_rejects_old_result(project):
    """Bulgu 4: a case edited while its set runs changes the context; the old job is cancelled."""
    state, _ = project
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    state = produce_all_but(state, SET("A"))
    old = fake_result(state, SET("A"))
    state = mark_running(state, SET("A"))
    edited = case("R1", title="Elle yazılmış")
    state, inv = apply(state, TestCaseEdited(case=TC("A", "R1").key, content=edited))

    assert inv.cancel == {SET("A")}
    assert state.node(SET("A")).status == Status.STALE
    assert old.input_hash == expected_hash(state, SET("A"))  # same inputs ...
    assert not settle(state, SET("A"), old).accepted  # ... but an old context
    assert settle(state, SET("A"), fake_result(state, SET("A"))).accepted


def test_running_node_whose_inputs_return_is_fresh(project):
    """Bulgu 5: a running node whose inputs went back to its recorded hash is fresh, not stale."""
    state, _ = project
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    state = mark_running(state, LABEL("A"))
    state, inv = apply(state, RequirementMoved(requirement="R2", to_cluster="A"))

    assert inv.cancel == {LABEL("A")}
    assert state.node(LABEL("A")).status == Status.FRESH
    assert analyze(state).stale == frozenset()


def test_result_with_pending_upstream_is_rejected(project):
    """Bulgu 6: the tree is not accepted while an embedding it reads is still stale."""
    state, _ = project
    state, _ = apply(state, RequirementTextChanged(requirement="R1", text="Yeni metin"))
    assert state.node(EMB("R1")).status == Status.STALE
    assert not settle(state, TREE, fake_result(state, TREE)).accepted


def test_settle_many_reports_duplicate_ref(project):
    """Bulgu 8: a second result for the same ref is listed as rejected."""
    state, _ = project
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    r = fake_result(state, LABEL("A"))
    out = settle_many(state, [(LABEL("A"), r), (LABEL("A"), r)])
    assert LABEL("A") in out.accepted and LABEL("A") in out.rejected


def produce_all_but(state, skip):
    for _ in range(20):
        ready = [r for r in analyze(state).ready if r != skip]
        if not ready:
            return state
        for r in ready:
            state = settle(state, r, fake_result(state, r)).state
    raise AssertionError("did not converge")


# Property test --------------------------------------------------------------------------------


def _random_event(rng: random.Random, state: ProjectState, step: int):
    clusters = list(state.keys_of(NodeKind.CLUSTER))
    reqs = list(REQ_TEXTS)
    kind = rng.choice(
        ["move", "move", "text", "kb", "method", "rename", "pin", "case", "merge", "delete"]
    )
    if kind == "move":
        return RequirementMoved(requirement=rng.choice(reqs), to_cluster=rng.choice(clusters))
    if kind == "text":
        return RequirementTextChanged(
            requirement=rng.choice(reqs), text=f"metin {rng.randint(0, 3)}"
        )
    if kind == "kb":
        return KbDocumentAdded(document_id="d", index_version=f"v{rng.randint(1, 3)}")
    if kind == "method":
        return MethodEdited(requirement=rng.choice(reqs), methods=(rng.choice(["Test", "Analiz"]),))
    if kind == "rename":
        return ClusterRenamed(cluster=rng.choice(clusters), name=f"Ad {rng.randint(0, 3)}")
    if kind == "pin":
        produced = [
            r
            for r, n in state.nodes.items()
            if r.kind not in SOURCE_KINDS and n.content is not None
        ]
        r = rng.choice(sorted(produced, key=lambda x: x.sort_key()))
        return NodeUnpinned(node=r) if state.node(r).pinned else NodePinned(node=r)
    if kind == "case":
        cases = list(state.keys_of(NodeKind.TEST_CASE))
        if not cases:
            return None
        key = rng.choice(cases)
        req = state.node(ref(NodeKind.TEST_CASE, key)).content.covers[0]
        return TestCaseEdited(case=key, content=case(req, covers=(req, rng.choice(reqs))))
    if kind == "merge" and len(clusters) >= 3:
        a, b = rng.sample(clusters, 2)
        return ClustersMerged(sources=(a, b), new_cluster=f"M{step}")
    if kind == "delete" and len(clusters) >= 3:
        gone = rng.choice(clusters)
        rest = [c for c in clusters if c != gone]
        return ClusterDeleted(
            cluster=gone, destinations={m: rng.choice(rest) for m in state.members(gone)}
        )
    return None


@pytest.mark.parametrize("seed", range(30))
def test_incremental_path_matches_full_recompute_random(seed):
    """Random events, partial production, running and cache: the incrementally derived state
    always agrees with a rebuilt one (fresh memo) on hashes, statuses and analysis."""
    rng = random.Random(seed)
    state, cache = fresh_project()
    for step in range(12):
        event = _random_event(rng, state, step)
        if event is not None:
            state, _ = apply(state, event, cache=cache if rng.random() < 0.5 else None)
        ready = list(analyze(state).ready)
        rng.shuffle(ready)
        for r in ready[: rng.randint(0, len(ready))]:
            if rng.random() < 0.15:
                state = mark_running(state, r)
                continue
            result = fake_result(state, r)
            state = settle(state, r, result).state
            cache.put(state.project_id, result.cache_key, result)
        rebuilt = ProjectState(
            project_id=state.project_id, nodes=state.nodes, stage_configs=state.stage_configs
        )
        derived = [x for x in state.nodes if x.kind not in SOURCE_KINDS | CHILD_KINDS]
        for x in derived:
            assert expected_hash(state, x) == expected_hash(rebuilt, x), (seed, step, x)
            n = state.node(x)
            if n.status in (Status.FRESH, Status.STALE):
                want = n.content is None or n.input_hash != expected_hash(rebuilt, x)
                assert (n.status == Status.STALE) == want, (seed, step, x)
        assert analyze(state) == analyze(rebuilt), (seed, step)
