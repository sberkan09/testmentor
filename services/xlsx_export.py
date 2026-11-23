"""Matrix export as xlsx (paket 4): sheets "Matris", "Test durumları" and "Uyarılar".

Headers are Turkish. Every text goes in as a string cell (a requirement starting with `=` stays
text, not a formula) with control characters removed (openpyxl rejects them).
"""

from __future__ import annotations

import io
import re
from collections.abc import Sequence
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from core.graph import ProjectState, case_cluster
from core.matrix_view import matrix_rows
from core.nodes import NodeKind, NodeRef, TestCaseContent

WARNING_TEXT = {
    "": "",
    "test_without_case": "Yöntemi Test olan gereksinimi kapsayan test durumu yok.",
    "case_without_test_method": "Yöntemleri Test içermeyen gereksinimi kapsayan test durumu var.",
}
_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")

MATRIX_HEADER = (
    ("Kimlik", 16),
    ("Metin", 70),
    ("Dil", 6),
    ("Öbek", 8),
    ("Öbek adı", 30),
    ("Yöntemler", 20),
    ("Test durumları", 28),
    ("Kapsandı", 10),
    ("Uyarı", 50),
)
CASE_HEADER = (
    ("Anahtar", 14),
    ("Öbek", 8),
    ("Başlık", 40),
    ("Kapsadığı gereksinimler", 24),
    ("Tip", 10),
    ("Öncelik", 10),
    ("Ön koşul", 30),
    ("Test girdisi", 30),
    ("Varsayım", 30),
    ("Adım no", 8),
    ("İşlem", 50),
    ("Beklenen sonuç", 50),
)
WARNING_HEADER = (("Kimlik", 16), ("Metin", 70), ("Uyarı", 60))


def _text(value: Any) -> Any:
    if isinstance(value, str):
        return _ILLEGAL.sub("", value)
    return value


def _sheet(ws: Worksheet, header: Sequence[tuple[str, int]], rows: Sequence[Sequence[Any]]) -> None:
    ws.append([h for h, _ in header])
    for row in rows:
        ws.append([_text(v) for v in row])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for i, (_, width) in enumerate(header, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for line in ws.iter_rows(min_row=2):
        for cell in line:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # never a formula
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"


def matrix_xlsx(state: ProjectState, test_method: str) -> bytes:
    rows = matrix_rows(state, test_method)
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Matris"
    _sheet(
        ws,
        MATRIX_HEADER,
        [
            (
                r.requirement_id,
                r.text,
                r.language,
                r.cluster,
                r.cluster_name,
                ", ".join(r.methods),
                ", ".join(r.test_case_keys),
                "Evet" if r.covered else "Hayır",
                WARNING_TEXT[r.warning],
            )
            for r in rows
        ],
    )

    case_rows: list[tuple[Any, ...]] = []
    for key in state.keys_of(NodeKind.TEST_CASE):
        content = state.node(NodeRef(kind=NodeKind.TEST_CASE, key=key)).content
        if not isinstance(content, TestCaseContent):
            continue
        head = (
            key,
            case_cluster(key),
            content.title,
            ", ".join(content.covers),
            content.type,
            content.priority,
            content.preconditions,
            content.test_inputs,
            content.assumptions,
        )
        for step in content.steps:
            case_rows.append((*head, step.no, step.action, step.expected))
    _sheet(wb.create_sheet("Test durumları"), CASE_HEADER, case_rows)

    _sheet(
        wb.create_sheet("Uyarılar"),
        WARNING_HEADER,
        [(r.requirement_id, r.text, WARNING_TEXT[r.warning]) for r in rows if r.warning],
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
