"""Postgres knowledge base index: pgvector (dense) and `tsvector` (keyword), fused with RRF
(docs/tasarim.md, İndeks; paket 7). Same `KbIndex` interface as `InMemoryIndex`.

Every statement filters on `project_id`. The keyword column holds the text after the same folding
as `core.kb.ranking.tokenize` (lower case, Turkish letters, no diacritics), so Turkish and
English match like in the in-memory index; ranking is `ts_rank_cd` (not BM25).

The connection is a `psycopg` connection with `autocommit=True` (the caller owns it). Vectors
travel as text literals, so the `pgvector` Python package is not needed; the server needs the
`vector` extension. Without it `ensure_schema` raises and the integration test skips.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from core.kb.chunking import Chunk
from core.kb.ranking import rrf, tokenize
from core.kb.settings import KbSettings


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.7g}" for x in vector) + "]"


class PgIndex:
    def __init__(self, conn: Any, settings: KbSettings, *, dim: int) -> None:
        self._conn = conn
        self.settings = settings
        self.dim = dim

    def ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"""CREATE TABLE IF NOT EXISTS kb_chunks (
                    project_id text NOT NULL,
                    passage_id text NOT NULL,
                    document_id text NOT NULL,
                    seq integer NOT NULL,
                    heading_path jsonb NOT NULL,
                    start_char integer NOT NULL,
                    prompt_text text NOT NULL,
                    fts text NOT NULL,
                    embedding vector({int(self.dim)}),
                    tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', fts)) STORED,
                    PRIMARY KEY (project_id, passage_id))"""
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS kb_chunks_document ON kb_chunks (project_id, document_id)"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS kb_chunks_tsv ON kb_chunks USING gin (tsv)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS kb_chunks_embedding ON kb_chunks "
                "USING hnsw (embedding vector_cosine_ops)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS kb_versions ("
                "project_id text PRIMARY KEY, changes integer NOT NULL)"
            )

    def _bump(self, cur: Any, project_id: str) -> None:
        cur.execute(
            "INSERT INTO kb_versions (project_id, changes) VALUES (%s, 1) "
            "ON CONFLICT (project_id) DO UPDATE SET changes = kb_versions.changes + 1",
            (project_id,),
        )

    def add(
        self,
        project_id: str,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]] | None = None,
    ) -> None:
        if vectors is not None and len(vectors) != len(chunks):
            raise ValueError("one vector per chunk")
        with self._conn.transaction(), self._conn.cursor() as cur:
            for doc in sorted({c.document_id for c in chunks}):
                cur.execute(
                    "DELETE FROM kb_chunks WHERE project_id = %s AND document_id = %s",
                    (project_id, doc),
                )
            for i, c in enumerate(chunks):
                cur.execute(
                    "INSERT INTO kb_chunks (project_id, passage_id, document_id, seq, "
                    "heading_path, start_char, prompt_text, fts, embedding) "
                    "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::vector)",
                    (
                        project_id,
                        c.passage_id,
                        c.document_id,
                        int(c.id.rsplit("#", 1)[1]),
                        json.dumps(list(c.heading_path), ensure_ascii=False),
                        c.start,
                        c.prompt_text(),
                        " ".join(tokenize(c.text)),
                        _vector_literal(vectors[i]) if vectors is not None else None,
                    ),
                )
            self._bump(cur, project_id)

    def remove_document(self, project_id: str, document_id: str) -> None:
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM kb_chunks WHERE project_id = %s AND document_id = %s",
                (project_id, document_id),
            )
            self._bump(cur, project_id)

    def version(self, project_id: str) -> str:
        with self._conn.cursor() as cur:
            cur.execute("SELECT changes FROM kb_versions WHERE project_id = %s", (project_id,))
            row = cur.fetchone()
        return f"v{row[0] if row else 0}"

    def texts(self, project_id: str, ids: Sequence[str]) -> list[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT passage_id, prompt_text FROM kb_chunks "
                "WHERE project_id = %s AND passage_id = ANY(%s)",
                (project_id, list(ids)),
            )
            found = dict(cur.fetchall())
        missing = [i for i in ids if i not in found]
        if missing:
            raise KeyError(f"passage {missing[0]!r} is not in project {project_id!r}")
        return [found[i] for i in ids]

    def search(
        self,
        project_id: str,
        query_texts: Sequence[str],
        k: int,
        query_vector: Sequence[float] | None = None,
    ) -> list[str]:
        depth = self.settings.rrf_depth
        rankings: list[list[str]] = []
        with self._conn.cursor() as cur:
            if query_vector is not None:
                cur.execute(
                    "SELECT passage_id FROM kb_chunks WHERE project_id = %s "
                    "AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> %s::vector, passage_id LIMIT %s",
                    (project_id, _vector_literal(query_vector), depth),
                )
                rankings.append([r[0] for r in cur.fetchall()])
            terms = list(dict.fromkeys(tokenize(" ".join(query_texts))))
            if terms:
                cur.execute(
                    "SELECT passage_id FROM kb_chunks WHERE project_id = %s "
                    "AND tsv @@ to_tsquery('simple', %s) "
                    "ORDER BY ts_rank_cd(tsv, to_tsquery('simple', %s)) DESC, passage_id "
                    "LIMIT %s",
                    (project_id, " | ".join(terms), " | ".join(terms), depth),
                )
                rankings.append([r[0] for r in cur.fetchall()])
        return rrf(rankings, self.settings.rrf_k)[:k]
