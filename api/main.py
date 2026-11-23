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

import importlib
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
    """The `ProjectService` of this process.

    TODO(birleştirme): paket 5'in `worker.service` kurucusu burada çağrılacak
    (`deps.complete`, `deps.embed`, `deps.settings`; `deps.store == "memory"` için
    `core.store.InMemoryStore`, aksi halde `deps.pg_dsn` ile Postgres deposu). İmza tahmin
    edilmedi.
    """
    try:
        module: Any = importlib.import_module("worker.service")
    except ModuleNotFoundError as exc:
        if exc.name not in {"worker.service", "worker"}:
            raise
        raise RuntimeError(
            "worker/service.py (paket 5) bulunamadı: API ProjectService olmadan başlamaz. "
            "Paket 5 birleştirilince api/main.py içindeki build_service() bağlanır."
        ) from exc
    deps = build_deps()
    raise NotImplementedError(
        f"build_service() worker.service ({module.__name__}) ile henüz bağlanmadı "
        f"(store={deps.store}, fake={deps.fake})"
    )


app = create_app(build_service())
