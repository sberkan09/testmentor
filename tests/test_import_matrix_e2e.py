"""Paket 4 done test: the golden set v0 goes from a file to the matrix and the xlsx export.

csv and xlsx input -> `build_project` (fake embedding) -> `drive` (fake model) -> nothing stale
-> `matrix_rows` -> `matrix_xlsx`. No network, no model.
"""

from __future__ import annotations

import asyncio
import csv
import io

import openpyxl
import pytest

from core.invalidation import analyze
from core.matrix_view import matrix_rows
from eval.golden import load_golden
from eval.stage_driver import drive
from services.fake_llm import FakeComplete, FakeEmbed
from services.importer import build_project
from services.settings import load_stage_settings, stage_configs
from services.xlsx_export import matrix_xlsx
from worker.contracts import ColumnMapping, ImportRequest

REQS = [r for p in load_golden().projects for r in p.requirements]


def csv_bytes() -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Kimlik", "Gereksinim", "Dil"])
    for r in REQS:
        w.writerow([r.id, r.text, r.language])
    return buf.getvalue().encode("utf-8-sig")


def xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Kimlik", "Gereksinim", "Dil"])
    for r in REQS:
        ws.append([r.id, r.text, r.language])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def run(data: bytes, filename: str) -> None:
    settings = load_stage_settings()
    request = ImportRequest(
        name="Altın set",
        key="ALTIN",
        mapping=ColumnMapping(text="Gereksinim", id="Kimlik", language="Dil"),
    )
    embed = FakeEmbed()
    state = await build_project(
        request,
        data,
        filename,
        embed=embed,
        settings=settings,
        stage_configs=stage_configs(settings, model="fake", embedding_model_version="fake-e"),
    )
    assert embed.calls == 1
    driven = await drive(state, FakeComplete(settings.test_method), settings=settings, embed=embed)
    assert not driven.errors
    state = driven.state
    assert not analyze(state).stale

    rows = matrix_rows(state, settings.test_method)
    assert len(rows) == len(REQS) == 40
    testable = [r for r in rows if settings.test_method in r.methods]
    assert testable
    assert all(r.covered and r.test_case_keys and r.warning == "" for r in testable)
    assert all(r.cluster_name for r in rows)

    wb = openpyxl.load_workbook(io.BytesIO(matrix_xlsx(state, settings.test_method)))
    assert wb.sheetnames == ["Matris", "Test durumları", "Uyarılar"]
    matrix = wb["Matris"]
    assert matrix.max_row - 1 == 40
    assert matrix.freeze_panes == "A2"
    header = [c.value for c in matrix[1]]
    assert header[:2] == ["Kimlik", "Metin"]
    assert matrix.cell(row=2, column=1).value == rows[0].requirement_id
    assert wb["Test durumları"].max_row - 1 >= 40


@pytest.mark.parametrize("fmt", ["csv", "xlsx"])
def test_golden_set_to_matrix(fmt: str) -> None:
    data = csv_bytes() if fmt == "csv" else xlsx_bytes()
    asyncio.run(run(data, f"altin.{fmt}"))
