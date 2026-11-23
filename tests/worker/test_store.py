"""Orchestrator stores (paket 5): project and job records, transactions, and the orchestrator on
Postgres: the done scenario, and a restarted process loading the project in the same state.

The Postgres cases need a server (tests/pg.py); `make pg-test` runs them with skip reasons."""

from __future__ import annotations

import pytest

from core.events import RequirementMoved
from core.invalidation import Hint, analyze
from core.nodes import ClusterLabelContent, Node, NodeKind, NodeRef, StageConfig
from services.fake_llm import FakeComplete
from tests.worker.helpers import calls, hashes, produced, ref, service
from worker.contracts import CommandRequest, MoveRequirement, Undo
from worker.store import JobRecord, MemoryProjectStore, ProjectRecord, UndoEntry, UndoStep


@pytest.fixture(params=["memory", "postgres"])
def store(request):
    if request.param == "memory":
        return MemoryProjectStore()
    return request.getfixturevalue("pg_store")


def record() -> ProjectRecord:
    set_a = NodeRef(kind=NodeKind.TEST_SET, key="A")
    return ProjectRecord(
        project_id="P",
        name="Örnek",
        stage_configs={NodeKind.TEST_SET: StageConfig(prompt_version="t1", params={"x": 0.5})},
        stage_modes={NodeKind.TEST_SET: "approval"},
        needs_approval=[set_a],
        hints={str(set_a): Hint(mode="merge", sources=(NodeRef(kind=NodeKind.TEST_SET, key="B"),))},
        undo={
            "ayse": [
                UndoEntry(
                    command="move_requirement",
                    expected={"cluster:A": 2},
                    contents={"cluster:A": None},
                    steps=(
                        UndoStep(clusters={"A": ("R1", "R2")}, pinned={"A": ()}),
                        UndoStep(event=RequirementMoved(requirement="R2", to_cluster="A")),
                    ),
                )
            ]
        },
        last_seq=42,
        cluster_counter=3,
    )


def test_project_record_round_trip(store):
    rec = record()
    store.save_project(rec)
    assert store.get_project("P") == rec
    rec.last_seq = 43
    store.save_project(rec)
    assert store.get_project("P").last_seq == 43
    assert [r.project_id for r in store.list_projects()] == ["P"]
    assert store.get_project("Q") is None


def test_job_record_round_trip(store):
    job = JobRecord(
        job_id="P-x-j1",
        stage=NodeKind.TEST_SET,
        nodes=[NodeRef(kind=NodeKind.TEST_SET, key="A")],
        priority="P1",
        state="running",
        started_at=1.5,
    )
    store.put_job("P", job)
    done = job.model_copy(update={"state": "done", "finished_at": 2.5, "calls": 1})
    store.put_job("P", done)
    assert store.jobs("P") == [done]
    assert store.jobs("Q") == []


def test_transaction_rolls_back_together(pg_store):
    lbl = NodeRef(kind=NodeKind.CLUSTER_LABEL, key="A")
    node = Node(ref=lbl, content=ClusterLabelContent(name="Ad"), input_hash="h", version=1)
    with pytest.raises(RuntimeError), pg_store.transaction():
        pg_store.put_node("P", node, expected_version=0)
        pg_store.save_project(record())
        raise RuntimeError("boom")
    assert pg_store.get_node("P", lbl) is None
    assert pg_store.history("P", lbl) == []
    assert pg_store.get_project("P") is None


async def test_move_scenario_on_postgres(pg_store):
    complete = FakeComplete()
    svc = service(pg_store, complete=complete)
    before = await produced(svc)
    n0 = len(complete.requests)
    move = CommandRequest(command=MoveRequirement(requirement="R2", to_cluster="B"))
    assert (await svc.command("P", move, "ayse")).accepted
    await svc.wait_idle()
    assert calls(complete.requests[n0:]) == {
        ("TestCaseDelta", "B/incremental"): 1,
        ("ClusterLabel", "A/label"): 1,
        ("ClusterLabel", "B/label"): 1,
    }
    n1 = len(complete.requests)
    assert (await svc.command("P", CommandRequest(command=Undo()), "ayse")).accepted
    await svc.wait_idle()
    assert complete.requests[n1:] == []
    assert hashes(svc.runtime("P").state) == hashes(before)
    log = pg_store.events("P")
    assert [(e.actor, e.event.type) for e in log] == [
        ("ayse", "requirement_moved"),
        ("ayse", "membership_changed"),
    ]
    await svc.close()


async def test_restarted_process_loads_the_same_state(pg_store, pg_dsn):
    from worker.store_pg import PostgresStore

    complete = FakeComplete()
    svc = service(pg_store, complete=complete)
    await produced(svc)
    move = CommandRequest(command=MoveRequirement(requirement="R2", to_cluster="B"))
    await svc.command("P", move, "ayse")
    await svc.wait_idle()
    before = svc.runtime("P").state
    seq = svc.snapshot("P").seq
    await svc.close()

    store2 = PostgresStore.connect(pg_dsn)  # a new process: nothing shared but the database
    complete2 = FakeComplete()
    again = service(store2, complete=complete2)
    await again.start()
    await again.wait_idle()
    state = again.runtime("P").state
    assert state.nodes == before.nodes
    assert not analyze(state).stale
    assert again.snapshot("P").seq == seq
    assert complete2.requests == []
    assert (await again.command("P", CommandRequest(command=Undo()), "ayse")).accepted
    await again.wait_idle()
    assert complete2.requests == []  # undo after the restart still comes from the cache
    assert again.runtime("P").state.members("A") == ("R1", "R2")
    assert len({j.job_id for j in store2.jobs("P")}) == len(store2.jobs("P"))
    await again.close()
    store2.close()


async def test_running_nodes_are_released_on_load(pg_store):
    svc = service(pg_store)
    state = await produced(svc)
    await svc.close()
    label = ref(NodeKind.CLUSTER_LABEL, "A")
    pg_store.set_status("P", label, state.node(label).status.__class__("running"))
    again = service(pg_store)
    await again.start()
    assert again.runtime("P").state.node(label).status.value == "fresh"
    assert pg_store.get_node("P", label).status.value == "fresh"
    await again.close()
