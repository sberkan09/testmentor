"""Import rows to requirements (paket 4). Pure: no files, no HTTP; `services.importer` reads the
file and hands over rows (`list[dict[str, str]]`, the header row already used as keys).

Row numbers in errors are spreadsheet rows: the header is row 1, the first data row is row 2.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from core.nodes import RequirementContent
from core.settings import ImportSettings
from worker.contracts import ColumnMapping


class RequirementImportError(ValueError):
    """The file cannot become a requirement set. `row` is the spreadsheet row, if one is to
    blame; the message is shown to the user (Turkish)."""

    def __init__(self, message: str, row: int | None = None) -> None:
        super().__init__(message)
        self.row = row


_BULLET = re.compile(r"^[\s\-•–—*·▪●]+")
_SPACE = re.compile(r"\s+")
_TR_CHARS = re.compile("[çğıöşüÇĞİÖŞÜ]")
_TR_WORDS = frozenset(
    "ve bir için ile olmalıdır olacaktır sağlayacaktır sistem kullanıcı gereksinim "
    "veya her bu de da en daha sonra önce içinde tarafından yapılmalıdır edilmelidir "
    "olarak gerekir".split()
)


def clean_text(text: str) -> str:
    """Whitespace and line breaks collapsed to single spaces, leading bullet marks removed."""
    return _BULLET.sub("", _SPACE.sub(" ", text).strip()).strip()


def detect_language(text: str) -> str:
    """`tr` when the text has Turkish letters or common Turkish words, otherwise `en`."""
    if _TR_CHARS.search(text):
        return "tr"
    words = re.findall(r"[^\W\d_]+", text.lower())
    return "tr" if any(w in _TR_WORDS for w in words) else "en"


def build_requirements(
    rows: Sequence[Mapping[str, str]], mapping: ColumnMapping, settings: ImportSettings
) -> list[RequirementContent]:
    """Requirements in file order. Fully blank rows are skipped; a row with other cells but no
    text, a repeated id, a missing mapped column or more than `max_requirements` is an error."""
    columns = {c for row in rows for c in row}
    for name in (mapping.text, mapping.id, mapping.language, mapping.source):
        if name is not None and rows and name not in columns:
            raise RequirementImportError(
                f"Kolon bulunamadı: {name!r}. Dosyadaki kolonlar: {', '.join(sorted(columns))}"
            )

    def cell(row: Mapping[str, str], name: str | None) -> str:
        return (row.get(name) or "").strip() if name else ""

    explicit = {cell(r, mapping.id) for r in rows} - {""}
    seen: dict[str, int] = {}
    counter = 0
    out: list[RequirementContent] = []
    for i, row in enumerate(rows):
        number = i + 2
        if not any((v or "").strip() for v in row.values()):
            continue
        text = clean_text(cell(row, mapping.text))
        if not text:
            raise RequirementImportError(f"Boş gereksinim metni (satır {number}).", number)
        rid = cell(row, mapping.id)
        if not rid:
            counter += 1
            while f"{settings.id_prefix}{counter}" in explicit:
                counter += 1
            rid = f"{settings.id_prefix}{counter}"
        elif rid in seen:
            raise RequirementImportError(
                f"Yinelenen gereksinim kimliği {rid!r} (satır {number}, ilk görüldüğü satır "
                f"{seen[rid]}).",
                number,
            )
        seen[rid] = number
        language = cell(row, mapping.language).lower() or detect_language(text)
        out.append(
            RequirementContent(
                id=rid, text=text, language=language, source=cell(row, mapping.source)
            )
        )
        if len(out) > settings.max_requirements:
            raise RequirementImportError(
                f"En fazla {settings.max_requirements} gereksinim içe alınabilir."
            )
    if not out:
        raise RequirementImportError("Dosyada gereksinim bulunamadı.")
    return out
