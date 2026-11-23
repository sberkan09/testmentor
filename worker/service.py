"""`worker.contracts.ProjectService` (paket 5): what the API (paket 6) calls.

One instance per process, one shared job queue for every project (the concurrency limit is the
model server's). Projects live in memory (`worker.runtime.ProjectRuntime`) and in the store; `start`
loads every stored project. An unknown project id raises `KeyError` (the API answers 404).

Setting up:

    store = PostgresStore.connect(dsn)            # or MemoryProjectStore() in tests
    service = OrchestratorService.from_config(store, complete=ClientComplete(client),
                                              embed=Embedder(...))
    await service.start()
    ...
    await service.close()

Development and tests use `services.fake_llm.FakeComplete` and `FakeEmbed`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from core.graph import ProjectState
from core.llm import Complete
from core.nodes import NodeRef
from core.stages.base import Embed, PassageSource, Retrieve
from services.settings import load_llm_settings, load_stage_settings, stage_configs
from worker import integration
from worker.contracts import (
    CommandRequest,
    CommandResult,
    ImportRequest,
    ServerEvent,
    Snapshot,
)
from worker.queue import JobQueue
from worker.runtime import ProjectRuntime, RuntimeDeps
from worker.settings import load_orchestrator_settings
from worker.store import ProjectStore


class OrchestratorService:
    def __init__(self, store: ProjectStore, deps: RuntimeDeps) -> None:
        self.store = store
        self.deps = deps
        o = deps.orchestrator
        self.queue = JobQueue(concurrency=o.concurrency, p2_share=o.p2_share)
        self._projects: dict[str, ProjectRuntime] = {}

    @classmethod
    def from_config(
        cls,
        store: ProjectStore,
        *,
        complete: Complete,
        embed: Embed,
        retrieve: Retrieve | None = None,
        passages: PassageSource | None = None,
        config_dir: str | Path = "config",
        model: str | None = None,
        embedding_model_version: str | None = None,
    ) -> OrchestratorService:
        """Settings from `config/`: stage settings (pipeline.yaml), stage configs with the active
        model (runtime.yaml `llm.model`) and embedding model version, orchestrator section."""
        from services.settings import load_embedding_settings

        settings = load_stage_settings(config_dir)
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
        )
        return cls(store, deps)

    # Lifecycle ----------------------------------------------------------------------------------

    async def start(self) -> None:
        """Load every stored project and queue its pending work."""
        for record in self.store.list_projects():
            if record.project_id not in self._projects:
                self._projects[record.project_id] = ProjectRuntime.load(
                    record, self.store, self.queue, self.deps
                )

    async def close(self) -> None:
        await self.queue.close()

    async def wait_idle(self) -> None:
        """Until no job is queued or running (tests, scripts)."""
        await self.queue.join()

    def runtime(self, project_id: str) -> ProjectRuntime:
        return self._projects[project_id]

    # ProjectService -----------------------------------------------------------------------------

    async def create_project(self, request: ImportRequest, data: bytes, filename: str) -> Snapshot:
        if request.key in self._projects or self.store.get_project(request.key) is not None:
            raise ValueError(f"project {request.key} exists")
        if self.deps.embed is None:
            raise RuntimeError("no embedding service")
        state = await integration.build_project(
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
        pid = state.project_id
        if pid in self._projects or self.store.get_project(pid) is not None:
            raise ValueError(f"project {pid} exists")
        self._projects[pid] = ProjectRuntime.create(name, state, self.store, self.queue, self.deps)
        return self.snapshot(pid)

    async def command(self, project_id: str, request: CommandRequest, actor: str) -> CommandResult:
        return self._projects[project_id].command(request, actor)

    def snapshot(self, project_id: str) -> Snapshot:
        rt = self._projects[project_id]
        return rt.snapshot(integration.matrix_rows(rt.state, self.deps.settings.test_method))

    def events_after(self, project_id: str, seq: int) -> list[ServerEvent] | None:
        return self._projects[project_id].events_after(seq)

    def subscribe(self, project_id: str) -> AsyncIterator[ServerEvent]:
        return self._projects[project_id].subscribe()

    def lock(self, project_id: str, ref: NodeRef, actor: str) -> bool:
        return self._projects[project_id].lock(ref, actor)

    def matrix_xlsx(self, project_id: str) -> bytes:
        rt = self._projects[project_id]
        return integration.matrix_xlsx(rt.state, self.deps.settings.test_method)

    def projects(self) -> list[tuple[str, str]]:
        return sorted((pid, rt.record.name) for pid, rt in self._projects.items())
