"""`ProjectService` surface (paket 5): construction from config, paket 4 (import, matrix view,
xlsx export), per-project knowledge base tools (paket 7), live progress, unknown projects."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from core.llm import LLMReply, LLMRequest
from core.nodes import NodeKind
from services.fake_llm import FakeComplete, FakeEmbed
from tests.worker.helpers import produced, project, ref, service
from worker.contracts import (
    ColumnMapping,
    CommandRequest,
    CreateCluster,
    ImportRequest,
    ProjectService,
)
from worker.runtime import ProjectTools, report_progress
from worker.service import OrchestratorService
from worker.store import MemoryProjectStore


def test_service_satisfies_the_contract():
    svc: ProjectService = service()  # type check: the Protocol
    for name in (
        "create_project",
        "command",
        "snapshot",
        "events_after",
        "subscribe",
        "lock",
        "matrix_xlsx",
        "projects",
    ):
        assert callable(getattr(svc, name))


def test_from_config_reads_the_orchestrator_section():
    svc = OrchestratorService.from_config(
        MemoryProjectStore(), complete=FakeComplete(), embed=FakeEmbed()
    )
    assert svc.deps.orchestrator.debounce_s == 1.5
    assert svc.queue.concurrency == 16 and svc.queue.p2_limit == 11
    assert svc.deps.settings.prune_removals is True


async def test_unknown_project_and_duplicate():
    svc = service()
    with pytest.raises(KeyError):
        svc.snapshot("X")
    await produced(svc)
    with pytest.raises(ValueError):
        await svc.add_project(svc.runtime("P").state, "again")
    await svc.close()


async def test_job_progress_is_live_only():
    class Streaming(FakeComplete):
        async def __call__(self, request: LLMRequest) -> LLMReply:
            report_progress(f"{request.unit} …")
            return await super().__call__(request)

    svc = service(complete=Streaming())
    await svc.add_project(project(), "P")
    sub = svc.subscribe("P")
    await svc.wait_idle()
    seen = []
    while not sub.queue.empty():
        seen.append(await sub.__anext__())
    progress = [e for e in seen if e.type == "job_progress"]
    assert progress and all(e.payload["text"].endswith("…") for e in progress)
    assert all(e.type != "job_progress" for e in svc.events_after("P", 0) or [])
    report_progress("outside a job")  # no-op
    await sub.aclose()
    await svc.close()


async def test_snapshot_matrix_and_xlsx_come_from_paket4():
    import io

    from openpyxl import load_workbook

    svc = service()
    await produced(svc)
    snap = svc.snapshot("P")
    assert [row.requirement_id for row in snap.matrix] == ["R1", "R2", "R3", "R4", "R5", "R6"]
    assert all(row.covered and row.warning == "" for row in snap.matrix)
    book = load_workbook(io.BytesIO(svc.matrix_xlsx("P")))
    assert book["Matris"].max_row == 7  # header + 6 requirements
    await svc.close()


async def test_create_project_imports_and_produces_everything():
    request = ImportRequest(name="Örnek", key="IMP", mapping=ColumnMapping(text="metin", id="no"))
    data = (
        "no,metin\n"
        "R1,Sistem kullanıcı girişini üç hatalı denemeden sonra kilitlemelidir.\n"
        "R2,Sistem kullanıcı girişini kilitlediğinde e-posta göndermelidir.\n"
        "R3,The system shall export the audit log as CSV.\n"
    ).encode()
    embed = FakeEmbed()
    svc = service()
    svc.deps = dataclasses.replace(svc.deps, embed=embed)
    snap = await svc.create_project(request, data, "set.csv")
    assert snap.project_id == "IMP" and snap.name == "Örnek"
    assert embed.calls == 1  # the import embeds once; embeddings are already settled
    await asyncio.wait_for(svc.wait_idle(), 10)
    assert embed.calls == 1
    assert svc.projects() == [("IMP", "Örnek")]
    snap = svc.snapshot("IMP")
    assert [r.requirement_id for r in snap.matrix] == ["R1", "R2", "R3"]
    assert all(r.covered for r in snap.matrix)
    assert all(n.status == "fresh" for n in snap.nodes)
    with pytest.raises(ValueError):
        await svc.create_project(request, data, "set.csv")
    # A cluster created by a command gets the next free key after the imported C00n keys.
    created = await svc.command(
        "IMP", CommandRequest(command=CreateCluster(members=("R3",))), "ayse"
    )
    assert created.accepted
    keys = svc.runtime("IMP").state.keys_of(NodeKind.CLUSTER)
    assert len(set(keys)) == len(keys) and all(k.startswith("C") for k in keys)
    await svc.close()


async def test_project_tools_are_built_per_project():
    built: list[str] = []
    asked: list[tuple[str, tuple[str, ...]]] = []

    def tools(pid: str) -> ProjectTools:
        built.append(pid)

        async def retrieve(members):
            asked.append((pid, tuple(m.id for m in members)))
            return []

        return ProjectTools(retrieve=retrieve)

    svc = service()
    svc.deps = dataclasses.replace(svc.deps, tools=tools)
    await produced(svc, "P")
    await produced(svc, "Q")
    assert built == ["P", "Q"]
    assert {pid for pid, _ in asked} == {"P", "Q"}
    assert ("P", ("R1", "R2")) in asked
    await svc.close()


async def test_subscription_registers_at_once_and_ends_with_its_task():
    svc = service()
    await produced(svc)
    rt = svc.runtime("P")
    sub = svc.subscribe("P")  # registered before the first read
    assert sub in rt._subscribers

    async def pump():
        async for _ in sub:
            pass

    task = asyncio.create_task(pump())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sub not in rt._subscribers
    await svc.close()


# Review fixes: event loop thread, loading, consistent snapshots ---------------------------------


async def test_service_refuses_calls_from_another_thread_or_loop():
    """Review finding 1c: the service is single-threaded on one event loop; a call from a worker
    thread (FastAPI's `def` endpoints) or from another loop fails loudly."""
    svc = service()
    await produced(svc)
    r1 = ref(NodeKind.REQUIREMENT, "R1")
    for call in (
        lambda: svc.snapshot("P"),
        lambda: svc.projects(),
        lambda: svc.lock("P", r1, "ayse"),
        lambda: svc.events_after("P", 0),
        lambda: svc.matrix_xlsx("P"),
    ):
        with pytest.raises(RuntimeError, match="event loop"):
            await asyncio.to_thread(call)

    async def elsewhere() -> None:
        svc.projects()

    with pytest.raises(RuntimeError, match="event loop"):
        await asyncio.to_thread(asyncio.run, elsewhere())
    assert svc.runtime("P").state.node(r1)  # still usable on its own loop
    assert svc.snapshot("P").locks == {}
    await svc.close()


async def test_a_project_that_fails_to_load_does_not_hide_the_others():
    """Review finding 1b: each project loads on its own; a failed one is retried later."""
    store = MemoryProjectStore()
    first = service(store)
    await produced(first, "P")
    await produced(first, "Q")
    await first.close()

    load = store.load
    broken = {"P"}

    def flaky_load(project_id: str):
        if project_id in broken:
            raise ConnectionError("lost")
        return load(project_id)

    store.load = flaky_load  # type: ignore[method-assign]
    again = service(store)
    assert again.projects() == [("Q", "Örnek portal")]
    with pytest.raises(KeyError):
        again.snapshot("P")
    broken.clear()
    assert again.projects() == [("P", "Örnek portal"), ("Q", "Örnek portal")]
    assert again.snapshot("P").project_id == "P"
    await again.close()


async def test_snapshot_agrees_with_the_events_up_to_its_seq():
    """Review finding 1: `seq`, nodes and jobs of a snapshot come from one state; replaying the
    live events up to a snapshot's `seq` on an earlier snapshot gives its nodes."""
    svc = service(complete=FakeComplete(delay_s=0.01))
    await svc.add_project(project(), "P")
    base = svc.snapshot("P")
    sub = svc.subscribe("P")
    nodes = {str(n.ref): n.model_dump(mode="json") for n in base.nodes}
    events = []
    checked = 0
    while not svc.runtime("P").idle() or not sub.queue.empty():
        snap = svc.snapshot("P")
        while not sub.queue.empty():
            events.append(sub.queue.get_nowait())
        for e in [e for e in events if e.seq <= snap.seq and e.type != "job_progress"]:
            if e.type == "node_removed":
                nodes.pop(f"{e.payload['ref']['kind']}:{e.payload['ref']['key']}", None)
            elif e.type.startswith("node_"):
                view = e.payload["node"]
                nodes[f"{view['ref']['kind']}:{view['ref']['key']}"] = view
        events = [e for e in events if e.seq > snap.seq]
        assert nodes == {str(n.ref): n.model_dump(mode="json") for n in snap.nodes}
        checked += 1
        await asyncio.sleep(0.005)
    assert checked > 3
    await sub.aclose()
    await svc.close()
