"""Priority job queue (docs/tasarim.md, İş kuyruğu).

- Three classes: P0 (what the user looks at, `Focus` and `Regenerate`), P1 (other user-triggered
  work), P2 (automatic progress). Among due jobs the better class starts first, then the older
  submission.
- A job is submitted under a key (a node, or a batched stage). A pending job with the same key is
  replaced by the new submission: the newer run function, the better of the two classes, and the
  new due time, so edits arriving inside the debounce window collapse into one job.
- At most `concurrency` jobs run; P2 jobs hold at most `p2_share` of the slots (at least one), so
  user work always finds a slot soon.
- A job with the same key may be pending while another runs (a batched stage gets new ready nodes
  while its previous batch is in flight).
- `cancel(job_id)` cancels the running task; the run function's own `finally` cleans up. A model
  call in flight is aborted with the task (`services.stage_llm.ClientComplete` stops streaming).

The queue knows nothing about nodes: the run function reads the current project state when it
starts, so a job always works on the newest inputs.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from worker.contracts import Priority

log = logging.getLogger(__name__)

Run = Callable[[int], Awaitable[None]]
"""Receives the job id assigned at start (for `cancel`)."""

_RANK = {"P0": 0, "P1": 1, "P2": 2}


def better(a: Priority, b: Priority) -> Priority:
    return a if _RANK[a] <= _RANK[b] else b


@dataclass
class Pending:
    key: str
    priority: Priority
    due: float
    order: int
    run: Run


@dataclass
class Running:
    job_id: int
    key: str
    priority: Priority
    task: asyncio.Task[None]


class JobQueue:
    def __init__(self, *, concurrency: int, p2_share: float) -> None:
        self.concurrency = concurrency
        self.p2_limit = max(1, math.floor(concurrency * p2_share))
        self._pending: dict[str, Pending] = {}
        self._running: dict[int, Running] = {}
        self._order = itertools.count()
        self._ids = itertools.count(1)
        self._wake: asyncio.Event | None = None
        self._idle: asyncio.Event | None = None
        self._dispatcher: asyncio.Task[None] | None = None
        self._closed = False

    # Submission ---------------------------------------------------------------------------------

    def submit(self, key: str, priority: Priority, run: Run, *, delay: float = 0.0) -> None:
        if self._closed:
            return
        now = asyncio.get_running_loop().time()
        old = self._pending.get(key)
        self._pending[key] = Pending(
            key=key,
            priority=priority if old is None else better(old.priority, priority),
            due=now + delay,
            order=next(self._order) if old is None else old.order,
            run=run,
        )
        self._kick()

    def reprioritize(self, key: str, priority: Priority) -> None:
        """Raise (never lower) a pending job's class; its due time stays."""
        job = self._pending.get(key)
        if job is not None and better(job.priority, priority) != job.priority:
            job.priority = priority
            self._kick()

    def drop(self, key: str) -> bool:
        """Remove a pending job (it had not started)."""
        found = self._pending.pop(key, None) is not None
        if found:
            self._kick()
        return found

    def cancel(self, job_id: int) -> bool:
        job = self._running.get(job_id)
        if job is None:
            return False
        job.task.cancel()
        return True

    # Views --------------------------------------------------------------------------------------

    def pending(self) -> list[Pending]:
        return sorted(self._pending.values(), key=lambda p: (_RANK[p.priority], p.order))

    def running(self) -> list[Running]:
        return list(self._running.values())

    def is_pending(self, key: str) -> bool:
        return key in self._pending

    def idle(self) -> bool:
        return not self._pending and not self._running

    async def join(self) -> None:
        """Wait until nothing is pending or running."""
        while not self.idle():
            self._ensure()
            assert self._idle is not None
            self._idle.clear()
            if self.idle():
                break
            await self._idle.wait()

    async def close(self) -> None:
        self._closed = True
        self._pending.clear()
        tasks = [r.task for r in self._running.values()]
        if self._dispatcher is not None:
            tasks.append(self._dispatcher)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._dispatcher = None

    # Dispatch -----------------------------------------------------------------------------------

    def _ensure(self) -> None:
        if self._wake is None:
            self._wake = asyncio.Event()
            self._idle = asyncio.Event()
        if (self._dispatcher is None or self._dispatcher.done()) and not self._closed:
            self._dispatcher = asyncio.get_running_loop().create_task(self._dispatch())

    def _kick(self) -> None:
        self._ensure()
        assert self._wake is not None
        self._wake.set()

    def _notify_idle(self) -> None:
        if self.idle() and self._idle is not None:
            self._idle.set()

    async def _dispatch(self) -> None:
        assert self._wake is not None
        loop = asyncio.get_running_loop()
        while not self._closed:
            self._wake.clear()
            self._start_due(loop.time())
            self._notify_idle()
            # Sleep until the next job that could start then; jobs that wait for a slot (all
            # slots, or the P2 share, taken) are woken by `_kick` when a job ends or arrives.
            p2_full = self._p2_running() >= self.p2_limit
            waits = [p.due for p in self._pending.values() if not (p.priority == "P2" and p2_full)]
            timeout = None
            if waits and len(self._running) < self.concurrency:
                timeout = max(0.0, min(waits) - loop.time())
            try:
                await asyncio.wait_for(self._wake.wait(), timeout)
            except TimeoutError:
                pass

    def _p2_running(self) -> int:
        return sum(1 for r in self._running.values() if r.priority == "P2")

    def _start_due(self, now: float) -> None:
        p2_running = self._p2_running()
        for job in self.pending():
            if len(self._running) >= self.concurrency:
                return
            if job.due > now:
                continue
            if job.priority == "P2" and p2_running >= self.p2_limit:
                continue
            del self._pending[job.key]
            job_id = next(self._ids)
            task = asyncio.get_running_loop().create_task(self._wrap(job_id, job))
            self._running[job_id] = Running(job_id, job.key, job.priority, task)
            if job.priority == "P2":
                p2_running += 1

    async def _wrap(self, job_id: int, job: Pending) -> None:
        try:
            await job.run(job_id)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - one job's failure must not stop the queue
            log.exception("job %s (%s) raised", job_id, job.key)
        finally:
            self._running.pop(job_id, None)
            if not self._closed:
                self._kick()
                self._notify_idle()
