"""services.importer: csv / xlsx reading and `build_project` (paket 4). Fake embedding only."""

from __future__ import annotations

import asyncio
import io

import openpyxl
import pytest

from core.importing import RequirementImportError
from core.invalidation import analyze
from core.nodes import NodeKind
from services.fake_llm import FakeEmbed
from services.importer import build_project, read_rows
from services.settings import load_stage_settings, stage_configs
from worker.contracts import ColumnMapping, ImportRequest

TEXT = "Sistem, kullanıcı girişini kilitlemelidir."


def test_csv_utf8_sig() -> None:
    data = "﻿Kimlik,Metin\nA,Şifre güvenli saklanmalıdır\n".encode()
    assert read_rows(data, "x.csv", None) == [
        {"Kimlik": "A", "Metin": "Şifre güvenli saklanmalıdır"}
    ]


def test_csv_cp1254_semicolon() -> None:
    data = "Kimlik;Metin\nA;Öğrenci şifresi\nB;İşlem günlüğü\n".encode("cp1254")
    rows = read_rows(data, "x.csv", None)
    assert rows == [
        {"Kimlik": "A", "Metin": "Öğrenci şifresi"},
        {"Kimlik": "B", "Metin": "İşlem günlüğü"},
    ]


def test_csv_quoted_newline() -> None:
    data = 'Kimlik,Metin\nA,"iki\nsatır, virgüllü"\n'.encode()
    assert read_rows(data, "x.csv", None)[0]["Metin"] == "iki\nsatır, virgüllü"


def test_csv_quoted_words_inside_quoted_cell() -> None:
    # The sniffer guesses the quote character wrong on this; only the delimiter is taken from it.
    data = 'Kimlik,Metin,Dil\nK4,"izi ""eskimiş"" yap, sonra sil.",tr\n'.encode()
    assert read_rows(data, "x.csv", None) == [
        {"Kimlik": "K4", "Metin": 'izi "eskimiş" yap, sonra sil.', "Dil": "tr"}
    ]


def make_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Birinci"
    ws.append(["Kimlik", "Metin"])
    ws.append(["X", "ilk sayfa"])
    second = wb.create_sheet("Gereksinimler")
    second.append(["Kimlik", "Metin", "Not"])
    second.append([1, TEXT, None])
    second.append([2.0, "ikinci", 3.5])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_xlsx_first_and_named_sheet() -> None:
    data = make_xlsx()
    assert read_rows(data, "x.xlsx", None) == [{"Kimlik": "X", "Metin": "ilk sayfa"}]
    rows = read_rows(data, "x.xlsx", "Gereksinimler")
    assert rows[0] == {"Kimlik": "1", "Metin": TEXT, "Not": ""}
    assert rows[1] == {"Kimlik": "2", "Metin": "ikinci", "Not": "3.5"}
    with pytest.raises(RequirementImportError, match="Yok"):
        read_rows(data, "x.xlsx", "Yok")


def test_unsupported_extension() -> None:
    with pytest.raises(RequirementImportError):
        read_rows(b"x", "x.docx", None)


def request(**kw: object) -> ImportRequest:
    base: dict[str, object] = {
        "name": "Örnek",
        "key": "ORN",
        "mapping": ColumnMapping(text="Metin", id="Kimlik"),
    }
    return ImportRequest.model_validate({**base, **kw})


def build(n: int = 12, **kw: object):  # type: ignore[no-untyped-def]
    lines = ["Kimlik,Metin"] + [
        f"R{i:02d},Sistem {i} numaralı {'rapor' if i % 2 else 'kayıt'} işlemini tamamlamalıdır."
        for i in range(1, n + 1)
    ]
    settings = load_stage_settings()
    embed = FakeEmbed()
    state = asyncio.run(
        build_project(
            request(**kw),
            "\n".join(lines).encode(),
            "x.csv",
            embed=embed,
            settings=settings,
            stage_configs=stage_configs(settings, model="fake", embedding_model_version="fake-e"),
        )
    )
    return state, embed


def test_build_project_state() -> None:
    state, embed = build()
    assert embed.calls == 1
    assert state.project_id == "ORN"
    ids = state.keys_of(NodeKind.REQUIREMENT)
    assert len(ids) == 12
    clusters = state.keys_of(NodeKind.CLUSTER)
    assert clusters[0] == "C001"
    placed = [m for c in clusters for m in state.members(c)]
    assert sorted(placed) == sorted(ids)
    stale = analyze(state).stale
    assert not {r for r in stale if r.kind in (NodeKind.EMBEDDING, NodeKind.CLUSTERING)}
    assert {r.kind for r in stale} >= {NodeKind.METHOD, NodeKind.TEST_SET}


def test_card_defaults_and_overrides() -> None:
    state, _ = build()
    card = state.node(_ref(NodeKind.PROJECT_CARD, "card")).content
    assert card.text == "Project: Örnek (ORN)"  # type: ignore[union-attr]
    assert [m.name for m in card.methods][:2] == ["Test", "Analiz"]  # type: ignore[union-attr]
    state, _ = build(card_text="Kart", methods=[{"name": "Test", "criterion": "c"}])
    card = state.node(_ref(NodeKind.PROJECT_CARD, "card")).content
    assert card.text == "Kart" and [m.name for m in card.methods] == ["Test"]  # type: ignore[union-attr]


def _ref(kind: NodeKind, key: str):  # type: ignore[no-untyped-def]
    from core.nodes import PROJECT_CARD_KEY, NodeRef

    return NodeRef(kind=kind, key=PROJECT_CARD_KEY if kind is NodeKind.PROJECT_CARD else key)
