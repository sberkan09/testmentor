"""Rules behind the table (docs/tasarim.md, Veri modeli kuralları): pinning, undo through the
cache, cancelling running work, empty clusters, context vs dependency."""

from core.events import (
    ClusterDeleted,
    ClusterRenamed,
    ClustersMerged,
    MethodEdited,
    NodeKept,
    NodePinned,
    NodeUnpinned,
    RequirementMoved,
    RequirementTextChanged,
    TestCaseEdited,
)
from core.graph import cache_key, expected_hash
from core.invalidation import analyze, apply, mark_failed, mark_running, settle
from core.nodes import NodeKind, Origin, Status, ref
from tests.core.helpers import (
    CL,
    LABEL,
    METHOD,
    MX,
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


def test_editing_stale_label_makes_it_fresh(project):
    """An edit is stamped with the current expected hash: no permanent warning."""
    state, _ = project
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    assert analyze(state).llm_calls == 4
    state, inv = apply(state, ClusterRenamed(cluster="B", name="Denetim izi"))

    node = state.node(LABEL("B"))
    assert node.status == Status.FRESH and node.pinned
    assert inv.pinned_warnings == frozenset()
    a = analyze(state)
    assert LABEL("B") not in a.stale
    assert a.llm_calls == 3


def test_editing_stale_method_makes_it_fresh(project):
    state, _ = project
    state, _ = apply(
        state, RequirementTextChanged(requirement="R1", text="Sistem, girişi 5 denemede kilitler.")
    )
    state, _ = apply(state, MethodEdited(requirement="R1", methods=("Test", "Analiz")))

    assert state.node(METHOD("R1")).status == Status.FRESH
    a = analyze(state)
    assert METHOD("R1") not in a.stale
    assert a.llm_calls == 2  # test set, label


def test_keep_mine_clears_warning(project):
    """ "Benimkini koru": content unchanged, new version, fresh."""
    state, _ = project
    state, _ = apply(state, ClusterRenamed(cluster="B", name="Denetim izi"))
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    before = state.node(LABEL("B"))
    state, inv = apply(state, NodeKept(node=LABEL("B")))

    after = state.node(LABEL("B"))
    assert after.status == Status.FRESH
    assert after.content == before.content
    assert after.version == before.version + 1
    assert analyze(state).pinned_warnings == frozenset()
    assert inv.llm_calls == 0


def test_pinned_case_carried_on_merge(project):
    state, cache = project
    edited = case("R1", title="Elle yazılmış kilitleme testi")
    state, _ = apply(state, TestCaseEdited(case=TC("A", "R1").key, content=edited))
    state, inv = apply(state, ClustersMerged(sources=("A", "B"), new_cluster="D"))

    assert inv.carried == {TC("A", "R1"): TC("D", "R1")}
    assert TC("A", "R1") in inv.removed
    node = state.node(TC("D", "R1"))
    assert node.content == edited and node.pinned and node.origin == Origin.EDITED
    state = produce_all(state, cache)
    assert state.node(SET("D")).content.case_keys[0] == TC("D", "R1").key
    assert state.node(TC("D", "R1")).content == edited


def test_pinned_case_carried_on_delete(project):
    state, _ = project
    edited = case("R2", title="Elle yazılmış sıfırlama testi")
    state, _ = apply(state, TestCaseEdited(case=TC("A", "R2").key, content=edited))
    state, inv = apply(state, ClusterDeleted(cluster="A", destinations={"R1": "B", "R2": "C"}))

    assert inv.carried == {TC("A", "R2"): TC("C", "R2")}
    assert state.node(TC("C", "R2")).content == edited


def test_pinned_case_carried_on_last_member_move_with_key_collision(project):
    state, cache = project
    edited = case("R1", title="Elle yazılmış kilitleme testi")
    state, _ = apply(state, TestCaseEdited(case=TC("A", "R1").key, content=edited))
    state, _ = apply(state, RequirementMoved(requirement="R1", to_cluster="B"))
    state = produce_all(state, cache)  # B now has its own generated B:TC-R1
    assert state.get(TC("B", "R1")) is not None
    state, inv = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))

    new = ref(NodeKind.TEST_CASE, "B:A.TC-R1")
    assert inv.carried == {TC("A", "R1"): new}
    assert state.node(new).content == edited and state.node(new).pinned


def test_failed_node_blocks_and_recovers(project):
    state, _ = project
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    state = produce_all_but(state, SET("A"))
    state = mark_failed(state, SET("A"))

    a = analyze(state)
    assert state.node(SET("A")).status == Status.FAILED
    assert a.failed == {SET("A")}
    assert SET("A") not in a.stale and SET("A") not in a.ready
    assert {TC("A", "R1"), MX("R1")} <= a.to_verify
    assert a.llm_calls == 0

    retried = mark_running(state, SET("A"))
    assert retried.node(SET("A")).status == Status.RUNNING

    state, _ = apply(state, RequirementMoved(requirement="R3", to_cluster="A"))
    assert state.node(SET("A")).status == Status.STALE
    assert SET("A") in analyze(state).stale


def test_incremental_state_matches_full_recompute(project):
    """`settle` rehashes only the result's downstream; a state rebuilt from scratch (fresh memo)
    must agree on every expected hash and on the analysis."""
    from core.graph import ProjectState, expected_hash
    from core.nodes import CHILD_KINDS, SOURCE_KINDS

    state, cache = project
    events = [
        RequirementMoved(requirement="R2", to_cluster="B"),
        TestCaseEdited(case=TC("C", "R5").key, content=case("R5", covers=("R5", "R1"))),
        RequirementTextChanged(requirement="R6", text="The system shall support 500 users."),
        ClustersMerged(sources=("A", "C"), new_cluster="D"),
    ]
    for event in events:
        state, _ = apply(state, event)
        for _ in range(20):
            ready = analyze(state).ready
            if not ready:
                break
            for r in ready:
                state = settle(state, r, fake_result(state, r)).state
                rebuilt = ProjectState(
                    project_id=state.project_id,
                    nodes=state.nodes,
                    stage_configs=state.stage_configs,
                )
                derived = [x for x in state.nodes if x.kind not in SOURCE_KINDS | CHILD_KINDS]
                assert {x: expected_hash(state, x) for x in derived} == {
                    x: expected_hash(rebuilt, x) for x in derived
                }
                assert analyze(state) == analyze(rebuilt)
                for x in derived:  # every status agrees with the full-recompute rule
                    n = state.node(x)
                    want = n.content is None or n.input_hash != expected_hash(rebuilt, x)
                    assert (n.status == Status.STALE) == want, x


def test_settle_many_matches_one_by_one(project):
    """A batch reaches the same contents as settling one by one; a stale result is rejected."""
    from core.invalidation import settle_many

    state, _ = project
    state, _ = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    ready = analyze(state).ready
    results = [(r, fake_result(state, r)) for r in ready]

    one_by_one = state
    for r, result in results:
        one_by_one = settle(one_by_one, r, result).state
    out = settle_many(state, results)

    assert out.accepted == set(ready) and out.rejected == frozenset()
    assert {r: n.content for r, n in out.state.nodes.items()} == {
        r: n.content for r, n in one_by_one.nodes.items()
    }
    assert analyze(out.state) == analyze(one_by_one)
    assert out.invalidation.stale == frozenset()  # ready nodes became fresh, nothing new

    stale_result = fake_result(project[0], SET("A"))  # made before the move
    again = settle_many(out.state, [(SET("A"), stale_result)])
    assert again.rejected == {SET("A")} and again.state is out.state
