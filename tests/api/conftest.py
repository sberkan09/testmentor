from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from tests.api.fake_service import FakeProjectService

CSV_ROWS = [
    ("R1", "Sistem kullanıcı girişini parola ile doğrulamalıdır"),
    ("R2", "Sistem kullanıcı girişini parola ile doğrulamalıdır ve hatayı uyarmalıdır"),
    ("R3", "Sistem raporları pdf olarak dışa aktarmalıdır"),
    ("R4", "Sistem raporları pdf olarak dışa aktarmalıdır ve tarihe göre sıralamalıdır"),
    ("R5", "Sistem oturumu on dakika sonra kapatmalıdır"),
    ("R6", "Sistem parola değişikliğini kaydetmelidir"),
]
META = {"name": "Deneme", "key": "DEN", "mapping": {"text": "Metin", "id": "Kimlik"}}


def csv_bytes() -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Kimlik", "Metin"])
    w.writerows(CSV_ROWS)
    return buf.getvalue().encode("utf-8")


@pytest.fixture
def service() -> FakeProjectService:
    return FakeProjectService(ring_size=50)


@pytest.fixture
def client(service: FakeProjectService, tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(service, static_dir=tmp_path / "yok", ping_interval_s=30)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client: TestClient) -> dict[str, Any]:
    r = client.post(
        "/projects",
        data={"meta": json.dumps(META)},
        files={"file": ("gereksinim.csv", csv_bytes(), "text/csv")},
        headers={"X-User": "ayse"},
    )
    assert r.status_code == 200, r.text
    return r.json()
