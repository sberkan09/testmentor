"""Paket 11: the server's example pool follows the pinned (approved or edited) test cases.

Pinning a case adds it to the pool without regenerating anything; a retrieval that runs again
(here: after a document upload) then selects it, except in the case's own cluster; unpinning
removes it. After a restart (simulated: the in-memory pool emptied) the first retrieval rebuilds
the pool before selecting, so the selections do not change. Fake model, in-memory store and
index, `kb.examples: 4` set here (the config default follows D10)."""

from __future__ import annotations

import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from tests.api.conftest import META, csv_bytes
from tests.api.test_kb_documents import DOC, USER, nodes, wait_idle


@pytest.fixture
def server_client(monkeypatch, tmp_path):
    monkeypatch.setenv("TESTMENTOR_FAKE_LLM", "1")
    monkeypatch.delenv("TESTMENTOR_PG_DSN", raising=False)
    from api.main import build_deps, build_server

    deps = build_deps()
    kb = deps.settings.kb.model_copy(update={"examples": 4})
    deps = dataclasses.replace(deps, settings=deps.settings.model_copy(update={"kb": kb}))
    server = build_server(deps)
    app = create_app(server.service, kb=server.kb, static_dir=tmp_path / "yok", ping_interval_s=30)
    with TestClient(app) as c:
        r = c.post(
            "/projects",
            data={"meta": json.dumps(META)},
            files={"file": ("gereksinim.csv", csv_bytes(), "text/csv")},
            headers=USER,
        )
        assert r.status_code == 200, r.text
        yield server, c


def command(client: TestClient, body: dict) -> dict:
    r = client.post("/projects/DEN/commands", json={"command": body}, headers=USER)
    assert r.status_code == 200, r.text
    return r.json()


def test_pinned_case_enters_the_pool_without_regenerating(server_client):
    server, client = server_client
    before = wait_idle(client)
    pool = server.kb.pool
    assert pool.entries("DEN") == {}
    case = next(n for n in before["nodes"] if n["ref"]["kind"] == "test_case")
    key = case["ref"]["key"]
    own_cluster = key.split(":", 1)[0]
    sets_before = {k: n["version"] for k, n in nodes(before, "test_set").items()}

    command(client, {"type": "pin", "node": case["ref"]})
    assert set(pool.entries("DEN")) == {key}
    after_pin = wait_idle(client)
    assert {k: n["version"] for k, n in nodes(after_pin, "test_set").items()} == sets_before

    # an edit is a new example text (same key, new example key)
    old_example = pool.entries("DEN")[key].example_key
    command(
        client,
        {
            "type": "edit_test_case",
            "case": key,
            "content": dict(case["content"], title=case["content"]["title"] + " (düzeltildi)"),
        },
    )
    assert pool.entries("DEN")[key].example_key != old_example

    # a retrieval that runs again selects it, except in the case's own cluster
    r = client.post(
        "/projects/DEN/kb/documents",
        files={"file": ("politika.md", DOC.encode(), "text/markdown")},
        headers=USER,
    )
    assert r.status_code == 200, r.text
    after = wait_idle(client)
    example = pool.entries("DEN")[key].example_key
    for cluster, n in nodes(after, "retrieval").items():
        keys = n["content"].get("example_keys", [])  # empty lists are left out of the view
        if cluster == own_cluster:
            assert example not in keys
        else:
            assert keys == [example]

    # restart: the pool lives in memory; the next retrieval rebuilds it from the pinned cases
    selected = {
        c: n["content"].get("example_keys", []) for c, n in nodes(after, "retrieval").items()
    }
    pool._projects.clear()
    server.service._synced.clear()
    r = client.post(
        "/projects/DEN/kb/documents",
        files={"file": ("ek.md", b"# Ek\n\nRaporlar haftalik alinir.\n", "text/markdown")},
        headers=USER,
    )
    assert r.status_code == 200, r.text
    again = wait_idle(client)
    assert set(pool.entries("DEN")) == {key}
    assert {
        c: n["content"].get("example_keys", []) for c, n in nodes(again, "retrieval").items()
    } == selected

    command(client, {"type": "unpin", "node": case["ref"]})
    assert pool.entries("DEN") == {}


