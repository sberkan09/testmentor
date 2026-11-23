"""Store failures in the middle of the work (review finding 6): memory changes only after a
successful commit, a job whose commit fails releases its nodes and is retried, a lasting
failure ends in `failed` instead of endless model calls."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from core.invalidation import analyze
from core.nodes import NodeKind, Status
from services.fake_llm import FakeComplete
from tests.worker.helpers import FAST, calls, produced, ref, service
from worker.contracts import (
    ApproveStage,
    CommandRequest,
    CreateCluster,
    EditRequirement,
    MoveRequirement,
    SetStageMode,
)
from worker.store import JobRecord, MemoryProjectStore

LABEL = NodeKind.CLUSTER_LABEL
SET = NodeKind.TEST_SET


class FailingStore(MemoryProjectStore):
    """Raises `ConnectionError` from `put_job` / `save_project` while armed."""

    def __init__(self) -> None:
        super().__init__()
        self.job_fails: Callable[[JobRecord], bool] = lambda job: False
        self.times = 0
        self.save_fails = 0

    def put_job(self, project_id: str, job: JobRecord) -> None:
        if self.times and self.job_fails(job):
            self.times -= 1
            raise ConnectionError("database connection lost (simulated)")
        super().put_job(project_id, job)

    def save_project(self, record) -> None:
        if self.save_fails:
            self.save_fails -= 1
            raise ConnectionError("database connection lost (simulated)")
        super().save_project(record)


def label_a_job(state: str) -> Callable[[JobRecord], bool]:
    return lambda job: job.state == state and ref(LABEL, "A") in job.nodes


def running_nodes(svc) -> list[str]:
    return sorted(
        str(r) for r, n in svc.runtime("P").state.nodes.items() if n.status.value == "running"
    )


def assert_store_mirrors_memory(svc) -> None:
    rt = svc.runtime("P")
    stored = svc.store.load("P")
    for r, node in rt.state.nodes.items():
        if node.version:
            assert stored[r].version == node.version, r
            assert stored[r].status == node.status, r


@pytest.mark.parametrize("state", ["running", "done"])
async def test_one_failed_job_commit_is_retried_and_leaves_nothing_running(state):
    store = FailingStore()
    complete = FakeComplete()
    svc = service(store, complete=complete)
    await produced(svc)
    n0 = len(complete.requests)
    old_jobs = {j.job_id for j in store.jobs("P")}
    store.job_fails, store.times = label_a_job(state), 1
    await svc.command(
        "P", CommandRequest(command=MoveRequirement(requirement="R2", to_cluster="B")), "a"
    )
    await asyncio.wait_for(svc.wait_idle(), 5)
    rt = svc.runtime("P")
    assert store.times == 0  # the failure happened
    assert running_nodes(svc) == [] and not rt._jobs and rt.idle()
    assert not analyze(rt.state).stale and not analyze(rt.state).failed
    assert rt.state.node(ref(LABEL, "A")).status == Status.FRESH
    new_jobs = [j for j in store.jobs("P") if j.job_id not in old_jobs]
    done = [j for j in new_jobs if ref(LABEL, "A") in j.nodes and j.state == "done"]
    assert len(done) == 1
    # A failed start costs no call; a failed end costs one more call for A.
    assert calls(complete.requests[n0:])[("ClusterLabel", "A/label")] == (
        2 if state == "done" else 1
    )
    assert_store_mirrors_memory(svc)
    await svc.close()


async def test_a_lasting_store_failure_ends_in_failed_after_the_retries():
    store = FailingStore()
    complete = FakeComplete()
    svc = service(store, complete=complete)
    await produced(svc)
    n0 = len(complete.requests)
    store.job_fails, store.times = label_a_job("done"), 1000
    await svc.command(
        "P", CommandRequest(command=MoveRequirement(requirement="R2", to_cluster="B")), "a"
    )
    await asyncio.wait_for(svc.wait_idle(), 5)
    rt = svc.runtime("P")
    assert rt.state.node(ref(LABEL, "A")).status == Status.FAILED
    assert running_nodes(svc) == [] and rt.idle()
    assert calls(complete.requests[n0:])[("ClusterLabel", "A/label")] == FAST.store_retries + 1
    assert rt.state.node(ref(LABEL, "B")).status == Status.FRESH  # other work went on
    assert_store_mirrors_memory(svc)
    await svc.close()


async def test_failed_commit_of_a_cancellation_releases_the_nodes():
    store = FailingStore()
    complete = FakeComplete()
    svc = service(store, complete=complete)
    await produced(svc)
    rt = svc.runtime("P")
    complete.delay_s = 0.2
    edit = EditRequirement(requirement="R1", text="Sistem girişi kilitler.")
    await svc.command("P", CommandRequest(command=edit), "a")
    label = ref(LABEL, "A")
    loop = asyncio.get_running_loop()
    end = loop.time() + 3
    while rt.state.node(label).status != Status.RUNNING:
        assert loop.time() < end
        await asyncio.sleep(0.005)
    complete.delay_s = 0.0
    store.job_fails, store.times = label_a_job("cancelled"), 1
    store.save_fails = 0
    again = EditRequirement(requirement="R1", text="Sistem girişi 15 dakika kilitler.")
    await svc.command("P", CommandRequest(command=again), "a")  # cancels A's label job
    await asyncio.wait_for(svc.wait_idle(), 5)
    assert store.times == 0
    assert running_nodes(svc) == [] and not rt._jobs and rt.idle()
    assert not analyze(rt.state).stale and not analyze(rt.state).failed
    await svc.close()


async def test_lock_and_cluster_key_change_nothing_when_the_commit_fails():
    store = FailingStore()
    svc = service(store)
    await produced(svc)
    rt = svc.runtime("P")
    r1 = ref(NodeKind.REQUIREMENT, "R1")
    store.save_fails = 1
    with pytest.raises(ConnectionError):
        svc.lock("P", r1, "ayse")
    assert svc.snapshot("P").locks == {}
    assert svc.lock("P", r1, "mehmet")  # the failed lock does not hold
    counter = rt.record.cluster_counter
    store.save_fails = 1
    with pytest.raises(ConnectionError):
        await svc.command("P", CommandRequest(command=CreateCluster(members=("R3",))), "ayse")
    assert rt.record.cluster_counter == counter
    created = await svc.command("P", CommandRequest(command=CreateCluster(members=("R3",))), "ayse")
    assert created.accepted
    assert f"C{counter + 1:03d}" in rt.state.keys_of(NodeKind.CLUSTER)
    await svc.close()


async def test_when_the_failure_cannot_be_recorded_either_memory_releases_alone():
    """The result commit and the failure record both fail: the release happens in memory
    only, the job is retried, and the next writes bring the store back in line."""
    store = FailingStore()
    complete = FakeComplete()
    svc = service(store, complete=complete)
    await produced(svc)
    n0 = len(complete.requests)
    seq0 = svc.snapshot("P").seq
    store.job_fails = lambda job: job.state in ("done", "failed") and ref(LABEL, "A") in job.nodes
    store.times = 2
    await svc.command(
        "P", CommandRequest(command=MoveRequirement(requirement="R2", to_cluster="B")), "a"
    )
    await asyncio.wait_for(svc.wait_idle(), 5)
    rt = svc.runtime("P")
    assert store.times == 0  # "done" failed, then "failed" failed: memory-only release
    assert running_nodes(svc) == [] and not rt._jobs and rt.idle()
    assert rt.state.node(ref(LABEL, "A")).status == Status.FRESH
    assert calls(complete.requests[n0:])[("ClusterLabel", "A/label")] == 2
    assert_store_mirrors_memory(svc)
    seqs = [e.seq for e in svc.events_after("P", seq0)]
    assert seqs == list(range(seq0 + 1, svc.snapshot("P").seq + 1))  # no gap from the failures
    await svc.close()


async def _approved_set_c(svc, complete: FakeComplete) -> str:
    """Approval mode on test sets, R5 edited, set C approved; returns R5's original text."""
    rt = svc.runtime("P")
    await svc.command("P", CommandRequest(command=SetStageMode(stage=SET, mode="approval")), "lead")
    text = rt.state.requirement("R5").text
    edit = EditRequirement(requirement="R5", text=text + " Ek.")
    await svc.command("P", CommandRequest(command=edit), "a")
    await svc.wait_idle()
    assert ("C", "waiting_approval") in {(j.node.key, j.state) for j in svc.snapshot("P").jobs}
    await svc.command("P", CommandRequest(command=ApproveStage(stage=SET)), "lead")
    assert rt.record.approved == [ref(SET, "C")]
    return text


