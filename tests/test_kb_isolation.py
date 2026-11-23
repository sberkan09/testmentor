"""Paket 7 done test: a project's chunks and examples never reach another project's searches or
prompts (docs/tasarim.md, Yalıtım).

Two projects get the same document ids and almost the same texts and the same requirements, so a
missing `project_id` filter would surface the other project's chunks: only a marker word differs.
The real retrieval and test set producers run (fake model); the assertions read the passages
layer of the prompts the model received. A leaky index must make the check fail, otherwise it
proves nothing.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import pytest

from core.kb.chunking import Chunk
from core.kb.settings import KbSettings
from core.nodes import NodeKind, RetrievalContent, ref
from core.prompts import render_example
from services.fake_llm import FakeEmbed
from services.kb_examples import ExamplePool, build_entry
from services.kb_index import InMemoryIndex, KbIndex, ingest_document
from services.kb_retrieve import (
    build_retrieval,
    make_example_source,
    make_select_examples,
)
from tests.stages.helpers import REQS, SETTINGS, ScriptedComplete, case_json, drive, project

KB = KbSettings(chunk_tokens=60, chunk_overlap_tokens=0, top_k=4, examples=2)
MARKERS = {"PA": "ALFAMARKER", "PB": "BETAMARKER"}
CLUSTERS = {"A": ("R1", "R2"), "B": ("R3", "R4"), "C": ("R5", "R6")}


def documents(marker: str) -> dict[str, str]:
    """Same ids and same sentences in both projects; only `marker` differs."""
    return {
        "SPEC": (
            "# Kimlik doğrulama\n\n"
            f"Kullanıcı girişi 3 başarısız denemeden sonra 15 dakika kilitlenir. {marker} kuralı.\n\n"
            f"Parola sıfırlama bağlantısı 30 dakika geçerlidir. {marker} kuralı.\n\n"
            "# Günlükleme\n\n"
            f"Her yapılandırma değişikliği kullanıcı ve zaman damgasıyla günlüğe yazılır. {marker}.\n\n"
            f"Denetim günlüğü CSV olarak dışa aktarılır. {marker}.\n"
        ),
        "GUIDE": (
            "# Performans\n\n"
            f"Rapor ekranı 2 saniye içinde açılır, eşzamanlı 200 kullanıcı desteklenir. {marker}.\n"
        ),
    }


class LeakyIndex(InMemoryIndex):
    """Ignores the project: everything lives in one shared project. The isolation check must
    notice."""

    def add(self, project_id, chunks, vectors=None):
        super().add("shared", chunks, vectors)

    def search(self, project_id, query_texts, k, query_vector=None):
        return super().search("shared", query_texts, k, query_vector)

    def texts(self, project_id, ids):
        return super().texts("shared", ids)


@contextmanager
def pg_index() -> Iterator[KbIndex]:
    psycopg = pytest.importorskip("psycopg")
    dsn = os.environ.get("TESTMENTOR_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("no Postgres (set TESTMENTOR_TEST_DATABASE_URL)")
    from services.kb_index_pg import PgIndex

    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres is not reachable: {exc}")
    schema = f"kbtest_{uuid.uuid4().hex[:8]}"
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except psycopg.Error as exc:
                pytest.skip(f"pgvector is not available: {exc}")
            cur.execute(f"CREATE SCHEMA {schema}")
            cur.execute(f"SET search_path TO {schema}, public")
        index = PgIndex(conn, KB, dim=FakeEmbed().dim)
        index.ensure_schema()
        yield index
    finally:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.close()


async def exercise(index: KbIndex, pool: ExamplePool) -> dict[str, dict]:
    """Ingests both projects, produces retrieval and test sets for each with the real producers
    and returns, per project, the retrieval content, its own chunks and the prompts sent."""
    embed = FakeEmbed()
    out: dict[str, dict] = {}
    own: dict[str, list[Chunk]] = {}
    for pid, marker in MARKERS.items():
        own[pid] = []
        for doc_id, text in documents(marker).items():
            own[pid] += await ingest_document(index, pid, doc_id, text, embed, KB)
        # one pooled example per project, covering the first requirement
        case = _case(marker)
        entry = await build_entry(f"{pid}:TC-1", case, [REQS["R1"][1]], embed)
        pool.add(pid, [entry])
    for pid, marker in MARKERS.items():
        retrieve, passages = build_retrieval(index, pid, embed, KB)
        complete = ScriptedComplete()
        run = await drive(
            project(REQS, CLUSTERS),
            complete,
            real={NodeKind.RETRIEVAL, NodeKind.TEST_SET},
            retrieve=retrieve,
            passages=passages,
            select_examples=make_select_examples(pool, pid, embed, KB.examples),
            example_texts=make_example_source(pool, pid),
        )
        assert not run.failed(), run.failed()
        retrieval = {
            c: run.state.node(ref(NodeKind.RETRIEVAL, c)).content for c in CLUSTERS
        }
        out[pid] = {
            "retrieval": retrieval,
            "chunks": own[pid],
            "prompts": [r.messages[-1]["content"] for r in complete.of(NodeKind.TEST_SET)],
        }
    return out


def _case(marker: str):
    from core.nodes import TestCaseContent

    d = case_json("R1", cid="TC-1")
    d["title"] = f"{marker} kilitleme örneği"
    return TestCaseContent.model_validate(d)


def assert_isolated(result: dict[str, dict], index: KbIndex, pool: ExamplePool) -> None:
    for pid, data in result.items():
        other = next(p for p in result if p != pid)
        own_ids = {c.passage_id for c in data["chunks"]}
        other_ids = {c.passage_id for c in result[other]["chunks"]}
        assert own_ids.isdisjoint(other_ids)
        for cluster, ret in data["retrieval"].items():
            assert isinstance(ret, RetrievalContent)
            assert ret.passage_ids, f"{pid}/{cluster}: nothing retrieved (the test would be empty)"
            assert set(ret.passage_ids) <= own_ids, f"{pid}/{cluster} got another project's chunk"
            assert ret.example_keys and all(k.startswith(f"{pid}:") for k in ret.example_keys)
        assert len(data["prompts"]) == len(CLUSTERS)
        for prompt in data["prompts"]:
            layer4 = prompt[prompt.index("# Retrieved passages") : prompt.index("# Requirements")]
            assert MARKERS[pid] in layer4
            assert MARKERS[other] not in prompt
            assert "# Project examples" in layer4 and f"{MARKERS[pid]} kilitleme" in layer4
        # the other project's ids and examples are not readable through this project
        with pytest.raises(KeyError):
            index.texts(pid, sorted(other_ids)[:1])
        foreign = pool.select(other, [1.0] * FakeEmbed().dim, 1)
        with pytest.raises(KeyError):
            pool.texts(pid, foreign)


async def test_in_memory_index_isolates_projects():
    index, pool = InMemoryIndex(KB), ExamplePool()
    assert_isolated(await exercise(index, pool), index, pool)


async def test_a_leaky_index_fails_the_check():
    index, pool = LeakyIndex(KB), ExamplePool()
    result = await exercise(index, pool)
    with pytest.raises(AssertionError, match="another project|MARKER|disjoint"):
        assert_isolated(result, index, pool)


async def test_pgvector_index_isolates_projects():
    with pg_index() as index:
        pool = ExamplePool()
        assert_isolated(await exercise(index, pool), index, pool)


async def test_every_retrieved_id_resolves_to_a_prompt_text_of_its_own_project():
    index, pool = InMemoryIndex(KB), ExamplePool()
    result = await exercise(index, pool)
    for pid, data in result.items():
        by_id = {c.passage_id: c.prompt_text() for c in data["chunks"]}
        ids: Sequence[str] = [i for r in data["retrieval"].values() for i in r.passage_ids]
        assert index.texts(pid, ids) == [by_id[i] for i in ids]


def test_example_text_is_what_the_prompt_shows():
    case = _case("ALFAMARKER")
    assert "Test case:" in render_example(["Gereksinim metni."], case)
    assert SETTINGS.test_method  # the shared fixture is importable