def test_move_stays_incremental_with_examples_and_a_pinned_case_elsewhere(monkeypatch, tmp_path):
    """Paket 5's criterion with examples on: a pinned case in a third cluster changes the example
    selection of both clusters of a move, and still the move costs 1 incremental call and 2 label
    calls (the left set is pruned without a call)."""
    import collections

    monkeypatch.setenv("TESTMENTOR_FAKE_LLM", "1")
    monkeypatch.delenv("TESTMENTOR_PG_DSN", raising=False)
    from api.main import build_deps, build_server

    deps = build_deps()
    kb = deps.settings.kb.model_copy(update={"examples": 4})
    deps = dataclasses.replace(deps, settings=deps.settings.model_copy(update={"kb": kb}))
    server = build_server(deps)
    fake = deps.complete
    app = create_app(server.service, kb=server.kb, static_dir=tmp_path / "yok", ping_interval_s=30)
    with TestClient(app) as client:
        r = client.post(
            "/projects",
            data={"meta": json.dumps(META)},
            files={"file": ("gereksinim.csv", csv_bytes(), "text/csv")},
            headers=USER,
        )
        assert r.status_code == 200, r.text
        snap = wait_idle(client)
        members = {k: n["content"]["members"] for k, n in nodes(snap, "cluster").items()}
        src, dst, third = sorted(members, key=lambda k: (-len(members[k]), k))[:3]
        case = next(
            n
            for n in snap["nodes"]
            if n["ref"]["kind"] == "test_case" and n["ref"]["key"].startswith(third + ":")
        )
        command(client, {"type": "pin", "node": case["ref"]})
        wait_idle(client)
        before = len(fake.requests)
        command(
            client,
            {"type": "move_requirement", "requirement": members[src][-1], "to_cluster": dst},
        )
        after = wait_idle(client)
        calls = collections.Counter(r.schema.__name__ for r in fake.requests[before:])
        assert calls == {"TestCaseDelta": 1, "ClusterLabel": 2}
        example = server.kb.pool.entries("DEN")[case["ref"]["key"]].example_key
        retrieval = nodes(after, "retrieval")
        assert example in retrieval[dst]["content"].get("example_keys", [])


async def test_a_failed_pool_sync_does_not_fail_the_committed_command():
    """The embedding service failing after a pin: the command still answers accepted, the
    project is left unsynced and the next selection syncs again."""
    from types import SimpleNamespace

    from core.nodes import RequirementContent
    from services.kb_example_sync import ExampleSyncingService
    from services.kb_examples import ExamplePool
    from worker.contracts import CommandResult

    class Inner:
        state = None

        async def command(self, project_id, request, actor):
            return CommandResult(accepted=True, seq=1)

        def runtime(self, project_id):
            return SimpleNamespace(state=self.state)

    calls = []

    async def broken(texts):
        raise RuntimeError("embedding down")

    syncing = ExampleSyncingService(Inner(), ExamplePool(), broken)

    async def failing_sync(project_id):
        calls.append(project_id)
        raise RuntimeError("embedding down")

    syncing.sync = failing_sync  # type: ignore[method-assign]
    result = await syncing.command("P", None, "ayse")  # type: ignore[arg-type]
    assert result.accepted and calls == ["P"]
    assert "P" not in syncing._synced

    async def select(members):
        return ["x"]

    selected = syncing.synced_selection("P", select)
    assert selected is not None
    with pytest.raises(RuntimeError):  # retried before the next selection
        await selected([RequirementContent(id="R1", text="t")])
    assert calls == ["P", "P"]
