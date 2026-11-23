"""The API on the real orchestrator after a restart (review findings 1 and 8): stored projects
load on the first request inside the server's event loop, the service is only called there,
and a client ahead of the server gets a snapshot."""

from __future__ import annotations

import asyncio
import json
import time

from fastapi.testclient import TestClient

from api.app import create_app
from tests.worker.helpers import project
from tests.worker.helpers import service as make_service
from worker.store import MemoryProjectStore


def stored_project_with_pending_work() -> MemoryProjectStore:
    """A first process imports project P and stops before its jobs ran."""
    store = MemoryProjectStore()

    async def first_process() -> None:
        svc = make_service(store)
        await svc.add_project(project(), "Örnek portal")
        assert not svc.runtime("P").idle()
        await svc.close()

    asyncio.run(first_process())
    return store


def test_first_requests_after_a_restart_load_the_stored_projects(tmp_path):
    store = stored_project_with_pending_work()
    app = create_app(make_service(store), static_dir=tmp_path / "yok", ping_interval_s=30)
    with TestClient(app) as client:
        r = client.get("/projects")
        assert r.status_code == 200, r.text
        assert r.json() == [{"id": "P", "name": "Örnek portal"}]
        r = client.get("/projects/P/snapshot")
        assert r.status_code == 200, r.text
        r = client.post(
            "/projects/P/locks",
            json={"ref": {"kind": "requirement", "key": "R1"}},
            headers={"X-User": "ayse"},
        )
        assert r.status_code == 200, r.text
        assert client.get("/projects/P/snapshot").json()["locks"] == {"requirement:R1": "ayse"}
        # The queued work of the first process runs on the server's loop.
        deadline = time.monotonic() + 20
        while True:
            snap = client.get("/projects/P/snapshot").json()
            if not snap["jobs"] and all(n["status"] == "fresh" for n in snap["nodes"]):
                break
            assert time.monotonic() < deadline, snap["jobs"]
            time.sleep(0.05)
        assert all(row["covered"] for row in snap["matrix"])
        assert client.get("/projects/P/matrix.xlsx").content[:2] == b"PK"


def test_websocket_with_a_future_seq_gets_a_snapshot(tmp_path):
    store = stored_project_with_pending_work()
    app = create_app(make_service(store), static_dir=tmp_path / "yok", ping_interval_s=30)
    with TestClient(app) as client:
        seq = client.get("/projects/P/snapshot").json()["seq"]
        with client.websocket_connect(f"/projects/P/events?after={seq + 100_000}&user=ayse") as ws:
            first = json.loads(ws.receive_text())
        assert first["type"] == "snapshot"
        assert first["snapshot"]["seq"] >= seq
