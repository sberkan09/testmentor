"""`ProjectService` surface (paket 5): construction from config, the paket 4 seam (import,
matrix view, xlsx export), live progress, unknown projects."""

from __future__ import annotations

import asyncio

import pytest

from core.llm import LLMReply, LLMRequest
from services.fake_llm import FakeComplete, FakeEmbed
from tests.worker.helpers import produced, project, service
from worker import integration
from worker.contracts import ColumnMapping, ImportRequest, ProjectService
from worker.runtime import report_progress
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


async def test_snapshot_matrix_comes_from_paket4():
    svc = service()
    await produced(svc)
    snap = svc.snapshot("P")
    if not integration.available()["matrix_rows"]:
        assert snap.matrix == ()  # paket 4 not merged yet
        with pytest.raises(integration.Paket4Missing):
            svc.matrix_xlsx("P")
        return
    assert [row.requirement_id for row in snap.matrix] == ["R1", "R2", "R3", "R4", "R5", "R6"]
    assert all(row.covered for row in snap.matrix)
    assert svc.matrix_xlsx("P")[:2] == b"PK"


async def test_create_project_imports_through_paket4():
    request = ImportRequest(name="Örnek", key="IMP", mapping=ColumnMapping(text="metin", id="no"))
    data = "no,metin\nR1,Sistem girişi kilitler.\nR2,Sistem rapor üretir.\n".encode()
    svc = service()
    if not integration.available()["build_project"]:
        with pytest.raises(integration.Paket4Missing):
            await svc.create_project(request, data, "set.csv")
        return
    snap = await svc.create_project(request, data, "set.csv")
    assert snap.project_id == "IMP" and snap.name == "Örnek"
    await asyncio.wait_for(svc.wait_idle(), 10)
    assert svc.projects() == [("IMP", "Örnek")]
    await svc.close()
