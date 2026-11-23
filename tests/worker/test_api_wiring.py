"""The API (paket 6) on the real orchestrator: `api.main.build_service` with the fake model, an
import through REST, every job finished, a command, the matrix export and event replay."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from api.app import create_app
from tests.api.conftest import META, csv_bytes


def test_api_on_the_real_service(monkeypatch, tmp_path):
    monkeypatch.setenv("TESTMENTOR_FAKE_LLM", "1")
    from api.main import build_service

    service = build_service()
    app = create_app(service, static_dir=tmp_path / "yok", ping_interval_s=30)
    with TestClient(app) as client:
        r = client.post(
            "/projects",
            data={"meta": json.dumps(META)},
            files={"file": ("gereksinim.csv", csv_bytes(), "text/csv")},
            headers={"X-User": "ayse"},
        )
        assert r.status_code == 200, r.text
        deadline = time.monotonic() + 20
        while True:
            snap = client.get("/projects/DEN/snapshot").json()
            if not snap["jobs"] and all(n["status"] == "fresh" for n in snap["nodes"]):
                break
            assert time.monotonic() < deadline, snap["jobs"]
            time.sleep(0.05)
        assert len(snap["matrix"]) == 6 and all(row["covered"] for row in snap["matrix"])
        cluster = snap["matrix"][0]["cluster"]
        other = next(row["cluster"] for row in snap["matrix"] if row["cluster"] != cluster)
        r = client.post(
            "/projects/DEN/commands",
            json={"command": {"type": "rename_cluster", "cluster": other, "name": "Raporlar"}},
            headers={"X-User": "ayse"},
        )
        assert r.status_code == 200 and r.json()["accepted"], r.text
        assert client.get("/projects/DEN/matrix.xlsx").content[:2] == b"PK"
        assert client.get("/projects").json() == [{"id": "DEN", "name": "Deneme"}]
