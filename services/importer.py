"""File to project (paket 4): reads csv / xlsx rows and builds the first `ProjectState`.

`core.importing` turns the rows into requirements; this module owns the file formats, the
embedding call and the first cut. The embedding and clustering-tree nodes are written here, from
the same vectors the cut used, so the embedding service is called once and a new project has
nothing stale in those two stages.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from itertools import count
from pathlib import PurePath

from core.graph import ProjectState, new_project
from core.importing import RequirementImportError, build_requirements
from core.invalidation import settle_many
from core.nodes import CLUSTERING_KEY, EmbeddingContent, MethodDef, NodeKind, NodeRef, StageConfig
from core.settings import ImportSettings, StageSettings
from core.stages import clustering
from core.stages.base import Embed, ProduceContext
from core.stages.calls import result
from services.settings import load_default_methods, load_import_settings
from worker.contracts import ImportRequest

INDEX_VERSION = "v1"
"""`kb_index` version of a project without documents (paket 7 moves it)."""


def read_rows(
    data: bytes, filename: str, sheet: str | None, encodings: Sequence[str] | None = None
) -> list[dict[str, str]]:
    """Rows keyed by the header row (the first row). csv: `encodings` in order (default the
    `import.encodings` setting), delimiter by `csv.Sniffer`. xlsx: the named or first sheet,
    every cell as text."""
    suffix = PurePath(filename).suffix.lower()
    if suffix == ".csv":
        return _read_csv(data, encodings or load_import_settings().encodings)
    if suffix in (".xlsx", ".xlsm"):
        return _read_xlsx(data, sheet)
    raise RequirementImportError("Desteklenmeyen dosya türü; csv ya da xlsx yükleyin.")


def _read_csv(data: bytes, encodings: Sequence[str]) -> list[dict[str, str]]:
    text: str | None = None
    for enc in encodings:
        try:
            text = data.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        raise RequirementImportError(
            f"Dosya kodlaması çözülemedi (denenenler: {', '.join(encodings)})."
        )
    # The sniffer is trusted for the delimiter only: its quote character guess breaks on text
    # with quoted words inside a quoted cell.
    try:
        delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    grid = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    return _rows_from_grid(grid)


def _read_xlsx(data: bytes, sheet: str | None) -> list[dict[str, str]]:
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (InvalidFileException, OSError, KeyError, ValueError) as exc:
        raise RequirementImportError(f"xlsx dosyası açılamadı: {exc}") from exc
    try:
        if sheet is not None and sheet not in wb.sheetnames:
            raise RequirementImportError(
                f"Sayfa bulunamadı: {sheet!r}. Sayfalar: {', '.join(wb.sheetnames)}"
            )
        ws = wb[sheet] if sheet is not None else wb[wb.sheetnames[0]]
        grid = [[_cell_text(v) for v in row] for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    return _rows_from_grid(grid)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _rows_from_grid(grid: Sequence[Sequence[str]]) -> list[dict[str, str]]:
    if not grid:
        return []
    header = [h.strip() for h in grid[0]]
    out: list[dict[str, str]] = []
    for line in grid[1:]:
        out.append({h: (line[i] if i < len(line) else "") for i, h in enumerate(header) if h})
    return out


async def build_project(
    request: ImportRequest,
    data: bytes,
    filename: str,
    *,
    embed: Embed,
    settings: StageSettings,
    stage_configs: Mapping[NodeKind, StageConfig],
    import_settings: ImportSettings | None = None,
    default_methods: Sequence[MethodDef] | None = None,
) -> ProjectState:
    """The new project: requirements, one embedding call, the first cut (clusters `C001`,
    `C002`, ...), the card, and the embedding and clustering-tree nodes already settled."""
    imp = import_settings or load_import_settings()
    rows = read_rows(data, filename, request.sheet, imp.encodings)
    requirements = build_requirements(rows, request.mapping, imp)
    ids = [r.id for r in requirements]
    vectors = await embed([r.text for r in requirements])
    if len(vectors) != len(ids):
        raise RuntimeError(f"embedding returned {len(vectors)} vectors for {len(ids)} texts")

    numbers = count(1)
    clusters = clustering.initial_membership(
        ids, vectors, settings.clustering, lambda: f"C{next(numbers):03d}"
    )
    methods = request.methods or tuple(default_methods or load_default_methods())
    state = new_project(
        request.key,
        requirements=requirements,
        clusters=clusters,
        card=request.card_text or f"Project: {request.name} ({request.key})",
        index_version=INDEX_VERSION,
        stage_configs=stage_configs,
        methods=methods,
    )

    emb_results = []
    for rid, vector in zip(ids, vectors, strict=True):
        ref = NodeRef(kind=NodeKind.EMBEDDING, key=rid)
        content = EmbeddingContent(vector=tuple(float(x) for x in vector))
        emb_results.append((ref, result(state, ref, content, mode="algorithm")))
    state = settle_many(state, emb_results).state

    tree_ref = NodeRef(kind=NodeKind.CLUSTERING, key=CLUSTERING_KEY)
    outcome = await clustering.produce(
        ProduceContext(state=state, refs=(tree_ref,), settings=settings),
        complete=None,  # type: ignore[arg-type]  # the tree is an algorithm, no model call
    )
    if outcome.failed:
        raise RuntimeError(f"clustering tree failed: {dict(outcome.failed)}")
    return settle_many(state, list(outcome.results)).state
