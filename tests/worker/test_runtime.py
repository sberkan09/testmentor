"""Orchestrator behaviour on the memory store (docs/tasarim.md, İş kuyruğu, Aşama kapıları, Çok
kullanıcılı çalışma, API kuralları): events, debounce, cancellation, cache-only results, gates,
versions, locks, undo, merge and delete, failures, restart."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable

import pytest

from core.invalidation import analyze
from core.llm import LLMRequest
from core.nodes import PROJECT_CARD_KEY, NodeKind, Status, TestCaseContent
from services.fake_llm import FakeComplete
from tests.worker import helpers
from tests.worker.helpers import FAST, Clock, calls, hashes, produced, project, ref, service
from worker.contracts import (
    ApproveStage,
    CommandRequest,
    CreateCluster,
    DeleteCluster,
    EditMethod,
    EditProjectCard,
    EditRequirement,
    EditTestCase,
    Focus,
    MergeClusters,
    MoveRequirement,
    Pin,
    Regenerate,
    RenameCluster,
    SetGranularity,
    SetStageMode,
    Undo,
    Unpin,
)
from worker.store import MemoryProjectStore

SET = NodeKind.TEST_SET
LABEL = NodeKind.CLUSTER_LABEL
METHOD = NodeKind.METHOD


def cmd(command, **versions: int) -> CommandRequest:
    return CommandRequest(command=command, expected_versions=versions)


async def until(cond: Callable[[], bool], limit_s: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + limit_s
    while not cond():
        if loop.time() > end:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.005)


def schemas(requests: list[LLMRequest]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in requests:
        out[r.schema.__name__] = out.get(r.schema.__name__, 0) + 1
    return out


# Events -----------------------------------------------------------------------------------------


async def test_command_events_are_numbered_and_replayable():
    svc = service()
    await produced(svc)
    seq0 = svc.snapshot("P").seq
    sub = svc.subscribe("P")
    result = await svc.command("P", cmd(RenameCluster(cluster="A", name="Giriş")), "ayse")
    assert result.accepted
    events = svc.events_after("P", seq0)
    assert [e.seq for e in events] == list(range(seq0 + 1, result.seq + 1))
    assert events[-1].type == "command_applied"
    assert events[-1].payload["result"]["seq"] == result.seq
    assert events[-1].actor == "ayse"
    updated = [e for e in events if e.type == "node_updated"]
    assert updated[0].payload["node"]["ref"] == {"kind": "cluster_label", "key": "A"}
    assert updated[0].payload["node"]["content"]["name"] == "Giriş"
    live = [await asyncio.wait_for(sub.__anext__(), 1) for _ in events]
    assert live == events
    await sub.aclose()
    assert svc.events_after("P", result.seq) == []


async def test_old_events_need_a_snapshot():
    svc = service(orchestrator=FAST.model_copy(update={"event_buffer": 5}))
    await produced(svc)
    assert svc.events_after("P", 0) is None
    seq = svc.snapshot("P").seq
    assert svc.events_after("P", seq - 3) is not None


async def test_rejected_command_is_published_with_its_reason():
    svc = service()
    await produced(svc)
    result = await svc.command("P", cmd(MoveRequirement(requirement="R9", to_cluster="A")), "ayse")
    assert not result.accepted and result.reason.startswith("invalid")
    last = svc.events_after("P", result.seq - 1)[-1]
    assert last.type == "command_rejected" and last.payload["result"]["seq"] == result.seq


# Queue integration ------------------------------------------------------------------------------


async def test_edits_inside_the_debounce_become_one_job():
    complete = FakeComplete()
    svc = service(complete=complete, orchestrator=FAST.model_copy(update={"debounce_s": 0.15}))
    await produced(svc)
    n0 = len(complete.requests)
    for text in ("Sistem, girişi kilitler.", "Sistem, girişi 15 dakika kilitler."):
        assert (
            await svc.command("P", cmd(EditRequirement(requirement="R1", text=text)), "a")
        ).accepted
        await asyncio.sleep(0.03)
    await svc.wait_idle()
    new = complete.requests[n0:]
    assert schemas(new) == {"MethodBatch": 1, "ClusterLabel": 1, "TestCaseDelta": 1}
    assert "15 dakika kilitler" in new[0].messages[-1]["content"]


async def test_focus_and_regenerate_raise_priority_user_work_is_p1():
    svc = service(orchestrator=FAST.model_copy(update={"debounce_s": 30}))
    await produced(svc)
    await svc.command("P", cmd(MoveRequirement(requirement="R2", to_cluster="B")), "a")
    jobs = {(j.node.kind, j.node.key): j for j in svc.snapshot("P").jobs}
    assert jobs[(LABEL, "A")].priority == "P1" and jobs[(LABEL, "A")].state == "queued"
    await svc.command("P", cmd(Focus(nodes=(ref(LABEL, "B"),))), "a")
    jobs = {(j.node.kind, j.node.key): j for j in svc.snapshot("P").jobs}
    assert jobs[(LABEL, "B")].priority == "P0"
    assert jobs[(LABEL, "A")].priority == "P1"
    await svc.close()


async def test_running_job_is_cancelled_when_its_input_changes():
    complete = FakeComplete()
    svc = service(complete=complete)
    await produced(svc)
    complete.delay_s = 0.3
    await svc.command("P", cmd(RenameCluster(cluster="C", name="Performans")), "a")
    await svc.command(
        "P", cmd(EditRequirement(requirement="R3", text="The system logs changes.")), "a"
    )
    rt = svc.runtime("P")
    await until(lambda: rt.state.node(ref(SET, "B")).status == Status.RUNNING)
    seq = rt.last_seq
    await svc.command("P", cmd(EditRequirement(requirement="R4", text="Export the log.")), "a")
    assert rt.state.node(ref(SET, "B")).status == Status.STALE
    await svc.wait_idle()
    events = svc.events_after("P", seq)
    assert any(e.type == "job_done" and e.payload.get("cancelled") for e in events)
    jobs = svc.store.jobs("P")
    assert any(j.state == "cancelled" and j.stage == SET for j in jobs)
    state = rt.state
    assert not analyze(state).stale
    assert state.node(ref(LABEL, "C")).content.name == "Performans"


async def test_result_of_a_changed_batch_member_only_reaches_the_cache():
    complete = FakeComplete()
    svc = service(complete=complete)
    await produced(svc)
    complete.delay_s = 0.3
    rt = svc.runtime("P")
    await svc.command("P", cmd(EditRequirement(requirement="R1", text="Giriş kilitlenir.")), "a")
    await svc.command("P", cmd(EditRequirement(requirement="R3", text="Changes are logged.")), "a")
    await until(lambda: rt.state.node(ref(METHOD, "R3")).status == Status.RUNNING)
    assert rt.state.node(ref(METHOD, "R1")).status == Status.RUNNING  # one batch
    await svc.command(
        "P", cmd(EditRequirement(requirement="R3", text="All changes are logged.")), "a"
    )
    await svc.wait_idle()
    batches = [r for r in complete.requests if r.schema.__name__ == "MethodBatch"]
    assert "Giriş kilitlenir." in batches[-2].messages[-1]["content"]
    assert "All changes are logged." in batches[-1].messages[-1]["content"]
    assert not analyze(rt.state).stale

    # The rejected result for "Changes are logged." was cached: undoing the last edit brings it
    # back without a classification call.
    n = len(complete.requests)
    assert (await svc.command("P", cmd(Undo()), "a")).accepted
    await svc.wait_idle()
    assert "MethodBatch" not in schemas(complete.requests[n:])
    assert rt.state.requirement("R3").text == "Changes are logged."


async def test_failed_node_waits_for_regenerate():
    class Flaky(FakeComplete):
        fail = True

        def reply(self, req):
            if self.fail and req.unit.startswith("C/label"):
                return {"name": ""}  # schema error, twice
            return super().reply(req)

    complete = Flaky()
    svc = service(complete=complete)
    await svc.add_project(project(), "P")
    await svc.wait_idle()
    rt = svc.runtime("P")
    assert rt.state.node(ref(LABEL, "C")).status == Status.FAILED
    assert any(j.state == "failed" for j in svc.store.jobs("P"))
    complete.fail = False
    result = await svc.command("P", cmd(Regenerate(node=ref(LABEL, "C"))), "a")
    assert result.accepted
    await svc.wait_idle()
    assert rt.state.node(ref(LABEL, "C")).status == Status.FRESH
    bad = await svc.command("P", cmd(Regenerate(node=ref(LABEL, "C"))), "a")
    assert not bad.accepted  # fresh: nothing to produce


# Stage gates ------------------------------------------------------------------------------------


async def test_approval_mode_holds_the_stage_until_approved():
    complete = FakeComplete()
    svc = service(complete=complete)
    await produced(svc)
    await svc.command("P", cmd(SetStageMode(stage=SET, mode="approval")), "lead")
    seq = svc.snapshot("P").seq
    n0 = len(complete.requests)
    await svc.command("P", cmd(MoveRequirement(requirement="R2", to_cluster="B")), "a")
    await svc.wait_idle()
    assert calls(complete.requests[n0:]) == {
        ("ClusterLabel", "A/label"): 1,
        ("ClusterLabel", "B/label"): 1,
    }
    snap = svc.snapshot("P")
    stage = next(s for s in snap.stages if s.stage == SET)
    assert stage.mode == "approval" and stage.waiting_approval and stage.stale == 2
    assert {(j.node.key, j.state) for j in snap.jobs} == {
        ("A", "waiting_approval"),
        ("B", "waiting_approval"),
    }
    waits = [e for e in svc.events_after("P", seq) if e.type == "stage_waiting_approval"]
    assert [e.payload["stage"] for e in waits] == [
        "test_set"
    ]  # once, when the stage starts waiting

    await svc.command("P", cmd(ApproveStage(stage=SET)), "lead")
    await svc.wait_idle()
    assert calls(complete.requests[n0:])[("TestCaseDelta", "B/incremental")] == 1
    assert not analyze(svc.runtime("P").state).stale


async def test_project_card_change_waits_for_approval_in_auto_mode():
    complete = FakeComplete()
    svc = service(complete=complete)
    await produced(svc)
    n0 = len(complete.requests)
    result = await svc.command("P", cmd(EditProjectCard(text="Project: Yeni portal (P)")), "lead")
    assert result.accepted
    await svc.wait_idle()
    assert complete.requests[n0:] == []
    snap = svc.snapshot("P")
    waiting = {s.stage for s in snap.stages if s.waiting_approval}
    assert waiting == {METHOD, LABEL}  # sets wait behind their methods
    for stage in (METHOD, LABEL, SET):
        await svc.command("P", cmd(ApproveStage(stage=stage)), "lead")
        await svc.wait_idle()
    assert schemas(complete.requests[n0:]) == {
        "MethodBatch": 1,
        "ClusterLabel": 3,
        "TestCaseSet": 3,
    }
    assert not analyze(svc.runtime("P").state).stale


# Multiple users ---------------------------------------------------------------------------------


async def test_stale_version_is_rejected_with_current_versions():
    svc = service()
    state = await produced(svc)
    key = state.test_cases("A")[0].key
    node = state.node(ref(NodeKind.TEST_CASE, key))
    content = node.content.model_copy(update={"title": "Ayşe'nin başlığı"})
    v = {f"test_case:{key}": node.version}
    first = await svc.command("P", cmd(EditTestCase(case=key, content=content), **v), "ayse")
    assert first.accepted
    other = content.model_copy(update={"title": "Mehmet'in başlığı"})
    second = await svc.command("P", cmd(EditTestCase(case=key, content=other), **v), "mehmet")
    assert not second.accepted and second.reason == "version_conflict"
    assert second.current_versions == {f"test_case:{key}": node.version + 1}
    current = svc.runtime("P").state.node(ref(NodeKind.TEST_CASE, key))
    assert current.content.title == "Ayşe'nin başlığı"


async def test_edit_lock_rejects_other_users_until_it_expires():
    clock = Clock()
    svc = service(clock=clock)
    await produced(svc)
    r1 = ref(NodeKind.REQUIREMENT, "R1")
    assert svc.lock("P", r1, "ayse")
    assert svc.lock("P", r1, "ayse")  # refresh
    assert not svc.lock("P", r1, "mehmet")
    assert svc.snapshot("P").locks == {"requirement:R1": "ayse"}
    edit = EditRequirement(requirement="R1", text="Mehmet'in metni.")
    blocked = await svc.command("P", cmd(edit), "mehmet")
    assert not blocked.accepted and blocked.reason.startswith("locked")
    moved = await svc.command("P", cmd(MoveRequirement(requirement="R1", to_cluster="B")), "mehmet")
    assert moved.accepted  # moving needs no lock
    clock.now += 61
    assert svc.snapshot("P").locks == {}
    assert (await svc.command("P", cmd(edit), "mehmet")).accepted
    changes = [e.payload for e in svc.events_after("P", 0) or [] if e.type == "lock_changed"]
    assert changes in ([], [{"ref": "requirement:R1", "user": "ayse"}])  # [] if out of buffer
    await svc.close()


# Undo -------------------------------------------------------------------------------------------


async def test_undo_of_edits_restores_without_model_calls():
    complete = FakeComplete()
    svc = service(complete=complete)
    before = await produced(svc)
    h0 = hashes(before)
    key = before.test_cases("B")[0].key
    case: TestCaseContent = before.node(ref(NodeKind.TEST_CASE, key)).content
    n0 = len(complete.requests)
    edits = [
        EditTestCase(case=key, content=case.model_copy(update={"title": "Düzenlendi"})),
        RenameCluster(cluster="A", name="Kimlik doğrulama"),
        EditMethod(requirement="R5", methods=("Analiz",)),
        Pin(node=ref(LABEL, "C")),
    ]
    for e in edits:
        assert (await svc.command("P", cmd(e), "ayse")).accepted
    await svc.wait_idle()
    assert schemas(complete.requests[n0:]) == {"TestCaseDelta": 1}  # C's set, R5 left the tests
    for _ in edits:
        assert (await svc.command("P", cmd(Undo()), "ayse")).accepted
        await svc.wait_idle()
    assert schemas(complete.requests[n0:]) == {"TestCaseDelta": 1}
    after = svc.runtime("P").state
    assert hashes(after) == h0
    assert not any(n.pinned for n in after.nodes.values())
    nothing = await svc.command("P", cmd(Undo()), "ayse")
    assert nothing.reason == "nothing_to_undo"


async def test_undo_is_refused_after_another_user_changed_the_same_nodes():
    svc = service()
    await produced(svc)
    await svc.command("P", cmd(MoveRequirement(requirement="R2", to_cluster="B")), "ayse")
    await svc.command("P", cmd(MoveRequirement(requirement="R2", to_cluster="C")), "mehmet")
    result = await svc.command("P", cmd(Undo()), "ayse")
    assert not result.accepted and result.reason == "version_conflict"
    assert set(result.current_versions) == {"cluster:A", "cluster:B"}
    # The refused entry left Ayşe's stack (review finding 7): nothing older to undo here.
    assert svc.runtime("P").record.undo["ayse"] == []
    assert (await svc.command("P", cmd(Undo()), "mehmet")).accepted
    assert (await svc.command("P", cmd(Undo()), "ayse")).reason == "nothing_to_undo"
    await svc.wait_idle()
    state = svc.runtime("P").state
    assert state.members("A") == ("R1",) and state.members("B") == ("R2", "R3", "R4")


async def test_undo_is_accepted_when_the_other_user_undid_first():
    svc = service()
    await produced(svc)
    await svc.command("P", cmd(MoveRequirement(requirement="R2", to_cluster="B")), "ayse")
    await svc.command("P", cmd(MoveRequirement(requirement="R2", to_cluster="C")), "mehmet")
    assert (await svc.command("P", cmd(Undo()), "mehmet")).accepted
    assert (await svc.command("P", cmd(Undo()), "ayse")).accepted  # same content again
    await svc.wait_idle()
    state = svc.runtime("P").state
    assert state.members("A") == ("R1", "R2") and state.members("C") == ("R5", "R6")


async def test_refused_undo_entry_is_dropped_so_older_commands_can_be_undone():
    """Review finding 7: an undo refused with `version_conflict` drops its entry."""
    svc = service()
    await produced(svc)
    rt = svc.runtime("P")
    await svc.command("P", cmd(RenameCluster(cluster="A", name="Giriş")), "ayse")
    await svc.command("P", cmd(MoveRequirement(requirement="R2", to_cluster="B")), "ayse")
    await svc.command("P", cmd(MoveRequirement(requirement="R4", to_cluster="C")), "mehmet")
    refused = await svc.command("P", cmd(Undo()), "ayse")  # B changed by Mehmet since
    assert not refused.accepted and refused.reason == "version_conflict"
    assert [e.command for e in rt.record.undo["ayse"]] == ["rename_cluster"]
    assert svc.store.get_project("P").undo["ayse"] == rt.record.undo["ayse"]  # persisted
    assert (await svc.command("P", cmd(Undo()), "ayse")).accepted  # the rename
    assert not rt.state.node(ref(LABEL, "A")).pinned
    assert rt.state.members("B") == ("R2", "R3")  # the move stays
    assert (await svc.command("P", cmd(Undo()), "ayse")).reason == "nothing_to_undo"
    await svc.wait_idle()
    assert rt.state.node(ref(LABEL, "A")).origin.value == "generated"
    await svc.close()


async def test_undo_of_other_users_commands_is_independent():
    svc = service()
    await produced(svc)
    await svc.command("P", cmd(RenameCluster(cluster="A", name="Ayşe")), "ayse")
    await svc.command("P", cmd(RenameCluster(cluster="B", name="Mehmet")), "mehmet")
    assert (await svc.command("P", cmd(Undo()), "ayse")).accepted
    state = svc.runtime("P").state
    assert state.node(ref(LABEL, "A")).origin.value == "generated"
    assert state.node(ref(LABEL, "B")).content.name == "Mehmet"


# Cluster commands -------------------------------------------------------------------------------


async def test_merge_uses_one_merge_call_and_one_label():
    complete = FakeComplete()
    svc = service(complete=complete)
    await produced(svc)
    n0 = len(complete.requests)
    result = await svc.command("P", cmd(MergeClusters(sources=("A", "B"))), "a")
    assert result.accepted
    await svc.wait_idle()
    assert calls(complete.requests[n0:]) == {
        ("MergeDecision", "C001/merge"): 1,
        ("ClusterLabel", "C001/label"): 1,
    }
    state = svc.runtime("P").state
    assert state.members("C001") == ("R1", "R2", "R3", "R4")
    covered = {r for c in state.test_cases("C001") for r in state.node(c).content.covers}
    assert covered == {"R1", "R2", "R3", "R4"}
    n1 = len(complete.requests)
    assert (await svc.command("P", cmd(Undo()), "a")).accepted
    await svc.wait_idle()
    assert complete.requests[n1:] == []
    assert svc.runtime("P").state.keys_of(NodeKind.CLUSTER) == ("A", "B", "C")


async def test_delete_and_create_cluster():
    complete = FakeComplete()
    svc = service(complete=complete)
    await produced(svc)
    n0 = len(complete.requests)
    dest = {"R5": "A", "R6": "B"}
    assert (
        await svc.command("P", cmd(DeleteCluster(cluster="C", destinations=dest)), "a")
    ).accepted
    await svc.wait_idle()
    assert calls(complete.requests[n0:]) == {
        ("TestCaseDelta", "A/incremental"): 1,
        ("TestCaseDelta", "B/incremental"): 1,
        ("ClusterLabel", "A/label"): 1,
        ("ClusterLabel", "B/label"): 1,
    }
    created = await svc.command("P", cmd(CreateCluster(members=("R5", "R6"))), "a")
    assert created.accepted
    await svc.wait_idle()
    state = svc.runtime("P").state
    assert state.members("C001") == ("R5", "R6")
    assert not analyze(state).stale


async def test_set_granularity_recuts_and_keeps_moved_requirements():
    svc = service()
    await produced(svc)
    await svc.command("P", cmd(MoveRequirement(requirement="R2", to_cluster="B")), "a")
    result = await svc.command("P", cmd(SetGranularity(distance_threshold=1.99)), "a")
    assert result.accepted, result
    await svc.wait_idle()
    state = svc.runtime("P").state
    assert state.cluster_of("R2") == "B"
    assert sorted(m for c in state.keys_of(NodeKind.CLUSTER) for m in state.members(c)) == [
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
        "R6",
    ]
    assert not analyze(state).stale


# Restart ----------------------------------------------------------------------------------------


async def test_restart_loads_the_same_state():
    store = MemoryProjectStore()
    svc = service(store)
    await produced(svc)
    await svc.command("P", cmd(MoveRequirement(requirement="R2", to_cluster="B")), "ayse")
    await svc.wait_idle()
    before = svc.runtime("P").state
    seq = svc.snapshot("P").seq
    await svc.close()

    again = service(store)
    await again.start()
    await again.wait_idle()
    state = again.runtime("P").state
    assert state.nodes == before.nodes
    assert not analyze(state).stale
    assert again.snapshot("P").seq == seq
    assert again.events_after("P", seq - 1) is None  # older events need a snapshot
    assert again.projects() == [("P", "Örnek portal")]
    assert (await again.command("P", cmd(Undo()), "ayse")).accepted  # undo stack persisted


@pytest.mark.parametrize("bad", ["", "cluster_label"])
async def test_bad_expected_version_key_is_invalid(bad):
    svc = service()
    await produced(svc)
    result = await svc.command("P", CommandRequest(command=Undo(), expected_versions={bad: 1}), "a")
    assert not result.accepted and result.reason.startswith("invalid")


async def test_changed_stage_config_on_restart_waits_for_approval():
    store = MemoryProjectStore()
    svc = service(store)
    await produced(svc)
    await svc.close()

    configs = dict(helpers.CONFIGS)
    configs[LABEL] = configs[LABEL].model_copy(update={"prompt_version": "new-label-prompt"})
    complete = FakeComplete()
    again = service(store, complete=complete)
    again.deps = dataclasses.replace(again.deps, stage_configs=configs)
    await again.start()
    await again.wait_idle()
    assert complete.requests == []
    snap = again.snapshot("P")
    label_stage = next(s for s in snap.stages if s.stage == LABEL)
    assert label_stage.stale == 3 and label_stage.waiting_approval
    assert store.get_project("P").stage_configs[LABEL].prompt_version == "new-label-prompt"
    assert [e.event.type for e in store.events("P")] == ["stage_config_changed"]
    await again.command("P", cmd(ApproveStage(stage=LABEL)), "lead")
    await again.wait_idle()
    assert schemas(complete.requests) == {"ClusterLabel": 3}
    assert not analyze(again.runtime("P").state).stale


async def test_undo_of_a_card_edit_stays_gated():
    complete = FakeComplete()
    svc = service(complete=complete)
    await produced(svc)
    await svc.command("P", cmd(EditProjectCard(text="Project: Yeni (P)")), "lead")
    await svc.command("P", cmd(EditProjectCard(text="Project: Daha yeni (P)")), "lead")
    n0 = len(complete.requests)
    assert (await svc.command("P", cmd(Undo()), "lead")).accepted  # back to a never-produced card
    await svc.wait_idle()
    assert complete.requests[n0:] == []
    assert any(s.waiting_approval for s in svc.snapshot("P").stages)


async def test_kb_document_added_rechecks_retrievals_with_early_cutoff():
    complete = FakeComplete()
    svc = service(complete=complete)
    before = await produced(svc)
    n0 = len(complete.requests)
    svc.kb_document_added("P", "doc-1", "v2", actor="ayse")
    await svc.wait_idle()
    state = svc.runtime("P").state
    assert complete.requests[n0:] == []  # passages unchanged: sets stay fresh
    assert not analyze(state).stale
    assert state.node(ref(NodeKind.KB_INDEX, "index")).content.version == "v2"
    assert state.node(ref(SET, "A")) == before.node(ref(SET, "A"))


async def test_snapshot_job_ids_are_unique():
    complete = FakeComplete(delay_s=0.2)
    svc = service(complete=complete)
    await svc.add_project(project(), "P")
    await until(lambda: any(j.state == "running" for j in svc.snapshot("P").jobs))
    for _ in range(20):
        ids = [j.id for j in svc.snapshot("P").jobs]
        assert len(ids) == len(set(ids))
        await asyncio.sleep(0.02)
    await svc.wait_idle()
    assert svc.runtime("P").idle()


# Review fixes: gates, pins, events ---------------------------------------------------------------


@pytest.mark.parametrize("back", ["undo", "edit"])
async def test_card_edit_taken_back_leaves_no_gate_behind(back):
    """Review finding 2: nodes that return to fresh by the normal rule leave `needs_approval`;
    a later move runs without approval (one incremental test call and two names)."""
    complete = FakeComplete()
    svc = service(complete=complete)
    before = await produced(svc)
    card = before.node(ref(NodeKind.PROJECT_CARD, PROJECT_CARD_KEY)).content
    await svc.command("P", cmd(EditProjectCard(text="Project: Yeni portal (P)")), "lead")
    await svc.wait_idle()
    rt = svc.runtime("P")
    assert rt.record.needs_approval
    back_cmd = Undo() if back == "undo" else EditProjectCard(text=card.text, methods=card.methods)
    assert (await svc.command("P", cmd(back_cmd), "lead")).accepted
    await svc.wait_idle()
    assert rt.record.needs_approval == [] and not analyze(rt.state).stale
    n0 = len(complete.requests)
    await svc.command("P", cmd(MoveRequirement(requirement="R2", to_cluster="B")), "a")
    await svc.wait_idle()
    assert calls(complete.requests[n0:]) == {
        ("TestCaseDelta", "B/incremental"): 1,
        ("ClusterLabel", "A/label"): 1,
        ("ClusterLabel", "B/label"): 1,
    }
    snap = svc.snapshot("P")
    assert not any(j.state == "waiting_approval" for j in snap.jobs)
    assert not any(s.waiting_approval for s in snap.stages)
    await svc.close()


async def test_approval_of_a_node_that_returned_to_fresh_does_not_carry_over():
    """Review finding 3: approve, undo at once (the set is fresh again), edit again: the set
    waits for a new approval."""
    complete = FakeComplete()
    svc = service(complete=complete)
    await produced(svc)
    rt = svc.runtime("P")
    await svc.command("P", cmd(SetStageMode(stage=SET, mode="approval")), "lead")
    text = rt.state.requirement("R5").text
    await svc.command("P", cmd(EditRequirement(requirement="R5", text=text + " Ek.")), "a")
    await svc.wait_idle()
    assert ("C", "waiting_approval") in {(j.node.key, j.state) for j in svc.snapshot("P").jobs}
    await svc.command("P", cmd(ApproveStage(stage=SET)), "lead")
    assert (await svc.command("P", cmd(Undo()), "a")).accepted  # before the job starts
    assert rt.record.approved == []
    await svc.wait_idle()
    n0 = len(complete.requests)
    await svc.command("P", cmd(EditRequirement(requirement="R5", text=text + " Başka.")), "a")
    await svc.wait_idle()
    assert ("TestCaseDelta", "C/incremental") not in calls(complete.requests[n0:])
    jobs = {(j.node.kind, j.node.key): j.state for j in svc.snapshot("P").jobs}
    assert jobs == {(SET, "C"): "waiting_approval"}
    await svc.close()


async def test_pin_of_a_pinned_node_is_refused_and_leaves_the_undo_stack_alone():
    """Review finding 4: an idle pin/unpin is `invalid` and pushes no undo entry, so undo
    takes back the edit (which pinned the case) without a version conflict."""
    svc = service()
    state = await produced(svc)
    rt = svc.runtime("P")
    key = state.test_cases("B")[0].key
    case_ref = ref(NodeKind.TEST_CASE, key)
    original = state.node(case_ref)
    edited = original.content.model_copy(update={"title": "Düzenlendi"})
    assert (await svc.command("P", cmd(EditTestCase(case=key, content=edited)), "ayse")).accepted
    assert rt.state.node(case_ref).pinned
    pin = await svc.command("P", cmd(Pin(node=case_ref)), "ayse")
    assert not pin.accepted and pin.reason.startswith("invalid: already pinned")
    unpin = await svc.command("P", cmd(Unpin(node=ref(LABEL, "A"))), "ayse")
    assert not unpin.accepted and unpin.reason.startswith("invalid: already unpinned")
    assert [e.command for e in rt.record.undo["ayse"]] == ["edit_test_case"]
    undone = await svc.command("P", cmd(Undo()), "ayse")
    assert undone.accepted, undone.reason
    node = rt.state.node(case_ref)
    assert node.content == original.content and not node.pinned
    await svc.close()


async def test_events_after_a_future_seq_need_a_snapshot():
    """Review finding 8: a client ahead of the server (e.g. after a restart with a lost tail)
    must not silently miss events."""
    svc = service()
    await produced(svc)
    last = svc.snapshot("P").seq
    assert svc.events_after("P", last) == []
    assert svc.events_after("P", last + 50) is None
    await svc.close()
