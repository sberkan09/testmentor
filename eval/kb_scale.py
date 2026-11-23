"""PgIndex at scale (pilot hazırlığı): ingest speed, search latency, isolation and dense
correctness on a synthetic multi-project table. No model, no network: random unit vectors and
generated text; runs against a pgvector Postgres (`TESTMENTOR_PG_DSN`).

    python -m eval.kb_scale --dsn postgresql://... [--projects 50] [--chunks 2000] [--big 20000]

Chunks are real text: the writer-visible golden v1 corpus documents (KDH, ETC; `python -m
eval.corpus fetch` cache) cut at the configured chunk size, copied under new document ids to reach
`--chunks` per project (one project gets `--big`). Vectors are random unit vectors (dense cost
depends on the row count, not on the text). Queries are real cluster retrievals: the member
texts of a golden v1 reference cluster as the keyword query, with a query vector planted near one
chunk: that chunk must come first among the dense results, and every result must belong to the
project. The tables are created in a fresh schema and dropped at the end.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np

from core.kb.chunking import Chunk
from core.kb.settings import KbSettings
from services.kb_index_pg import PgIndex, _vector_literal


def unit(rng: np.random.Generator, dim: int) -> np.ndarray:
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def corpus_chunks(settings: KbSettings) -> list[Chunk]:
    from core.kb.chunking import chunk_document
    from eval.kb_corpus import load_corpus

    out: list[Chunk] = []
    for project in ("KDH", "ETC"):
        for doc_id, text in load_corpus(project):
            out += chunk_document(
                doc_id,
                text,
                chunk_tokens=settings.chunk_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
    return out


def chunks_for(base: list[Chunk], n: int) -> list[Chunk]:
    """`n` chunks: copies of the corpus chunks under document ids `C<copy>-<document>`."""
    out: list[Chunk] = []
    copy = 0
    while len(out) < n:
        for c in base[: n - len(out)]:
            doc = f"C{copy}-{c.document_id}"
            out.append(
                Chunk(
                    id=f"{doc}#{c.id.rsplit('#', 1)[1]}",
                    document_id=doc,
                    heading_path=c.heading_path,
                    text=c.text,
                    start=c.start,
                )
            )
        copy += 1
    return out


def cluster_queries() -> list[list[str]]:
    from eval.golden_v1 import load_golden_v1

    out = []
    for p in load_golden_v1().projects:
        texts = {r.id: r.text for r in p.requirements}
        out += [[texts[m] for m in members] for members in p.reference_clusters()]
    return out


def measure(
    index: PgIndex,
    project: str,
    vectors: np.ndarray,
    chunks: list[Chunk],
    rng: random.Random,
    nprng: np.random.Generator,
    queries: int,
    k: int,
    clusters: list[list[str]],
) -> dict[str, Any]:
    latencies, dense_ms, keyword_ms, first_ok, foreign = [], [], [], 0, 0
    from core.kb.ranking import tokenize

    own = {c.passage_id for c in chunks}
    for _ in range(queries):
        target = rng.randrange(len(chunks))
        q = vectors[target] + 0.05 * unit(nprng, vectors.shape[1])
        q = q / np.linalg.norm(q)
        members = rng.choice(clusters)
        t = time.perf_counter()
        ids = index.search(project, members, k, query_vector=q.tolist())
        latencies.append(time.perf_counter() - t)
        foreign += sum(1 for i in ids if i not in own)
        with index._conn.cursor() as cur:  # the two rankings apart (same SQL as PgIndex.search)
            t = time.perf_counter()
            cur.execute(
                "SELECT passage_id FROM kb_chunks WHERE project_id = %s AND embedding IS NOT NULL "
                "ORDER BY embedding <=> %s::vector, passage_id LIMIT %s",
                (project, _vector_literal(q.tolist()), index.settings.rrf_depth),
            )
            dense = [r[0] for r in cur.fetchall()]
            dense_ms.append((time.perf_counter() - t) * 1000)
            first_ok += dense[0] == chunks[target].passage_id
            terms = " | ".join(dict.fromkeys(tokenize(" ".join(members))))
            t = time.perf_counter()
            cur.execute(
                "SELECT passage_id FROM kb_chunks WHERE project_id = %s "
                "AND tsv @@ to_tsquery('simple', %s) "
                "ORDER BY ts_rank_cd(tsv, to_tsquery('simple', %s)) DESC, passage_id LIMIT %s",
                (project, terms, terms, index.settings.rrf_depth),
            )
            cur.fetchall()
            keyword_ms.append((time.perf_counter() - t) * 1000)
    ms = sorted(x * 1000 for x in latencies)
    return {
        "project": project,
        "chunks": len(chunks),
        "queries": queries,
        "p50_ms": round(statistics.median(ms), 1),
        "p95_ms": round(ms[int(0.95 * (len(ms) - 1))], 1),
        "max_ms": round(ms[-1], 1),
        "dense_p50_ms": round(statistics.median(dense_ms), 1),
        "keyword_p50_ms": round(statistics.median(keyword_ms), 1),
        "dense_first_ok": first_ok,
        "foreign_results": foreign,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--projects", type=int, default=50)
    ap.add_argument("--chunks", type=int, default=2000)
    ap.add_argument("--big", type=int, default=20000)
    ap.add_argument("--dim", type=int, default=1024)
    ap.add_argument("--queries", type=int, default=40)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    import psycopg

    schema = f"kbscale_{int(time.time())}"
    conn = psycopg.connect(args.dsn, autocommit=True)
    conn.execute(f"CREATE SCHEMA {schema}")
    conn.execute(f"SET search_path TO {schema}, public")
    rng, nprng = random.Random(7), np.random.default_rng(7)
    settings = KbSettings(top_k=4)
    base = corpus_chunks(settings)
    clusters = cluster_queries()
    print(f"derlem: {len(base)} parça; sorgu öbekleri: {len(clusters)}", flush=True)
    index = PgIndex(conn, settings, dim=args.dim)
    index.ensure_schema()
    result: dict[str, Any] = {
        "params": vars(args) | {"out": str(args.out)},
        "ingest": [],
        "search": [],
    }
    data: dict[str, tuple[np.ndarray, list[Chunk]]] = {}
    try:
        names = [f"P{i:03d}" for i in range(args.projects)] + ["BIG"]
        total_t, total_n = 0.0, 0
        for name in names:
            n = args.big if name == "BIG" else args.chunks
            chunks = chunks_for(base, n)
            vectors = np.stack([unit(nprng, args.dim) for _ in range(n)])
            t = time.perf_counter()
            docs: dict[str, list[int]] = {}  # one add per document, like uploads
            for j, c in enumerate(chunks):
                docs.setdefault(c.document_id, []).append(j)
            for doc_ids in docs.values():
                index.add(
                    name, [chunks[i] for i in doc_ids], [vectors[i].tolist() for i in doc_ids]
                )
            dt = time.perf_counter() - t
            total_t, total_n = total_t + dt, total_n + n
            if name in ("P000", "BIG"):
                result["ingest"].append(
                    {
                        "project": name,
                        "chunks": n,
                        "seconds": round(dt, 1),
                        "chunks_per_s": round(n / dt, 1),
                    }
                )
                data[name] = (vectors, chunks)
            print(f"{name}: {n} parça, {dt:.1f} sn", flush=True)
        result["ingest_total"] = {
            "chunks": total_n,
            "seconds": round(total_t, 1),
            "chunks_per_s": round(total_n / total_t, 1),
        }
        conn.execute("ANALYZE kb_chunks")
        for name in ("P000", "BIG"):
            vectors, chunks = data[name]
            result["search"].append(
                measure(
                    index, name, vectors, chunks, rng, nprng, args.queries, settings.top_k, clusters
                )
            )
            print(json.dumps(result["search"][-1], ensure_ascii=False), flush=True)
        with conn.cursor() as cur:
            cur.execute(
                "EXPLAIN SELECT passage_id FROM kb_chunks WHERE project_id = 'BIG' "
                "AND embedding IS NOT NULL ORDER BY embedding <=> %s::vector, passage_id LIMIT 50",
                (_vector_literal(unit(nprng, args.dim).tolist()),),
            )
            result["dense_plan"] = [r[0].split("'[")[0] for r in cur.fetchall()]
            cur.execute("SELECT pg_size_pretty(pg_total_relation_size('kb_chunks'))")
            result["table_size"] = cur.fetchone()[0]
    finally:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.close()
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
