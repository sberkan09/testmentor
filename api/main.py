"""`uvicorn api.main:app`: the server process (paket 6).

Environment:
- `TESTMENTOR_FAKE_LLM=1`: `services.fake_llm` for the model and embeddings (development,
  Playwright, the Compose check). The store is Postgres when `TESTMENTOR_PG_DSN` is set, else in
  memory.
- otherwise `ClientComplete` over `LLMClient.from_config()` and `services.embedder.Embedder`;
  the store is Postgres at `TESTMENTOR_PG_DSN`.
- `TESTMENTOR_STORE=memory` forces the in-memory store in both cases (demo with a real model).
- `web/dist`, when built, is served under `/` (see `create_app`).
- login: `auth:` of config/runtime.yaml, `TESTMENTOR_AUTH_MODE`, `TESTMENTOR_AUTH_SECRET`
  (`api/auth.py`).

`build_server()` is the single place where the orchestrator of paket 5 (`worker/service.py`) and
the knowledge base (paket 7, wired in paket 10) are put together; the dependencies are assembled
here as `ServiceDeps`. The project index follows the store: `services.kb_index_pg.PgIndex` on its
own connection to the same database with Postgres, `InMemoryIndex` in memory.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from api.app import create_app
from api.auth import Authenticator
from core.llm import Complete
from core.stages.base import Embed
from services.settings import StageSettings, load_stage_settings
from worker.contracts import ProjectService

if TYPE_CHECKING:
    from services.kb_documents import KbDocuments


@dataclass(frozen=True)
class ServiceDeps:
    complete: Complete
    embed: Embed
    settings: StageSettings
    store: str
    """`memory` or `postgres`."""
    pg_dsn: str | None
    fake: bool
    embedding_dim: int
    """Dimension of the knowledge base vectors (`kb_chunks.embedding`)."""


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
    store = os.environ.get("TESTMENTOR_STORE", "").strip().lower()
    dsn = os.environ.get("TESTMENTOR_PG_DSN") or None
    if _truthy("TESTMENTOR_FAKE_LLM"):
        from services.fake_llm import FakeComplete, FakeEmbed

        postgres = store != "memory" and dsn is not None
        return ServiceDeps(
            complete=FakeComplete(settings.test_method),
            embed=FakeEmbed(),
            settings=settings,
            store="postgres" if postgres else "memory",
            pg_dsn=dsn if postgres else None,
            fake=True,
            embedding_dim=FakeEmbed().dim,
        )
    from services.embedder import Embedder
    from services.llm_client import LLMClient
    from services.settings import load_embedding_settings
    from services.stage_llm import ClientComplete

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
        embedding_dim=load_embedding_settings().dim,
    )


@dataclass(frozen=True)
class Server:
    service: Any
    """`worker.service.OrchestratorService`."""
    kb: KbDocuments


def build_server(deps: ServiceDeps | None = None) -> Server:
    """The orchestrator with the memory or Postgres store (stored projects load on the first
    request) and the project knowledge base: index, example pool (`kb.examples: 0` leaves the
    prompts unchanged), retrieval tools per project and the upload handler."""
    from services.kb_documents import (
        KbDocuments,
        MemoryRegistry,
        PgRegistry,
        load_upload_settings,
    )
    from services.kb_examples import ExamplePool
    from services.kb_index import InMemoryIndex
    from services.kb_rerank import make_reranker
    from services.kb_retrieve import build_retrieval, make_example_source, make_select_examples
    from services.settings import load_embedding_settings, load_llm_settings
    from worker.runtime import ProjectTools
    from worker.service import OrchestratorService
    from worker.store import MemoryProjectStore
    from worker.store_pg import PostgresStore

    deps = deps or build_deps()
    kb_settings = deps.settings.kb
    index: Any
    registry: Any
    if deps.store == "memory":
        store: Any = MemoryProjectStore()
        index = InMemoryIndex(kb_settings)
        registry = MemoryRegistry()
    else:
        import psycopg

        from services.kb_index_pg import PgIndex

        assert deps.pg_dsn is not None
        store = PostgresStore.connect(deps.pg_dsn)
        kb_conn = psycopg.connect(deps.pg_dsn, autocommit=True)
        from services.settings import load_runtime

        pg_kb = load_runtime().get("kb_postgres") or {}
        index = PgIndex(kb_conn, kb_settings, dim=deps.embedding_dim, **pg_kb)
        index.ensure_schema()
        registry = PgRegistry(kb_conn)
        registry.ensure_schema()
    pool = ExamplePool()
    # approved (pinned) test cases enter the example pool after each command and before a
    # project's first retrieval in this process (paket 11)
    from services.kb_example_sync import ExampleSyncingService

    syncing = ExampleSyncingService(None, pool, deps.embed)
    reranker = make_reranker(kb_settings.reranker, kb_settings.rerank_max_tokens)
    embed = deps.embed

    def tools(project_id: str) -> ProjectTools:
        retrieve, passages = build_retrieval(index, project_id, embed, kb_settings, reranker)
        return ProjectTools(
            retrieve=retrieve,
            passages=passages,
            select_examples=syncing.synced_selection(
                project_id, make_select_examples(pool, project_id, embed, kb_settings.examples)
            ),
            example_texts=make_example_source(pool, project_id),
        )

    service = OrchestratorService.from_config(
        store,
        complete=deps.complete,
        embed=embed,
        tools=tools,
        settings=deps.settings,
        model="fake-llm" if deps.fake else load_llm_settings().model,
        embedding_model_version="fake-embed"
        if deps.fake
        else load_embedding_settings().model_version,
    )
    syncing.bind(service)
    kb = KbDocuments(
        index,
        registry,
        pool,
        embed,
        kb_settings,
        load_upload_settings(),
        on_change=service.kb_document_added,
    )
    return Server(service=syncing, kb=kb)


def build_service() -> ProjectService:
    """`build_server().service`."""
    return build_server().service


server = build_server()
app = create_app(server.service, kb=server.kb, auth=Authenticator.from_config())
