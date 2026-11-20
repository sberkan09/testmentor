"""Rules behind the table (docs/tasarim.md, Veri modeli kuralları): pinning, undo through the
cache, cancelling running work, empty clusters, context vs dependency."""

from core.events import (
    ClusterRenamed,
    MethodEdited,
    NodePinned,
    NodeUnpinned,
    RequirementMoved,
    RequirementTextChanged,
    TestCaseEdited,
)
from core.graph import cache_key, expected_hash
from core.invalidation import analyze, apply, mark_running, settle
from core.nodes import Origin, Status
from tests.core.helpers import (
    CL,
    LABEL,
    METHOD,
    RET,
    SET,
    TC,
    case,
    fake_result,
    produce_all,
)


def test_pinned_label_stales_without_call(project):
    """A pinned stale node is warned about, not counted and never queued."""
    state, cache = project
    state, _ = apply(state, ClusterRenamed(cluster="B", name="Denetim izi"))
    state, inv = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))

    assert LABEL("B") in inv.stale
    assert inv.pinned_warnings == {LABEL("B")}
    assert inv.llm_calls == 3
    state = produce_all(state, cache)
    a = analyze(state)
    assert a.stale == {LABEL("B")}
    assert a.pinned_warnings == {LABEL("B")}
    assert a.llm_calls == 0
    assert state.node(LABEL("B")).content.name == "Denetim izi"


def test_unpin_makes_node_plannable(project):
    state, cache = project
    state, _ = apply(state, ClusterRenamed(cluster="B", name="Denetim izi"))
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    state = produce_all(state, cache)
    state, inv = apply(state, NodeUnpinned(node=LABEL("B")))

    assert inv.llm_calls == 1
    assert analyze(state).ready == (LABEL("B"),)


def test_pin_event_protects_generated_node(project):
    state, _ = project
    state, _ = apply(state, NodePinned(node=LABEL("A")))
    state, inv = apply(
        state, RequirementTextChanged(requirement="R1", text="Sistem, girişi 5 denemede kilitler.")
    )
    assert LABEL("A") in inv.pinned_warnings
    assert inv.llm_calls == 2  # method, test set


def test_pinned_stale_upstream_does_not_block(project):
    """A pinned method that went stale still feeds its set: the set is produced, no deadlock."""
    state, cache = project
    state, _ = apply(state, MethodEdited(requirement="R1", methods=("Analiz",)))
    state = produce_all(state, cache)
    state, _ = apply(
        state, RequirementTextChanged(requirement="R1", text="Sistem, girişi 5 denemede kilitler.")
    )
    state = produce_all(state, cache)

    a = analyze(state)
    assert a.stale == {METHOD("R1")}
    assert a.pinned_warnings == {METHOD("R1")}
    assert state.node(SET("A")).status == Status.FRESH


def test_move_back_before_regeneration_is_free(project):
    """Hash equality: undoing before anything ran makes the old outputs fresh again."""
    state, _ = project
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    state, inv = apply(state, RequirementMoved(requirement="R2", to_cluster="A"))

    assert inv.llm_calls == 0
    a = analyze(state)
    assert a.stale == frozenset() and a.to_verify == frozenset()


def test_move_and_undo_comes_from_cache(project):
    """Taşıyıp geri almak cache'ten döner: 0 model çağrısı."""
    state, cache = project
    original = state.node(SET("A")).content
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    state = produce_all(state, cache)
    state, inv = apply(state, RequirementMoved(requirement="R2", to_cluster="A"), cache=cache)

    assert inv.llm_calls == 0
    assert {SET("A"), SET("B"), LABEL("A"), LABEL("B")} <= inv.cache_hits
    a = analyze(state)
    assert a.stale == frozenset() and a.to_verify == frozenset()
    assert state.node(SET("A")).content == original


def test_running_node_cancelled_when_inputs_change(project):
    state, _ = project
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    state = produce_all_but(state, SET("A"))
    old_result = fake_result(state, SET("A"))
    state = mark_running(state, SET("A"))
    assert state.node(SET("A")).status == Status.RUNNING

    state, inv = apply(state, RequirementMoved(requirement="R3", to_cluster="A"))
    assert SET("A") in inv.cancel
    assert state.node(SET("A")).status == Status.STALE

    before = state.node(SET("A"))
    out = settle(state, SET("A"), old_result)
    assert not out.accepted
    assert out.state.node(SET("A")) == before


def test_running_node_kept_when_inputs_unchanged(project):
    state, _ = project
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    state = produce_all_but(state, SET("A"))
    state = mark_running(state, SET("A"))
    state, inv = apply(state, ClusterRenamed(cluster="C", name="Performans"))

    assert inv.cancel == frozenset()
    assert state.node(SET("A")).status == Status.RUNNING
    out = settle(state, SET("A"), fake_result(state, SET("A")))
    assert out.accepted
    assert out.state.node(SET("A")).status == Status.FRESH


def test_last_member_moved_removes_cluster(project):
    state, _ = project
    state, _ = apply(state, RequirementMoved(requirement="R1", to_cluster="B"))
    state, inv = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))

    assert inv.removed == {
        CL("A"), LABEL("A"), RET("A"), SET("A"), TC("A", "R1"), TC("A", "R2"),
    }  # fmt: skip
    assert not any(r.key == "A" for r in inv.stale)
    assert state.members("B") == ("R1", "R2", "R3", "R4")


def test_pinned_case_is_context_not_dependency(project):
    """Editing a case changes the set's cache key but not its input hash."""
    state, _ = project
    h, k = expected_hash(state, SET("A")), cache_key(state, SET("A"))
    state, _ = apply(state, TestCaseEdited(case=TC("A", "R1").key, content=case("R1", title="X")))

    assert expected_hash(state, SET("A")) == h
    assert cache_key(state, SET("A")) != k
    assert state.node(SET("A")).status == Status.FRESH


def test_pinned_case_survives_regeneration(project):
    state, cache = project
    edited = case("R1", title="Elle yazılmış kilitleme testi")
    state, _ = apply(state, TestCaseEdited(case=TC("A", "R1").key, content=edited))
    state, _ = apply(state, RequirementMoved(requirement="R3", to_cluster="A"))
    state = produce_all(state, cache)

    node = state.node(TC("A", "R1"))
    assert node.content == edited
    assert node.origin == Origin.EDITED and node.pinned
    keys = state.node(SET("A")).content.case_keys
    assert keys[0] == TC("A", "R1").key
    assert set(keys) == {TC("A", "R1").key, TC("A", "R2").key, TC("A", "R3").key}


def produce_all_but(state, skip):
    """Produce everything ready except `skip` and what waits on it."""
    for _ in range(20):
        ready = [r for r in analyze(state).ready if r != skip]
        if not ready:
            return state
        for r in ready:
            state = settle(state, r, fake_result(state, r)).state
    raise AssertionError("did not converge")
