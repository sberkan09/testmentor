"""Knowledge base on the server (paket 10): `api.main.build_server` wires the project index into
the orchestrator; an upload through REST makes every retrieval search again, its passage ids
reach the snapshot and the test sets that depend on them are produced again. Fake model,
in-memory store and index."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from tests.api.conftest import META, csv_bytes

DOC = (
    "# Parola politikası\n\n"
    "Kullanıcı girişi parola ile doğrulanır. Hatalı parola girişinde kullanıcı uyarılır.\n\n"
    "# Raporlar\n\n"
    "Raporlar pdf olarak dışa aktarılır ve tarihe göre sıralanır.\n"
)
USER = {"X-User": "ayse"}


def wait_idle(client: TestClient, key: str = "DEN") -> dict:
    deadline = time.monotonic() + 20
    while True:
        snap = client.get(f"/projects/{key}/snapshot").json()
        if not snap["jobs"] and all(n["status"] == "fresh" for n in snap["nodes"]):
            return snap
        assert time.monotonic() < deadline, snap["jobs"]
        time.sleep(0.05)


def nodes(snap: dict, kind: str) -> dict[str, dict]:
    return {n["ref"]["key"]: n for n in snap["nodes"] if n["ref"]["kind"] == kind}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("TESTMENTOR_FAKE_LLM", "1")
    monkeypatch.delenv("TESTMENTOR_PG_DSN", raising=False)
    from api.main import build_server

    server = build_server()
    app = create_app(server.service, kb=server.kb, static_dir=tmp_path / "yok", ping_interval_s=30)
    with TestClient(app) as c:
        r = c.post(
            "/projects",
            data={"meta": json.dumps(META)},
            files={"file": ("gereksinim.csv", csv_bytes(), "text/csv")},
            headers=USER,
        )
        assert r.status_code == 200, r.text
        yield c


def test_upload_reaches_retrieval_and_regenerates_test_sets(client):
    before = wait_idle(client)
    retrieval = nodes(before, "retrieval")
    assert retrieval and all(n["content"]["passage_ids"] == [] for n in retrieval.values())
    test_sets = {k: n["version"] for k, n in nodes(before, "test_set").items()}
    assert client.get("/projects/DEN/kb/documents").json() == []

    r = client.post(
        "/projects/DEN/kb/documents",
        files={"file": ("Parola Politikası.md", DOC.encode(), "text/markdown")},
        headers=USER,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document"]["id"] == "Parola-Politikası.md" and body["document"]["chunks"] >= 1
    assert body["seq"] > before["seq"]

    after = wait_idle(client)
    retrieval = nodes(after, "retrieval")
    assert all(n["content"]["passage_ids"] for n in retrieval.values())
    assert all(
        p.startswith("Parola-Politikası.md#")
        for n in retrieval.values()
        for p in n["content"]["passage_ids"]
    )
    regenerated = nodes(after, "test_set")
    assert all(regenerated[k]["version"] > v for k, v in test_sets.items())
    index_before = nodes(before, "kb_index")["index"]["content"]["version"]
    assert nodes(after, "kb_index")["index"]["content"]["version"] != index_before
    listed = client.get("/projects/DEN/kb/documents").json()
    assert [(d["id"], d["name"], d["added_by"]) for d in listed] == [
        ("Parola-Politikası.md", "Parola Politikası.md", "ayse")
    ]

    # removing it: retrieval empty again
    r = client.delete("/projects/DEN/kb/documents/Parola-Politikası.md", headers=USER)
    assert r.status_code == 200, r.text
    final = wait_idle(client)
    assert all(n["content"]["passage_ids"] == [] for n in nodes(final, "retrieval").values())
    assert client.get("/projects/DEN/kb/documents").json() == []


def test_upload_errors(client):
    wait_idle(client)
    r = client.post(
        "/projects/DEN/kb/documents",
        files={"file": ("a.docx", b"x", "application/zip")},
        headers=USER,
    )
    assert r.status_code == 422 and "desteklenmeyen" in r.json()["detail"]
    r = client.post("/projects/DEN/kb/documents", files={"file": ("bos.txt", b" ", "text/plain")})
    assert r.status_code == 400  # X-User required in header mode
    r = client.post(
        "/projects/YOK/kb/documents",
        files={"file": ("a.txt", b"metin", "text/plain")},
        headers=USER,
    )
    assert r.status_code == 404
    assert client.get("/projects/YOK/kb/documents").status_code == 404
    assert client.delete("/projects/DEN/kb/documents/yok.md", headers=USER).status_code == 404


def test_without_a_knowledge_base_the_endpoints_answer_404(tmp_path):
    from tests.api.fake_service import FakeProjectService

    app = create_app(FakeProjectService(ring_size=10), static_dir=tmp_path / "yok")
    with TestClient(app) as c:
        assert c.get("/projects/P/kb/documents").status_code == 404


def test_fake_model_uses_postgres_when_a_dsn_is_set(monkeypatch):
    monkeypatch.setenv("TESTMENTOR_FAKE_LLM", "1")
    monkeypatch.delenv("TESTMENTOR_PG_DSN", raising=False)
    from api.main import build_deps  # first import builds a server: in memory here

    monkeypatch.setenv("TESTMENTOR_PG_DSN", "postgresql://u@h/db")
    monkeypatch.delenv("TESTMENTOR_STORE", raising=False)
    deps = build_deps()
    assert deps.fake and deps.store == "postgres" and deps.pg_dsn == "postgresql://u@h/db"
    assert deps.embedding_dim == 48
    monkeypatch.setenv("TESTMENTOR_STORE", "memory")
    assert build_deps().store == "memory"
    monkeypatch.delenv("TESTMENTOR_STORE")
    monkeypatch.delenv("TESTMENTOR_PG_DSN")
    assert build_deps().store == "memory"
