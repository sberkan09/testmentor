"""`PgIndex` against Postgres with pgvector (paket 10): the same behaviour as `InMemoryIndex`,
the document list, the dimension check, and the server wired on Postgres (upload → retrieval
passage ids). Each test runs in its own schema. Skipped without a server
(`TESTMENTOR_TEST_DATABASE_URL` or `TESTMENTOR_PG_DSN`) or without the `vector` extension."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Iterator

import pytest

from core.kb.chunking import Chunk
from core.kb.settings import KbSettings
from services.fake_llm import FakeEmbed
from services.kb_index import InMemoryIndex, ingest_document

psycopg = pytest.importorskip("psycopg")
KB = KbSettings(chunk_tokens=40, chunk_overlap_tokens=0, top_k=4)
EMBED = FakeEmbed()


def _dsn() -> str:
    dsn = os.environ.get("TESTMENTOR_TEST_DATABASE_URL") or os.environ.get("TESTMENTOR_PG_DSN")
    if not dsn:
        pytest.skip("no Postgres (set TESTMENTOR_TEST_DATABASE_URL or TESTMENTOR_PG_DSN)")
    return dsn


@pytest.fixture
def schema_dsn() -> Iterator[str]:
    """A DSN whose search path starts at a fresh schema (dropped afterwards)."""
    dsn = _dsn()
    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres is not reachable: {exc}")
    schema = f"kbpg_{uuid.uuid4().hex[:8]}"
    try:
        try:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except psycopg.Error as exc:
            pytest.skip(f"pgvector is not available: {exc}")
        conn.execute(f"CREATE SCHEMA {schema}")
        yield psycopg.conninfo.make_conninfo(dsn, options=f"-c search_path={schema},public")
    finally:
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.close()


@pytest.fixture
def pg(schema_dsn):
    from services.kb_index_pg import PgIndex

    conn = psycopg.connect(schema_dsn, autocommit=True)
    index = PgIndex(conn, KB, dim=EMBED.dim)
    index.ensure_schema()
    index.ensure_schema()  # idempotent
    yield index
    conn.close()


def chunks(doc: str, *paras: str) -> list[Chunk]:
    return [
        Chunk(id=f"{doc}#{i}", document_id=doc, heading_path=("Bölüm",), text=t, start=i * 100)
        for i, t in enumerate(paras)
    ]


DOCS = {
    "politika.md": "# Kilitleme\n\nHesap 3 başarısız denemeden sonra 15 dakika kilitlenir.\n\n"
    "# Parola\n\nParola sıfırlama bağlantısı 30 dakika geçerlidir.\n",
    "audit.md": "# Audit\n\nEvery configuration change is logged with user and timestamp.\n\n"
    "# Export\n\nThe audit log can be exported as CSV.\n",
}
QUERIES = [
    ["kullanıcı girişi kilitlenir"],
    ["audit log export csv"],
    ["parola sıfırlama"],
    ["configuration change"],
]


async def test_same_results_as_the_in_memory_index(pg):
    memory = InMemoryIndex(KB)
    for doc, text in DOCS.items():
        a = await ingest_document(pg, "P", doc, text, EMBED, KB)
        b = await ingest_document(memory, "P", doc, text, EMBED, KB)
        assert a == b
    assert pg.documents("P") == memory.documents("P") and len(pg.documents("P")) == 2
    for q in QUERIES:
        vector = (await EMBED(q))[0]
        found = pg.search("P", q, 4, vector)
        assert found, q
        # dense ranking is exact in both; the keyword ranking differs (ts_rank_cd, not BM25),
        # so the best hit is compared, not the whole fused list
        assert found[0] in memory.search("P", q, 4, vector)
        assert pg.texts("P", found) == memory.texts("P", found)


def test_texts_versions_replace_and_remove(pg):
    assert pg.version("P") == "v0" and pg.documents("P") == {}
    pg.add("P", chunks("d", "kilitleme süresi", "parola"), [[1.0] + [0.0] * 47] * 2)
    assert pg.version("P") == "v1" and pg.documents("P") == {"d": 2}
    ids = pg.search("P", ["kilitleme"], 5)
    assert len(ids) == 1 and pg.texts("P", ids) == ["[d §Bölüm] kilitleme süresi"]
    pg.add("P", chunks("d", "yalnızca bu"), None)  # replaces the document
    assert pg.version("P") == "v2" and pg.documents("P") == {"d": 1}
    assert pg.search("P", ["kilitleme"], 5) == []
    with pytest.raises(KeyError):
        pg.texts("P", ids)
    pg.remove_document("P", "d")
    assert pg.version("P") == "v3" and pg.documents("P") == {}


def test_projects_never_see_each_other(pg):
    pg.add("P", chunks("ortak", "gizli P metni kilitleme"), [[1.0] + [0.0] * 47])
    pg.add("Q", chunks("ortak", "gizli Q metni kilitleme"), [[1.0] + [0.0] * 47])
    p = pg.search("P", ["kilitleme"], 5, [1.0] + [0.0] * 47)
    q = pg.search("Q", ["kilitleme"], 5, [1.0] + [0.0] * 47)
    assert pg.texts("P", p) == ["[ortak §Bölüm] gizli P metni kilitleme"]
    assert pg.texts("Q", q) == ["[ortak §Bölüm] gizli Q metni kilitleme"]
    pg.remove_document("P", "ortak")
    assert pg.documents("Q") == {"ortak": 1} and pg.version("Q") == "v1"


def test_a_table_of_another_dimension_is_refused(pg, schema_dsn):
    from services.kb_index_pg import PgIndex

    conn = psycopg.connect(schema_dsn, autocommit=True)
    try:
        with pytest.raises(RuntimeError, match="dimension 48"):
            PgIndex(conn, KB, dim=1024).ensure_schema()
    finally:
        conn.close()


async def test_registry_and_uploads_on_postgres(schema_dsn):
    from services.kb_documents import KbDocuments, PgRegistry, UploadSettings
    from services.kb_examples import ExamplePool
    from services.kb_index_pg import PgIndex

    conn = psycopg.connect(schema_dsn, autocommit=True)
    try:
        index = PgIndex(conn, KB, dim=EMBED.dim)
        index.ensure_schema()
        registry = PgRegistry(conn)
        registry.ensure_schema()
        calls = []
        kb = KbDocuments(
            index,
            registry,
            ExamplePool(),
            EMBED,
            KB,
            UploadSettings(),
            lambda *a: calls.append(a) or len(calls),
            clock=lambda: 5.0,
        )
        info, _ = await kb.add("P", "Politika v1.md", DOCS["politika.md"].encode(), "ayse")
        listed = kb.list("P")
        assert [(d.id, d.name, d.chunks, d.added_by, d.added_at) for d in listed] == [
            ("Politika-v1.md", "Politika v1.md", info.chunks, "ayse", 5.0)
        ]
        assert calls == [("P", "Politika-v1.md", "v1.e0", "ayse")]
        # a second process sees the same list
        other = KbDocuments(
            PgIndex(conn, KB, dim=EMBED.dim),
            PgRegistry(conn),
            ExamplePool(),
            EMBED,
            KB,
            UploadSettings(),
            lambda *a: 0,
        )
        assert other.list("P") == listed
        kb.remove("P", "Politika-v1.md", "ayse")
        assert kb.list("P") == [] and registry.get_all("P") == {}
    finally:
        conn.close()


def test_server_on_postgres_upload_reaches_retrieval(schema_dsn, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TESTMENTOR_FAKE_LLM", "1")
    monkeypatch.setenv("TESTMENTOR_PG_DSN", schema_dsn)
    monkeypatch.delenv("TESTMENTOR_STORE", raising=False)
    from api.app import create_app
    from api.main import build_server  # the module builds its own server on first import
    from tests.api.conftest import META, csv_bytes

    server = build_server()
    app = create_app(server.service, kb=server.kb, static_dir=tmp_path / "yok")
    user = {"X-User": "ayse"}

    def idle() -> dict:
        deadline = time.monotonic() + 30
        while True:
            snap = client.get("/projects/DEN/snapshot").json()
            if not snap["jobs"] and all(n["status"] == "fresh" for n in snap["nodes"]):
                return snap
            assert time.monotonic() < deadline, snap["jobs"]
            time.sleep(0.05)

    with TestClient(app) as client:
        r = client.post(
            "/projects",
            data={"meta": json.dumps(META)},
            files={"file": ("g.csv", csv_bytes(), "text/csv")},
            headers=user,
        )
        assert r.status_code == 200, r.text
        idle()
        r = client.post(
            "/projects/DEN/kb/documents",
            files={"file": ("politika.md", DOCS["politika.md"].encode(), "text/markdown")},
            headers=user,
        )
        assert r.status_code == 200, r.text
        snap = idle()
        retrieval = [n for n in snap["nodes"] if n["ref"]["kind"] == "retrieval"]
        assert retrieval and all(n["content"]["passage_ids"] for n in retrieval)
    with psycopg.connect(schema_dsn) as conn:
        assert conn.execute("SELECT count(*) FROM kb_chunks").fetchone()[0] >= 1
        assert conn.execute("SELECT count(*) FROM tm_projects").fetchone()[0] == 1
        assert conn.execute("SELECT name FROM kb_documents").fetchone()[0] == "politika.md"


# Scale changes (pilot hazırlığı, eval/kb_scale.py) ------------------------------------------


def _corpus() -> list[Chunk]:
    words = (
        "hesap parola kilit oturum rapor belge imza kayit sorgu bildirim guvenlik erisim "
        "veri yedek arsiv form alan hata mesaj sure"
    ).split()
    import random

    rng = random.Random(3)
    out: list[Chunk] = []
    for d in range(6):
        paras = [" ".join(rng.choices(words, k=rng.randint(8, 30))) for _ in range(25)]
        out += chunks(f"D{d}.md", *paras)
    return out


def test_keyword_ranking_is_the_in_memory_bm25_when_unbounded(schema_dsn):
    """No term or candidate limit: the Postgres keyword ranking is exactly `Bm25Index`."""
    from core.kb.ranking import Bm25Index
    from services.kb_index_pg import PgIndex

    conn = psycopg.connect(schema_dsn, autocommit=True)
    index = PgIndex(
        conn,
        KB,
        dim=EMBED.dim,
        keyword_max_df=1.0,
        keyword_max_terms=10**6,
        keyword_candidates=10**6,
    )
    index.ensure_schema()
    corpus = _corpus()
    for doc in sorted({c.document_id for c in corpus}):
        index.add("P", [c for c in corpus if c.document_id == doc])
    bm = Bm25Index(KB.bm25_k1, KB.bm25_b)
    for c in corpus:
        bm.add(c.passage_id, c.text)
    with conn.cursor() as cur:
        for query in ("hesap kilit parola", "rapor imza arsiv yedek", "oturum sure hata mesaj"):
            from core.kb.ranking import tokenize

            ref = [d for d, _ in bm.search(query, 20)]
            assert index._bm25(cur, "P", tokenize(query), 20) == ref, query
    conn.close()


def test_term_frequencies_follow_adds_replacements_and_removals(schema_dsn):
    """`kb_terms` equals a recount after every change, and is backfilled for chunks indexed
    before it existed."""
    from services.kb_index_pg import PgIndex

    conn = psycopg.connect(schema_dsn, autocommit=True)
    index = PgIndex(conn, KB, dim=EMBED.dim)
    index.ensure_schema()

    def recount() -> dict[str, int]:
        rows = conn.execute(
            "SELECT term, count(*) FROM (SELECT DISTINCT passage_id, "
            "unnest(string_to_array(fts, ' ')) AS term FROM kb_chunks WHERE project_id = 'P') t "
            "GROUP BY term"
        ).fetchall()
        return {t: int(n) for t, n in rows}

    def stored() -> dict[str, int]:
        rows = conn.execute("SELECT term, df FROM kb_terms WHERE project_id = 'P'").fetchall()
        return {t: int(n) for t, n in rows}

    index.add("P", chunks("a.md", "hesap kilit hesap", "parola sifirlama"))
    index.add("P", chunks("b.md", "rapor hesap"))
    assert stored() == recount() and stored()["hesap"] == 2
    index.add("P", chunks("a.md", "oturum suresi"))  # replaced
    assert stored() == recount() and stored()["hesap"] == 1 and "kilit" not in stored()
    index.remove_document("P", "b.md")
    assert stored() == recount() == {"oturum": 1, "suresi": 1}
    conn.execute("DELETE FROM kb_terms")
    conn.execute("UPDATE kb_chunks SET fts_len = NULL")
    index.ensure_schema()  # backfill
    assert stored() == recount()
    assert conn.execute("SELECT count(*) FROM kb_chunks WHERE fts_len IS NULL").fetchone()[0] == 0
    conn.close()


def test_dense_search_has_no_approximate_index(pg):
    """Exact per-project dense search: the HNSW index is dropped by `ensure_schema`."""
    rows = pg._conn.execute(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'kb_chunks'"
    ).fetchall()
    assert "kb_chunks_embedding" not in {r[0] for r in rows}
