"""Knowledge base index (docs/tasarim.md, İndeks; paket 7).

`KbIndex` is the interface; `InMemoryIndex` (numpy cosine plus BM25, fused with RRF) serves
development, tests and measurement, `services/kb_index_pg.py` serves production (pgvector and
`tsvector`). Every call carries the `project_id`: a project never sees another project's chunks,
not even when document ids and texts are the same (tests/test_kb_isolation.py).

The interface is synchronous: search is CPU work over a local structure or one SQL statement, and
`core.stages.base.PassageSource` (the prompt side) is synchronous. The query vector comes from
the caller (`services/kb_retrieve.py`), which owns the embedding client.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from core.kb.chunking import Chunk, chunk_document
from core.kb.ranking import Bm25Index, rrf
from core.kb.settings import KbSettings
from core.stages.base import Embed

EMBED_BATCH = 128


class KbIndex(Protocol):
    def add(
        self,
        project_id: str,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]] | None = None,
    ) -> None:
        """Adds the chunks; every document they belong to is replaced (its earlier chunks go)."""

    def remove_document(self, project_id: str, document_id: str) -> None: ...

    def search(
        self,
        project_id: str,
        query_texts: Sequence[str],
        k: int,
        query_vector: Sequence[float] | None = None,
    ) -> list[str]:
        """Up to `k` passage ids (`Chunk.passage_id`), best first. Dense (cosine to
        `query_vector`) and keyword (BM25 over `query_texts` joined) rankings are fused with RRF;
        without a query vector only the keyword ranking counts."""

    def texts(self, project_id: str, ids: Sequence[str]) -> list[str]:
        """Prompt texts of the passage ids, same order. `KeyError` for an id the project does
        not hold."""

    def version(self, project_id: str) -> str:
        """Changes with every add or remove in the project (`KbIndexContent.version`)."""


@dataclass
class _Project:
    chunks: dict[str, Chunk] = field(default_factory=dict)
    vectors: dict[str, np.ndarray] = field(default_factory=dict)
    bm25: Bm25Index | None = None
    by_document: dict[str, set[str]] = field(default_factory=dict)
    changes: int = 0
    matrix: np.ndarray | None = None
    matrix_ids: list[str] = field(default_factory=list)


def _unit(vector: Sequence[float]) -> np.ndarray:
    v = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(v))
    return v / norm if norm else v


class InMemoryIndex:
    def __init__(self, settings: KbSettings) -> None:
        self.settings = settings
        self._projects: dict[str, _Project] = {}

    def _project(self, project_id: str) -> _Project:
        p = self._projects.get(project_id)
        if p is None:
            p = self._projects[project_id] = _Project(
                bm25=Bm25Index(self.settings.bm25_k1, self.settings.bm25_b)
            )
        return p

    def add(
        self,
        project_id: str,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]] | None = None,
    ) -> None:
        if vectors is not None and len(vectors) != len(chunks):
            raise ValueError("one vector per chunk")
        p = self._project(project_id)
        for doc in {c.document_id for c in chunks}:
            self._drop(p, doc)
        for i, c in enumerate(chunks):
            pid = c.passage_id
            p.chunks[pid] = c
            p.by_document.setdefault(c.document_id, set()).add(pid)
            assert p.bm25 is not None
            p.bm25.add(pid, c.text)
            if vectors is not None:
                p.vectors[pid] = _unit(vectors[i])
        p.changes += 1
        p.matrix = None

    def remove_document(self, project_id: str, document_id: str) -> None:
        p = self._project(project_id)
        self._drop(p, document_id)
        p.changes += 1
        p.matrix = None

    @staticmethod
    def _drop(p: _Project, document_id: str) -> None:
        for pid in p.by_document.pop(document_id, set()):
            p.chunks.pop(pid, None)
            p.vectors.pop(pid, None)
            assert p.bm25 is not None
            p.bm25.remove(pid)

    def version(self, project_id: str) -> str:
        p = self._projects.get(project_id)
        return f"v{p.changes if p else 0}"

    def texts(self, project_id: str, ids: Sequence[str]) -> list[str]:
        p = self._projects.get(project_id)
        if p is None:
            raise KeyError(f"unknown passage ids {list(ids)[:3]} in project {project_id!r}")
        out = []
        for i in ids:
            chunk = p.chunks.get(i)
            if chunk is None:
                raise KeyError(f"passage {i!r} is not in project {project_id!r}")
            out.append(chunk.prompt_text())
        return out

    def search(
        self,
        project_id: str,
        query_texts: Sequence[str],
        k: int,
        query_vector: Sequence[float] | None = None,
    ) -> list[str]:
        p = self._projects.get(project_id)
        if p is None or not p.chunks:
            return []
        depth = self.settings.rrf_depth
        rankings: list[list[str]] = []
        if query_vector is not None and p.vectors:
            rankings.append(self._dense(p, _unit(query_vector), depth))
        assert p.bm25 is not None
        rankings.append([i for i, _ in p.bm25.search(" ".join(query_texts), depth)])
        return rrf(rankings, self.settings.rrf_k)[:k]

    @staticmethod
    def _dense(p: _Project, q: np.ndarray, depth: int) -> list[str]:
        if p.matrix is None:
            p.matrix_ids = sorted(p.vectors)  # id order: stable ties
            p.matrix = np.stack([p.vectors[i] for i in p.matrix_ids])
        if p.matrix.shape[1] != q.shape[0]:
            raise ValueError(f"query vector has {q.shape[0]} dimensions, index {p.matrix.shape[1]}")
        scores = p.matrix @ q
        order = np.argsort(-scores, kind="stable")[:depth]
        return [p.matrix_ids[i] for i in order]


async def ingest_document(
    index: KbIndex,
    project_id: str,
    document_id: str,
    text: str,
    embed: Embed,
    settings: KbSettings,
) -> list[Chunk]:
    """Chunks the document, embeds the chunk texts in batches and adds them (replacing an earlier
    version of the same document). Returns the chunks."""
    chunks = chunk_document(
        document_id,
        text,
        chunk_tokens=settings.chunk_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
        chars_per_token=settings.chars_per_token,
    )
    vectors: list[list[float]] = []
    for i in range(0, len(chunks), EMBED_BATCH):
        vectors += await embed([c.text for c in chunks[i : i + EMBED_BATCH]])
    index.add(project_id, chunks, vectors)
    return chunks
