"""Knowledge base uploads on the server (docs/tasarim.md, İndeks; paket 10).

`KbDocuments` turns an uploaded file into chunks of the project's index and tells the
orchestrator (`on_change`, wired to `OrchestratorService.kb_document_added`): every retrieval of
the project searches again, and a test set goes stale only when its passage ids come out
different.

- Text: plain text and Markdown (UTF-8, else Windows-1254), PDF with a text layer (`pypdf`, run
  in a worker thread). A file that yields no chunk (a scanned PDF) is refused, not added.
- The document id is the file name made safe (`[\\w.-]`), so uploading the same file again
  replaces the document and keeps its passage ids (`<document>#<seq>@<digest>`): unchanged text
  means unchanged test sets.
- The list comes from the index (`KbIndex.documents`: chunk counts survive a restart in
  Postgres) plus a small registry for the original file name, who added it and when.

Index and orchestrator calls run on the caller's event loop thread (both are single-threaded).
"""

from __future__ import annotations

import asyncio
import io
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from core.kb.settings import KbSettings
from core.stages.base import Embed
from services.kb_examples import ExamplePool
from services.kb_index import KbIndex, ingest_document
from services.kb_retrieve import index_version


class UploadSettings(BaseModel):
    """`kb_upload:` of config/runtime.yaml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_mb: float = Field(default=20, gt=0)
    extensions: tuple[str, ...] = (".txt", ".md", ".markdown", ".pdf")


def load_upload_settings(config_dir: str | Path = "config") -> UploadSettings:
    from services.settings import load_runtime

    return UploadSettings.model_validate(load_runtime(config_dir).get("kb_upload") or {})


class UploadRejected(ValueError):
    """The file cannot be added (the API answers 422 with the message)."""


@dataclass(frozen=True)
class DocumentInfo:
    id: str
    name: str
    chunks: int
    added_by: str = ""
    added_at: float = 0.0
    """Unix time; 0 when unknown (a document indexed outside the upload endpoint)."""


@dataclass(frozen=True)
class DocumentMeta:
    name: str
    added_by: str
    added_at: float


class DocumentRegistry(Protocol):
    def put(self, project_id: str, document_id: str, meta: DocumentMeta) -> None: ...

    def remove(self, project_id: str, document_id: str) -> None: ...

    def get_all(self, project_id: str) -> dict[str, DocumentMeta]: ...


class MemoryRegistry:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, DocumentMeta]] = {}

    def put(self, project_id: str, document_id: str, meta: DocumentMeta) -> None:
        self._data.setdefault(project_id, {})[document_id] = meta

    def remove(self, project_id: str, document_id: str) -> None:
        self._data.get(project_id, {}).pop(document_id, None)

    def get_all(self, project_id: str) -> dict[str, DocumentMeta]:
        return dict(self._data.get(project_id, {}))


class PgRegistry:
    """`kb_documents` next to `kb_chunks` (same database, its own autocommit connection)."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS kb_documents ("
                "project_id text NOT NULL, document_id text NOT NULL, name text NOT NULL, "
                "added_by text NOT NULL, added_at double precision NOT NULL, "
                "PRIMARY KEY (project_id, document_id))"
            )

    def put(self, project_id: str, document_id: str, meta: DocumentMeta) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kb_documents (project_id, document_id, name, added_by, added_at) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (project_id, document_id) DO UPDATE "
                "SET name = EXCLUDED.name, added_by = EXCLUDED.added_by, "
                "added_at = EXCLUDED.added_at",
                (project_id, document_id, meta.name, meta.added_by, meta.added_at),
            )

    def remove(self, project_id: str, document_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM kb_documents WHERE project_id = %s AND document_id = %s",
                (project_id, document_id),
            )

    def get_all(self, project_id: str) -> dict[str, DocumentMeta]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT document_id, name, added_by, added_at FROM kb_documents "
                "WHERE project_id = %s",
                (project_id,),
            )
            return {d: DocumentMeta(n, b, float(a)) for d, n, b, a in cur.fetchall()}