async def test_approved_node_whose_job_is_cancelled_needs_a_new_approval():
    """Gate rule (review findings 2/3): a running approved node keeps its approval, but when
    its job is cancelled because its input changed, the approval goes."""
    complete = FakeComplete()
    svc = service(complete=complete)
    await produced(svc)
    rt = svc.runtime("P")
    text = await _approved_set_c(svc, complete)
    complete.delay_s = 0.3
    loop = asyncio.get_running_loop()
    end = loop.time() + 3
    while rt.state.node(ref(SET, "C")).status != Status.RUNNING:
        assert loop.time() < end
        await asyncio.sleep(0.005)
    assert rt.record.approved == [ref(SET, "C")]  # running keeps it
    complete.delay_s = 0.0
    again = EditRequirement(requirement="R5", text=text + " Başka.")
    await svc.command("P", CommandRequest(command=again), "a")  # cancels C's job
    assert rt.record.approved == []
    await asyncio.wait_for(svc.wait_idle(), 5)
    jobs = {(j.node.kind, j.node.key): j.state for j in svc.snapshot("P").jobs}
    assert jobs == {(SET, "C"): "waiting_approval"}
    assert any(j.state == "cancelled" and j.stage == SET for j in svc.store.jobs("P"))
    await svc.close()


async def test_approved_node_retried_after_a_store_failure_needs_no_new_approval():
    """Gate rule: a job released without a result because the store failed keeps the
    approval; the retry produces the set without asking again."""
    store = FailingStore()
    complete = FakeComplete()
    svc = service(store, complete=complete)
    await produced(svc)
    rt = svc.runtime("P")
    store.job_fails = lambda job: job.state == "done" and ref(SET, "C") in job.nodes
    store.times = 1
    n0 = len(complete.requests)
    await _approved_set_c(svc, complete)
    await asyncio.wait_for(svc.wait_idle(), 5)
    assert store.times == 0
    assert rt.state.node(ref(SET, "C")).status == Status.FRESH
    assert calls(complete.requests[n0:])[("TestCaseDelta", "C/incremental")] == 2
    assert rt.record.approved == [] and not svc.snapshot("P").jobs
    await svc.close()
