"""Job queue (docs/tasarim.md, İş kuyruğu): priority, P2 share, debounce, replacement, cancel."""

from __future__ import annotations

import asyncio

from worker.queue import JobQueue


def recorder(log: list[str], name: str, gate: asyncio.Event | None = None, delay: float = 0.0):
    async def run(job_id: int) -> None:
        log.append(name)
        if gate is not None:
            await gate.wait()
        if delay:
            await asyncio.sleep(delay)

    return run


async def test_better_class_starts_first_then_older():
    q = JobQueue(concurrency=1, p2_share=0.7)
    log: list[str] = []
    q.submit("a", "P2", recorder(log, "a"))
    q.submit("b", "P1", recorder(log, "b"))
    q.submit("c", "P0", recorder(log, "c"))
    q.submit("d", "P1", recorder(log, "d"))
    await asyncio.wait_for(q.join(), 2)
    assert log == ["c", "b", "d", "a"]


async def test_p2_jobs_hold_at_most_their_share_of_slots():
    q = JobQueue(concurrency=10, p2_share=0.7)
    gate = asyncio.Event()
    log: list[str] = []
    for i in range(12):
        q.submit(f"auto{i}", "P2", recorder(log, f"auto{i}", gate))
    await asyncio.sleep(0.02)
    assert len(q.running()) == 7  # floor(10 * 0.7)
    q.submit("user", "P1", recorder(log, "user", gate))
    q.submit("look", "P0", recorder(log, "look", gate))
    await asyncio.sleep(0.02)
    assert {r.key for r in q.running()} >= {"user", "look"}
    assert len(q.running()) == 9
    gate.set()
    await asyncio.wait_for(q.join(), 2)
    assert len(log) == 14


async def test_successive_submissions_inside_the_debounce_collapse_into_one_job():
    q = JobQueue(concurrency=4, p2_share=0.7)
    log: list[str] = []
    for i in range(5):
        q.submit("set:A", "P1", recorder(log, f"edit{i}"), delay=0.05)
        await asyncio.sleep(0.01)
    assert log == []  # still inside the window
    await asyncio.wait_for(q.join(), 2)
    assert log == ["edit4"]  # the newest run function, once


async def test_replacement_keeps_the_better_class_and_queue_position():
    q = JobQueue(concurrency=1, p2_share=1.0)
    gate = asyncio.Event()
    log: list[str] = []
    q.submit("busy", "P0", recorder(log, "busy", gate))
    await asyncio.sleep(0.01)
    q.submit("x", "P0", recorder(log, "x-old"))
    q.submit("y", "P1", recorder(log, "y"))
    q.submit("x", "P2", recorder(log, "x-new"))  # automatic resubmission does not demote
    gate.set()
    await asyncio.wait_for(q.join(), 2)
    assert log == ["busy", "x-new", "y"]


async def test_reprioritize_raises_a_pending_job():
    q = JobQueue(concurrency=1, p2_share=1.0)
    gate = asyncio.Event()
    log: list[str] = []
    q.submit("busy", "P0", recorder(log, "busy", gate))
    await asyncio.sleep(0.01)
    q.submit("a", "P2", recorder(log, "a"))
    q.submit("b", "P2", recorder(log, "b"))
    q.reprioritize("b", "P0")
    q.reprioritize("b", "P2")  # never lowers
    gate.set()
    await asyncio.wait_for(q.join(), 2)
    assert log == ["busy", "b", "a"]


async def test_cancel_stops_the_running_task_and_runs_its_cleanup():
    q = JobQueue(concurrency=2, p2_share=1.0)
    cleaned: list[int] = []
    started = asyncio.Event()

    async def slow(job_id: int) -> None:
        try:
            started.set()
            await asyncio.sleep(10)
        finally:
            cleaned.append(job_id)

    q.submit("set:A", "P1", slow)
    await asyncio.wait_for(started.wait(), 1)
    (job,) = q.running()
    assert q.cancel(job.job_id)
    await asyncio.wait_for(q.join(), 1)
    assert cleaned == [job.job_id]
    assert not q.cancel(job.job_id)


async def test_same_key_may_be_pending_while_running_and_drop_removes_it():
    q = JobQueue(concurrency=2, p2_share=1.0)
    gate = asyncio.Event()
    log: list[str] = []
    q.submit("batch:method", "P2", recorder(log, "first", gate))
    await asyncio.sleep(0.01)
    q.submit("batch:method", "P2", recorder(log, "second"), delay=0.05)
    assert q.is_pending("batch:method")
    assert [r.key for r in q.running()] == ["batch:method"]
    assert q.drop("batch:method")
    gate.set()
    await asyncio.wait_for(q.join(), 1)
    assert log == ["first"]


async def test_a_raising_job_does_not_stop_the_queue():
    q = JobQueue(concurrency=1, p2_share=1.0)
    log: list[str] = []

    async def boom(job_id: int) -> None:
        raise RuntimeError("x")

    q.submit("a", "P0", boom)
    q.submit("b", "P1", recorder(log, "b"))
    await asyncio.wait_for(q.join(), 1)
    assert log == ["b"]
    await q.close()
