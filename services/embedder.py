"""Batched embedding client for the embedding service (OpenAI-compatible `/v1/embeddings`).

The model version is part of every result so that callers can put it into the embedding hash.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from services.settings import EmbeddingSettings, load_embedding_settings


class EmbeddingError(RuntimeError):
    pass


class EmbeddingBatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    model_version: str
    vectors: list[list[float]]
    prompt_tokens: int | None = None


class Embedder:
    def __init__(
        self,
        settings: EmbeddingSettings,
        *,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_parallel_batches: int = 4,
    ) -> None:
        self._settings = settings
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.AsyncClient(
            base_url=settings.base_url.rstrip("/"),
            headers=headers,
            timeout=settings.request_timeout_s,
            transport=transport,
        )
        self._sem = asyncio.Semaphore(max_parallel_batches)

    @classmethod
    def from_config(
        cls, config_dir: str | Path = "config", *, transport: httpx.AsyncBaseTransport | None = None
    ) -> Embedder:
        s = load_embedding_settings(config_dir)
        api_key = os.environ.get(s.api_key_env) if s.api_key_env else None
        return cls(s, api_key=api_key, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> Embedder:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """Embed texts in order; splits into batches of `batch_size` sent in parallel."""
        s = self._settings
        if not texts:
            return EmbeddingBatch(model=s.model, model_version=s.model_version, vectors=[])
        chunks = [list(texts[i : i + s.batch_size]) for i in range(0, len(texts), s.batch_size)]
        parts = await asyncio.gather(*(self._embed_chunk(c) for c in chunks))
        vectors = [v for part, _ in parts for v in part]
        tokens = [t for _, t in parts]
        return EmbeddingBatch(
            model=s.model,
            model_version=s.model_version,
            vectors=vectors,
            prompt_tokens=sum(tokens) if all(t is not None for t in tokens) else None,
        )

    async def _embed_chunk(self, texts: list[str]) -> tuple[list[list[float]], int | None]:
        async with self._sem:
            try:
                resp = await self._http.post(
                    "/embeddings", json={"model": self._settings.model, "input": texts}
                )
            except httpx.HTTPError as exc:
                raise EmbeddingError(f"transport error: {exc!r}") from exc
        if resp.status_code >= 400:
            raise EmbeddingError(f"HTTP {resp.status_code}: {resp.text[:2000]}")
        body = resp.json()
        data = sorted(body["data"], key=lambda d: d["index"])
        if len(data) != len(texts):
            raise EmbeddingError(f"expected {len(texts)} vectors, got {len(data)}")
        return [d["embedding"] for d in data], (body.get("usage") or {}).get("prompt_tokens")
