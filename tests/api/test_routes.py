"""Routes: project list, import (csv, bad input), snapshot, xlsx download, static files."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import openpyxl
from fastapi.testclient import TestClient

from api.app import XLSX_TYPE, create_app
from tests.api.conftest import META, csv_bytes
from tests.api.fake_service import FakeProjectService


def test_projects_list_and_snapshot(client: TestClient, project: dict[str, Any]) -> None:
    assert client.get("/projects").json() == [{"id": "DEN", "name": "Deneme"}]
    snap = client.get("/projects/DEN/snapshot").json()
    assert snap == project
    assert snap["project_id"] == "DEN" and len(snap["matrix"]) == 6
    assert client.get("/projects/YOK/snapshot").status_code == 404


def test_import_errors_are_422(client: TestClient) -> None:
    files = {"file": ("g.csv", csv_bytes(), "text/csv")}
    assert client.post("/projects", data={"meta": "{bozuk"}, files=files).status_code == 422
    bad_map = dict(META, mapping={"text": "Olmayan"})
    r = client.post("/projects", data={"meta": json.dumps(bad_map)}, files=files)
    assert r.status_code == 422


def test_duplicate_project_is_422(client: TestClient, project: dict[str, Any]) -> None:
    r = client.post(
        "/projects",
        data={"meta": json.dumps(META)},
        files={"file": ("g.csv", csv_bytes(), "text/csv")},
    )
    assert r.status_code == 422


def test_matrix_xlsx(client: TestClient, project: dict[str, Any]) -> None:
    r = client.get("/projects/DEN/matrix.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(XLSX_TYPE)
    assert 'filename="DEN-matrix.xlsx"' in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames


def test_lock_and_command_need_user(client: TestClient, project: dict[str, Any]) -> None:
    ref = {"kind": "requirement", "key": "R1"}
    assert client.post("/projects/DEN/locks", json={"ref": ref}).status_code == 400


def test_move_requirement_changes_clusters(client: TestClient, project: dict[str, Any]) -> None:
    clusters = {
        n["ref"]["key"]: n["content"]["members"]
        for n in project["nodes"]
        if n["ref"]["kind"] == "cluster"
    }
    src = next((k for k, m in clusters.items() if len(m) > 1), None)
    assert src is not None and len(clusters) >= 2, clusters
    dst = next(k for k in clusters if k != src)
    req = clusters[src][0]
    r = client.post(
        "/projects/DEN/commands",
        json={"command": {"type": "move_requirement", "requirement": req, "to_cluster": dst}},
        headers={"X-User": "ayse"},
    )
    assert r.status_code == 200, r.text
    snap = client.get("/projects/DEN/snapshot").json()
    row = next(m for m in snap["matrix"] if m["requirement_id"] == req)
    assert row["cluster"] == dst


def test_static_files_with_spa_fallback(service: FakeProjectService, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>uygulama</html>", encoding="utf-8")
    (tmp_path / "a.js").write_text("1", encoding="utf-8")
    with TestClient(create_app(service, static_dir=tmp_path)) as c:
        assert "uygulama" in c.get("/").text
        assert c.get("/a.js").text == "1"
        assert "uygulama" in c.get("/projeler/DEN").text  # client-side route
        assert c.get("/projects").status_code == 200  # API routes win over the static mount
