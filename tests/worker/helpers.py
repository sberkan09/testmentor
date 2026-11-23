"""Shared layout for the orchestrator tests: the paket 3 settings from config/pipeline.yaml
(`prune_removals: true`), `services.fake_llm` for the model and embeddings, project P with
requirements R1–R6 in clusters A{R1,R2}, B{R3,R4}, C{R5,R6}; no network, no GPU."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

import yaml

import core.stages  # noqa: F401  (registers the stages)
from core.graph import ProjectState, content_hash, new_project
from core.invalidation import analyze
from core.llm import LLMRequest
from core.nodes import MethodDef, NodeKind, NodeRef, RequirementContent
from services.fake_llm import FakeComplete, FakeEmbed
from services.settings import load_stage_settings, stage_configs
from worker.runtime import RuntimeDeps
from worker.service import OrchestratorService
from worker.settings import OrchestratorSettings
from worker.store import MemoryProjectStore, ProjectStore

SETTINGS = load_stage_settings("config")
CONFIGS = stage_configs(SETTINGS, model="fake-llm", embedding_model_version="fake-embed")
METHODS = tuple(
    MethodDef(**m)
    for m in yaml.safe_load(open("config/pipeline.yaml", encoding="utf-8"))["methods"]
)
REQS = {
    "R1": (
        "tr",
        "Sistem, kullanıcı girişini 3 başarısız denemeden sonra 15 dakika kilitlemelidir.",
    ),
    "R2": ("tr", "Sistem, parola sıfırlama bağlantısını 30 dakika geçerli tutmalıdır."),
    "R3": ("en", "The system shall log every configuration change with user and timestamp."),
    "R4": ("en", "The system shall export the audit log as CSV."),
    "R5": ("tr", "Sistem, rapor ekranını 2 saniye içinde açmalıdır."),
    "R6": ("en", "The system shall support 200 concurrent users."),
}
CLUSTERS = {"A": ("R1", "R2"), "B": ("R3", "R4"), "C": ("R5", "R6")}
FAST = OrchestratorSettings(debounce_s=0.01, concurrency=16, p2_share=0.7, lock_s=60)


def project(pid: str = "P") -> ProjectState:
    return new_project(
        pid,
        requirements=[
            RequirementContent(id=k, language=lang, text=t) for k, (lang, t) in REQS.items()
        ],
        clusters=CLUSTERS,
        card="Project: Örnek portal (P)",
        index_version="v1",
        stage_configs=CONFIGS,
        methods=METHODS,
    )


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def service(
    store: ProjectStore | None = None,
    *,
    complete: FakeComplete | None = None,
    orchestrator: OrchestratorSettings = FAST,
    clock: Callable[[], float] | None = None,
) -> OrchestratorService:
    deps = RuntimeDeps(
        complete=complete or FakeComplete(),
        settings=SETTINGS,
        stage_configs=CONFIGS,
        orchestrator=orchestrator,
        embed=FakeEmbed(),
        clock=clock or Clock(),
    )
    return OrchestratorService(store or MemoryProjectStore(), deps)


async def produced(svc: OrchestratorService, pid: str = "P") -> ProjectState:
    """Add the project, run every job, assert nothing is left to produce."""
    await svc.add_project(project(pid), "Örnek portal")
    await svc.wait_idle()
    state = svc.runtime(pid).state
    an = analyze(state)
    assert not an.stale and not an.failed, (an.stale, an.failed)
    return state


def calls(requests: list[LLMRequest]) -> Counter[tuple[str, str]]:
    """(schema, unit) of model calls."""
    return Counter((r.schema.__name__, r.unit) for r in requests)


def hashes(state: ProjectState) -> dict[NodeRef, str | None]:
    return {
        r: content_hash(n.content) if n.content is not None else None
        for r, n in state.nodes.items()
    }


def ref(kind: NodeKind, key: str) -> NodeRef:
    return NodeRef(kind=kind, key=key)
