"""Postgres knowledge base index: pgvector (dense) and `tsvector` (keyword), fused with RRF
(docs/tasarim.md, İndeks; paket 7). Same `KbIndex` interface as `InMemoryIndex`.

Every statement filters on `project_id`. The keyword column holds the text after the same folding
as `core.kb.ranking.tokenize` (lower case, Turkish letters, no diacritics), so Turkish and
English match like in the in-memory index; ranking is `ts_rank_cd` (not BM25).

Scale (pilot hazırlığı, `eval/kb_scale.py`, 120,000 chunks in 51 projects):

- Dense search is exact per project (no HNSW index). With HNSW the planner scanned the global
  approximate index and filtered by project afterwards: 6 of 30 planted nearest chunks were missed
  in a 20,000-chunk project. The in-memory index that D9 measured is exact; a per-project scan of
  20,000 1024-d vectors takes tens of milliseconds.
- Keyword ranking is BM25 with the in-memory index's formula (`core.kb.ranking.Bm25Index`: same
  k1, b, idf and length normalisation; `kb_terms` holds the per-project document frequency,
  `fts_len` the chunk length), computed over a bounded candidate set: the chunks matching the
  query's distinctive terms (in at most `keyword_max_df` of the project's chunks, rarest first,
  at most `keyword_max_terms`), the first `keyword_candidates` by `ts_rank_cd`. Every query term
  scores. Before, all query terms were OR-ed and ranked by `ts_rank_cd`: common words matched
  nearly every chunk (2.7 s, p95 14 s at 20,000 chunks) and the top 20 shared only 15–21 % with
  BM25, the ranking D9 measured.

The connection is a `psycopg` connection with `autocommit=True` (the caller owns it). Vectors
travel as text literals, so the `pgvector` Python package is not needed; the server needs the
`vector` extension. Without it `ensure_schema` raises and the integration test skips.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from typing import Any

from core.kb.chunking import Chunk
from core.kb.ranking import rrf, tokenize
from core.kb.settings import KbSettings


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.7g}" for x in vector) + "]"


class PgIndex:
    def __init__(
        self,
        conn: Any,
        settings: KbSettings,
        *,
        dim: int,
        keyword_max_df: float = 0.2,
        keyword_max_terms: int = 32,
        keyword_candidates: int = 200,
    ) -> None:
        self._conn = conn
        self.settings = settings
        self.dim = dim
        self.keyword_max_df = keyword_max_df
        self.keyword_max_terms = keyword_max_terms
        self.keyword_candidates = keyword_candidates

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
                "CREATE INDEX IF NOT EXISTS kb_chunks_document "
                "ON kb_chunks (project_id, document_id)"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS kb_chunks_tsv ON kb_chunks USING gin (tsv)")
            cur.execute("ALTER TABLE kb_chunks ADD COLUMN IF NOT EXISTS fts_len integer")
            cur.execute(
                "UPDATE kb_chunks SET fts_len = "
                "coalesce(array_length(string_to_array(fts, ' '), 1), 0) WHERE fts_len IS NULL"
            )
            # exact per-project dense search: a global approximate index filtered by project
            # loses results (module docstring)
            cur.execute("DROP INDEX IF EXISTS kb_chunks_embedding")
            cur.execute(
                "CREATE TABLE IF NOT EXISTS kb_terms (project_id text NOT NULL, "
                "term text NOT NULL, df integer NOT NULL, PRIMARY KEY (project_id, term))"
            )
            cur.execute(
                "SELECT NOT EXISTS (SELECT 1 FROM kb_terms) AND EXISTS (SELECT 1 FROM kb_chunks)"
            )
            if cur.fetchone()[0]:  # chunks indexed before kb_terms existed
                cur.execute(
                    "INSERT INTO kb_terms (project_id, term, df) "
                    "SELECT project_id, term, count(*) FROM ("
                    "SELECT DISTINCT project_id, passage_id, unnest(string_to_array(fts, ' ')) "
                    "AS term FROM kb_chunks) t WHERE term <> '' GROUP BY project_id, term"
                )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS kb_versions ("
                "project_id text PRIMARY KEY, changes integer NOT NULL)"
            )
            # A table made earlier with another embedding model keeps its dimension
            # (`CREATE TABLE IF NOT EXISTS`): fail here, not on the first insert.
            cur.execute(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'kb_chunks'::regclass AND attname = 'embedding'"
            )
            row = cur.fetchone()
        if row is not None and row[0] > 0 and int(row[0]) != int(self.dim):
            raise RuntimeError(
                f"kb_chunks.embedding has dimension {row[0]}, the embedding model gives "
                f"{self.dim} (config/runtime.yaml embedding.dim); the table was created with "
                "another embedding model: re-index into a new database or drop kb_chunks"
            )

    @staticmethod
    def _term_counts(fts_texts: Sequence[str]) -> Counter[str]:
        counts: Counter[str] = Counter()
        for text in fts_texts:
            counts.update({t for t in text.split(" ") if t})
        return counts

    def _apply_terms(self, cur: Any, project_id: str, delta: Counter[str]) -> None:
        delta = Counter({t: n for t, n in delta.items() if n})
        if not delta:
            return
        terms = sorted(delta)
        cur.execute(
            "INSERT INTO kb_terms (project_id, term, df) "
            "SELECT %s, t, n FROM unnest(%s::text[], %s::int[]) AS u(t, n) "
            "ON CONFLICT (project_id, term) DO UPDATE SET df = kb_terms.df + EXCLUDED.df",
            (project_id, terms, [delta[t] for t in terms]),
        )
        cur.execute("DELETE FROM kb_terms WHERE project_id = %s AND df <= 0", (project_id,))

    def _removed_terms(self, cur: Any, project_id: str, document_ids: Sequence[str]) -> Counter:
        cur.execute(
            "SELECT fts FROM kb_chunks WHERE project_id = %s AND document_id = ANY(%s)",
            (project_id, list(document_ids)),
        )
        return self._term_counts([r[0] for r in cur.fetchall()])

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
        documents = sorted({c.document_id for c in chunks})
        rows = [
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
            )
            for i, c in enumerate(chunks)
        ]
        with self._conn.transaction(), self._conn.cursor() as cur:
            delta: Counter[str] = Counter()
            delta.subtract(self._removed_terms(cur, project_id, documents))
            cur.execute(
                "DELETE FROM kb_chunks WHERE project_id = %s AND document_id = ANY(%s)",
                (project_id, documents),
            )
            cur.executemany(
                "INSERT INTO kb_chunks (project_id, passage_id, document_id, seq, "
                "heading_path, start_char, prompt_text, fts, embedding, fts_len) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::vector, %s)",
                [(*r, len(r[7].split())) for r in rows],
            )
            delta.update(self._term_counts([r[7] for r in rows]))
            self._apply_terms(cur, project_id, delta)
            self._bump(cur, project_id)

    def remove_document(self, project_id: str, document_id: str) -> None:
        with self._conn.transaction(), self._conn.cursor() as cur:
            delta: Counter[str] = Counter()
            delta.subtract(self._removed_terms(cur, project_id, [document_id]))
            cur.execute(
                "DELETE FROM kb_chunks WHERE project_id = %s AND document_id = %s",
                (project_id, document_id),
            )
            self._apply_terms(cur, project_id, delta)
            self._bump(cur, project_id)

    def version(self, project_id: str) -> str:
        with self._conn.cursor() as cur:
            cur.execute("SELECT changes FROM kb_versions WHERE project_id = %s", (project_id,))
            row = cur.fetchone()
        return f"v{row[0] if row else 0}"

    def documents(self, project_id: str) -> dict[str, int]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT document_id, count(*) FROM kb_chunks WHERE project_id = %s "
                "GROUP BY document_id ORDER BY document_id",
                (project_id,),
            )
            return {d: int(n) for d, n in cur.fetchall()}

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
            keyword = self._bm25(cur, project_id, tokenize(" ".join(query_texts)), depth)
            if keyword:
                rankings.append(keyword)
        return rrf(rankings, self.settings.rrf_k)[:k]

    def _bm25(self, cur: Any, project_id: str, tokens: Sequence[str], depth: int) -> list[str]:
        """Up to `depth` passage ids by BM25 (positive scores, best first, ties by id)."""
        query = list(dict.fromkeys(tokens))
        if not query:
            return []
        cur.execute(
            "SELECT count(*), coalesce(sum(fts_len), 0) FROM kb_chunks WHERE project_id = %s",
            (project_id,),
        )
        n_docs, total = (int(x) for x in cur.fetchone())
        if not n_docs:
            return []
        cur.execute(
            "SELECT term, df FROM kb_terms WHERE project_id = %s AND term = ANY(%s)",
            (project_id, sorted(set(query))),
        )
        df = {t: int(n) for t, n in cur.fetchall()}
        terms = self._distinctive(df, n_docs)
        if not terms:
            return []
        tsq = " | ".join(terms)
        cur.execute(
            "SELECT passage_id, fts, fts_len FROM kb_chunks WHERE project_id = %s "
            "AND tsv @@ to_tsquery('simple', %s) "
            "ORDER BY ts_rank_cd(tsv, to_tsquery('simple', %s)) DESC, passage_id LIMIT %s",
            (project_id, tsq, tsq, self.keyword_candidates),
        )
        k1, b = self.settings.bm25_k1, self.settings.bm25_b
        avg = (total / n_docs) or 1.0
        idf = {
            t: math.log(1.0 + (n_docs - n + 0.5) / (n + 0.5)) for t, n in df.items() if t in query
        }
        scores: dict[str, float] = {}
        for passage_id, fts, length in cur.fetchall():
            tf = Counter(fts.split())
            norm_len = k1 * (1.0 - b + b * (length or 0) / avg)
            score = sum(
                w * tf[t] * (k1 + 1.0) / (tf[t] + norm_len) for t, w in idf.items() if tf[t]
            )
            if score > 0:
                scores[passage_id] = score
        return [p for p, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:depth]]

    def _distinctive(self, df: dict[str, int], n_docs: int) -> list[str]:
        limit = max(1, int(self.keyword_max_df * n_docs))
        rare = sorted((n, t) for t, n in df.items() if n <= limit)
        return [t for _, t in rare[: self.keyword_max_terms]]
