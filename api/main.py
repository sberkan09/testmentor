"""`uvicorn api.main:app`: the server process (paket 6).

Environment:
- `TESTMENTOR_FAKE_LLM=1`: `services.fake_llm` and an in-memory store (development, Playwright).
- otherwise `ClientComplete` over `LLMClient.from_config()` and `services.embedder.Embedder`;
  the store is in memory when `TESTMENTOR_STORE=memory` (demo with a real model), else Postgres
  at `TESTMENTOR_PG_DSN`.
- `web/dist`, when built, is served under `/` (see `create_app`).

`build_service()` is the single place where the orchestrator of paket 5 (`worker/service.py`) is
wired; the dependencies it needs are assembled here as `ServiceDeps`.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from api.app import create_app
from core.llm import Complete
from core.stages.base import Embed
from services.settings import StageSettings, load_stage_settings
from worker.contracts import ProjectService


@dataclass(frozen=True)
class ServiceDeps:
    complete: Complete
    embed: Embed
    settings: StageSettings
    store: str
    """`memory` or `postgres`."""
    pg_dsn: str | None
    fake: bool


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


class _EmbedAdapter:
    """`core.stages.base.Embed` over `Embedder.embed` (which returns a batch with usage)."""

    def __init__(self, embedder: Any) -> None:
        self._embedder = embedder

    async def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        batch = await self._embedder.embed(texts)
        return batch.vectors


def build_deps() -> ServiceDeps:
    settings = load_stage_settings()
    if _truthy("TESTMENTOR_FAKE_LLM"):
        from services.fake_llm import FakeComplete, FakeEmbed

        return ServiceDeps(
            complete=FakeComplete(settings.test_method),
            embed=FakeEmbed(),
            settings=settings,
            store="memory",
            pg_dsn=None,
            fake=True,
        )
    from services.embedder import Embedder
    from services.llm_client import LLMClient
    from services.stage_llm import ClientComplete

    store = os.environ.get("TESTMENTOR_STORE", "postgres").strip().lower()
    dsn = os.environ.get("TESTMENTOR_PG_DSN")
    if store != "memory" and not dsn:
        raise RuntimeError(
            "TESTMENTOR_PG_DSN is not set; set it, or use TESTMENTOR_STORE=memory "
            "(in-memory store) or TESTMENTOR_FAKE_LLM=1"
        )
    return ServiceDeps(
        complete=ClientComplete(LLMClient.from_config()),
        embed=_EmbedAdapter(Embedder.from_config()),
        settings=settings,
        store="memory" if store == "memory" else "postgres",
        pg_dsn=dsn,
        fake=False,
    )


def build_service() -> ProjectService:
    """The `ProjectService` of this process: `worker.service.OrchestratorService` (paket 5) with
    the memory or Postgres store; stored projects load on the first request."""
    from services.settings import load_embedding_settings, load_llm_settings
    from worker.service import OrchestratorService
    from worker.store import MemoryProjectStore
    from worker.store_pg import PostgresStore

    deps = build_deps()
    if deps.store == "memory":
        store: Any = MemoryProjectStore()
    else:
        assert deps.pg_dsn is not None
        store = PostgresStore.connect(deps.pg_dsn)
    return OrchestratorService.from_config(
        store,
        complete=deps.complete,
        embed=deps.embed,
        settings=deps.settings,
        model="fake-llm" if deps.fake else load_llm_settings().model,
        embedding_model_version="fake-embed"
        if deps.fake
        else load_embedding_settings().model_version,
    )


app = create_app(build_service())
