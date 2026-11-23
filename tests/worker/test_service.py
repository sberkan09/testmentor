"""`ProjectService` surface (paket 5): construction from config, paket 4 (import, matrix view,
xlsx export), per-project knowledge base tools (paket 7), live progress, unknown projects."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from core.llm import LLMReply, LLMRequest
from core.nodes import NodeKind
from services.fake_llm import FakeComplete, FakeEmbed
from tests.worker.helpers import produced, project, service
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
