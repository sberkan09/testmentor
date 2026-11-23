"""core.importing: rows to requirements (paket 4). Pure, no files."""

from __future__ import annotations

import pytest

from core.importing import RequirementImportError, build_requirements, detect_language
from core.settings import ImportSettings
from worker.contracts import ColumnMapping

SETTINGS = ImportSettings(id_prefix="REQ-", max_requirements=5, encodings=("utf-8",))
MAP = ColumnMapping(text="Metin", id="Kimlik", language="Dil", source="Kaynak")


def test_mapping_and_fields() -> None:
    out = build_requirements(
        [{"Kimlik": "A-1", "Metin": "Sistem açılmalıdır.", "Dil": "TR", "Kaynak": "SRS 3.1"}],
        MAP,
        SETTINGS,
    )
    assert [(r.id, r.text, r.language, r.source) for r in out] == [
        ("A-1", "Sistem açılmalıdır.", "tr", "SRS 3.1")
    ]


def test_cleaning_whitespace_newlines_bullets() -> None:
    out = build_requirements(
        [{"Kimlik": "1", "Metin": "  - Sistem   rapor\r\n  üretmelidir. \n"}],
        ColumnMapping(text="Metin", id="Kimlik"),
        SETTINGS,
    )
    assert out[0].text == "Sistem rapor üretmelidir."
    bullets = build_requirements(
        [{"Metin": "• Birinci"}, {"Metin": "* İkinci"}, {"Metin": "– Üçüncü"}],
        ColumnMapping(text="Metin"),
        SETTINGS,
    )
    assert [r.text for r in bullets] == ["Birinci", "İkinci", "Üçüncü"]


def test_blank_rows_skipped_and_ids_assigned() -> None:
    out = build_requirements(
        [{"Metin": "Bir"}, {"Metin": "  "}, {}, {"Metin": "İki"}],
        ColumnMapping(text="Metin"),
        SETTINGS,
    )
    assert [r.id for r in out] == ["REQ-1", "REQ-2"]


def test_generated_id_skips_explicit_ids() -> None:
    out = build_requirements(
        [{"Kimlik": "REQ-1", "Metin": "Bir"}, {"Kimlik": "", "Metin": "İki"}],
        ColumnMapping(text="Metin", id="Kimlik"),
        SETTINGS,
    )
    assert [r.id for r in out] == ["REQ-1", "REQ-2"]


def test_duplicate_id_error_names_row() -> None:
    with pytest.raises(RequirementImportError, match="satır 3") as exc:
        build_requirements(
            [{"Kimlik": "X", "Metin": "Bir"}, {"Kimlik": "X", "Metin": "İki"}],
            ColumnMapping(text="Metin", id="Kimlik"),
            SETTINGS,
        )
    assert exc.value.row == 3


def test_empty_text_error_names_row() -> None:
    with pytest.raises(RequirementImportError, match="satır 3") as exc:
        build_requirements(
            [{"Kimlik": "A", "Metin": "Bir"}, {"Kimlik": "B", "Metin": " - "}],
            ColumnMapping(text="Metin", id="Kimlik"),
            SETTINGS,
        )
    assert exc.value.row == 3


def test_missing_text_column_error() -> None:
    with pytest.raises(RequirementImportError, match="Metin"):
        build_requirements([{"Başka": "x"}], MAP, SETTINGS)


def test_no_requirements_error() -> None:
    with pytest.raises(RequirementImportError):
        build_requirements([], ColumnMapping(text="Metin"), SETTINGS)
    with pytest.raises(RequirementImportError):
        build_requirements([{"Metin": ""}], ColumnMapping(text="Metin"), SETTINGS)


def test_limit() -> None:
    many = [{"Metin": f"Gereksinim {i}"} for i in range(6)]
    with pytest.raises(RequirementImportError, match="5"):
        build_requirements(many, ColumnMapping(text="Metin"), SETTINGS)
    assert len(build_requirements(many[:5], ColumnMapping(text="Metin"), SETTINGS)) == 5


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Sistem kullanıcı girişini kilitlemelidir.", "tr"),
        ("Rapor ve çıktı için bir ekran olmalıdır", "tr"),
        ("The system shall export the audit log as CSV.", "en"),
        ("", "en"),
    ],
)
def test_language_detection(text: str, language: str) -> None:
    assert detect_language(text) == language


def test_language_detected_when_no_column() -> None:
    out = build_requirements(
        [{"Metin": "Sistem şifreyi saklamalıdır."}, {"Metin": "The system shall log in."}],
        ColumnMapping(text="Metin"),
        SETTINGS,
    )
    assert [r.language for r in out] == ["tr", "en"]