_UNSAFE = re.compile(r"[^\w.-]+")


def document_id_for(filename: str) -> str:
    """The file name (no directories) with every run of other characters than letters, digits,
    `.`, `_` and `-` turned into `-`; `belge` when nothing is left. Never holds `#` or `@`
    (the passage id separators)."""
    name = PurePath(filename.replace("\\", "/")).name
    safe = _UNSAFE.sub("-", name).strip("-.")[:120]
    return safe or "belge"


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1254"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UploadRejected("metin UTF-8 ya da Windows-1254 olarak çözülemedi")


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise UploadRejected(f"PDF okunamadı: {exc}") from exc
    return "\n\n".join(p for p in pages if p)


async def extract_text(filename: str, data: bytes, settings: UploadSettings) -> str:
    """Text of an uploaded file by its extension. `UploadRejected` for another type, a file over
    the size limit or one that cannot be read."""
    suffix = PurePath(filename).suffix.lower()
    if suffix not in settings.extensions:
        allowed = ", ".join(settings.extensions)
        kind = suffix or "(uzantısız)"
        raise UploadRejected(f"desteklenmeyen dosya türü {kind}; izinli: {allowed}")
    if len(data) > settings.max_mb * 1024 * 1024:
        raise UploadRejected(f"dosya {settings.max_mb:g} MB sınırını aşıyor")
    if suffix == ".pdf":
        return await asyncio.to_thread(_pdf_text, data)
    return _decode(data)


OnChange = Callable[[str, str, str, str], int]
"""(project id, document id, index version, actor) → last event number."""


class KbDocuments:
    def __init__(
        self,
        index: KbIndex,
        registry: DocumentRegistry,
        pool: ExamplePool,
        embed: Embed,
        settings: KbSettings,
        upload: UploadSettings,
        on_change: OnChange,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.index = index
        self.registry = registry
        self.pool = pool
        self.embed = embed
        self.settings = settings
        self.upload = upload
        self.on_change = on_change
        self.clock = clock

    async def add(
        self, project_id: str, filename: str, data: bytes, actor: str
    ) -> tuple[DocumentInfo, int]:
        """Index the file (replacing a document of the same id) and notify the orchestrator.
        Returns the document and the last event number."""
        text = await extract_text(filename, data, self.upload)
        if not text.strip():
            raise UploadRejected(
                "dosyada metin yok (taranmış PDF olabilir); "
                "metin katmanlı PDF, .txt ya da .md yükle"
            )
        document_id = document_id_for(filename)
        chunks = await ingest_document(
            self.index, project_id, document_id, text, self.embed, self.settings
        )
        meta = DocumentMeta(PurePath(filename).name or document_id, actor, self.clock())
        self.registry.put(project_id, document_id, meta)
        seq = self._changed(project_id, document_id, actor)
        return DocumentInfo(document_id, meta.name, len(chunks), actor, meta.added_at), seq

    def remove(self, project_id: str, document_id: str, actor: str) -> int:
        """`KeyError` for a document the project does not hold."""
        if document_id not in self.index.documents(project_id):
            raise KeyError(document_id)
        self.index.remove_document(project_id, document_id)
        self.registry.remove(project_id, document_id)
        return self._changed(project_id, document_id, actor)

    def list(self, project_id: str) -> list[DocumentInfo]:
        metas = self.registry.get_all(project_id)
        out = []
        for document_id, count in self.index.documents(project_id).items():
            m = metas.get(document_id)
            out.append(
                DocumentInfo(
                    document_id,
                    m.name if m else document_id,
                    count,
                    m.added_by if m else "",
                    m.added_at if m else 0.0,
                )
            )
        return out

    def _changed(self, project_id: str, document_id: str, actor: str) -> int:
        version = index_version(self.index, self.pool, project_id)
        return self.on_change(project_id, document_id, version, actor)
