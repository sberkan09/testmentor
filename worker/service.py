"""`worker.contracts.ProjectService` (paket 5): what the API (paket 6) calls.

One instance per process, one shared job queue for every project (the concurrency limit is the
model server's). Projects live in memory (`worker.runtime.ProjectRuntime`) and in the store; `start`
loads every stored project. An unknown project id raises `KeyError` (the API answers 404).

The service is single-threaded: every method runs on one event loop, in its thread (the API's
endpoints are `async def`), so a command, a job step and a snapshot never interleave. A call from
another thread or loop raises `RuntimeError`.

Setting up:

    store = PostgresStore.connect(dsn)            # or MemoryProjectStore() in tests
    service = OrchestratorService.from_config(store, complete=ClientComplete(client),
                                              embed=Embedder(...))
    await service.start()
    ...
    await service.close()

Development and tests use `services.fake_llm.FakeComplete` and `FakeEmbed`. The knowledge base
(paket 7) comes in per project through `tools=lambda pid: ProjectTools(...)` built with
`services.kb_retrieve` (`build_retrieval`, `make_select_examples`, `make_example_source`).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from core.events import KbDocumentAdded
from core.graph import ProjectState
from core.llm import Complete
from core.matrix_view import matrix_rows
from core.nodes import NodeRef
from core.settings import StageSettings
from core.stages.base import Embed, PassageSource, Retrieve
from services.importer import build_project
from services.settings import load_llm_settings, load_stage_settings, stage_configs
from services.xlsx_export import matrix_xlsx
from worker.contracts import (
    CommandRequest,
    CommandResult,
    ImportRequest,
    ServerEvent,
    Snapshot,
)
from worker.queue import JobQueue
from worker.runtime import ProjectRuntime, ProjectTools, RuntimeDeps
from worker.settings import load_orchestrator_settings
from worker.store import ProjectStore

log = logging.getLogger(__name__)


class OrchestratorService:
    def __init__(self, store: ProjectStore, deps: RuntimeDeps) -> None:
        self.store = store
        self.deps = deps
        o = deps.orchestrator
        self.queue = JobQueue(concurrency=o.concurrency, p2_share=o.p2_share)
        self._projects: dict[str, ProjectRuntime] = {}
        self._loaded = False
        self._load_errors: dict[str, str] = {}
        """Projects that failed to load (id → error), retried on the next call."""
        self._loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    def from_config(
        cls,
        store: ProjectStore,
        *,
        complete: Complete,
        embed: Embed,
        retrieve: Retrieve | None = None,
        passages: PassageSource | None = None,
        tools: Callable[[str], ProjectTools] | None = None,
        config_dir: str | Path = "config",
        model: str | None = None,
        embedding_model_version: str | None = None,
        settings: StageSettings | None = None,
    ) -> OrchestratorService:
        """Settings from `config/`: stage settings (pipeline.yaml), stage configs with the active
        model (runtime.yaml `llm.model`) and embedding model version, orchestrator section."""
        from services.settings import load_embedding_settings

        settings = settings or load_stage_settings(config_dir)
        configs = stage_configs(
            settings,
            model=model or load_llm_settings(config_dir).model,
            embedding_model_version=embedding_model_version
            or load_embedding_settings(config_dir).model_version,
        )
        deps = RuntimeDeps(
            complete=complete,
            settings=settings,
            stage_configs=configs,
            orchestrator=load_orchestrator_settings(config_dir),
            embed=embed,
            retrieve=retrieve,
            passages=passages,
            tools=tools,
        )
        return cls(store, deps)

    # Lifecycle ----------------------------------------------------------------------------------

    async def start(self) -> None:
        """Load every stored project and queue its pending work. Optional: the first call of any
        service method inside the event loop does it too (the API builds the service before the
        loop runs)."""
        self._load()

    def _on_loop(self) -> None:
        """The service has one writer: every method runs on the event loop it first ran on, in
        that loop's thread (`async def` endpoints; never FastAPI's thread pool)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError(
                "OrchestratorService must be called on its event loop thread "
                "(an `async def` endpoint), not from a worker thread"
            ) from None
        if self._loop is None:
            self._loop = loop
        elif loop is not self._loop:
            raise RuntimeError("OrchestratorService is bound to another event loop")

    def _load(self) -> None:
        """Every stored project, each on its own: one that fails to load is logged, left out and
        tried again on the next call; the others are served."""
        self._on_loop()
        if self._loaded:
            return
        failed = False
        for record in self.store.list_projects():
            pid = record.project_id
            if pid in self._projects:
                continue
            try:
                self._projects[pid] = ProjectRuntime.load(record, self.store, self.queue, self.deps)
            except Exception as exc:  # noqa: BLE001 - the other projects stay available
                failed = True
                for p in self.queue.pending():  # jobs the half-loaded runtime queued
                    if p.key.startswith(f"{pid}|"):
                        self.queue.drop(p.key)
                if pid not in self._load_errors:
                    log.exception("project %s could not be loaded; retrying on the next call", pid)
                self._load_errors[pid] = f"{type(exc).__name__}: {exc}"
            else:
                self._load_errors.pop(pid, None)
        self._loaded = not failed

    async def close(self) -> None:
        await self.queue.close()

    async def wait_idle(self) -> None:
        """Until no job is queued or running (tests, scripts)."""
        await self.queue.join()

    def runtime(self, project_id: str) -> ProjectRuntime:
        self._load()
        return self._projects[project_id]

    # ProjectService -----------------------------------------------------------------------------

    async def create_project(self, request: ImportRequest, data: bytes, filename: str) -> Snapshot:
        self._load()
        if request.key in self._projects or self.store.get_project(request.key) is not None:
            raise ValueError(f"project {request.key} exists")
        if self.deps.embed is None:
            raise RuntimeError("no embedding service")
        state = await build_project(
            request,
            data,
            filename,
            embed=self.deps.embed,
            settings=self.deps.settings,
            stage_configs=self.deps.stage_configs,
        )
        return await self.add_project(state, request.name)

    async def add_project(self, state: ProjectState, name: str) -> Snapshot:
        """Register an already built project (import, tests, development data)."""
        self._load()
        pid = state.project_id
        if pid in self._projects or self.store.get_project(pid) is not None:
            raise ValueError(f"project {pid} exists")
        self._projects[pid] = ProjectRuntime.create(name, state, self.store, self.queue, self.deps)
        return self.snapshot(pid)

    async def command(self, project_id: str, request: CommandRequest, actor: str) -> CommandResult:
        return self.runtime(project_id).command(request, actor)

    def snapshot(self, project_id: str) -> Snapshot:
        method = self.deps.settings.test_method
        return self.runtime(project_id).snapshot(lambda state: matrix_rows(state, method))

    def events_after(self, project_id: str, seq: int) -> list[ServerEvent] | None:
        return self.runtime(project_id).events_after(seq)

    def subscribe(self, project_id: str) -> AsyncIterator[ServerEvent]:
        return self.runtime(project_id).subscribe()

    def lock(self, project_id: str, ref: NodeRef, actor: str) -> bool:
        return self.runtime(project_id).lock(ref, actor)

    def matrix_xlsx(self, project_id: str) -> bytes:
        rt = self.runtime(project_id)
        return matrix_xlsx(rt.state, self.deps.settings.test_method)

    def kb_document_added(
        self, project_id: str, document_id: str, index_version: str, actor: str = "system"
    ) -> int:
        """After a knowledge base upload (paket 7; not part of the frozen `ProjectService`):
        every retrieval re-checks; test sets whose passages are unchanged stay fresh."""
        event = KbDocumentAdded(document_id=document_id, index_version=index_version)
        return self.runtime(project_id).system_event(event, actor)

    def projects(self) -> list[tuple[str, str]]:
        self._load()
        return sorted((pid, rt.record.name) for pid, rt in self._projects.items())
