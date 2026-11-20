"""Document corpus manifest of golden set v1 (paket 1b, stage 3).

One `eval/corpus/<project>/manifest.yaml` per project. Documents are not stored in the repository:
the manifest pins where each one comes from (URL and SHA-256), under which licence, how its text is
extracted and whether the test writer may see it.

- `downloads`: files fetched from the web, keyed by a short name. One download can hold several
  documents (SUBSET-026 is one zip with nine chapters).
- `documents`: the unit that golden items cite (`source.doc`, `support_passages[].doc`).
- `role`: `corpus` documents are visible to the test writer; `reference` documents are the answer
  key (official test procedures, conformance criteria) and are never given to the writer; `mixed`
  documents hold both, and `reference_parts` says which parts must be stripped.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CORPUS_DIR = Path(__file__).resolve().parent
SHA256 = r"^[0-9a-f]{64}$"


class Role(StrEnum):
    corpus = "corpus"
    reference = "reference"
    mixed = "mixed"


class RepoText(StrEnum):
    """May the extracted text be committed? `private_only`: only while the repository is private
    (user decision of 20 Nov 2026 for ERTMS)."""

    yes = "yes"
    private_only = "private_only"
    no = "no"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Download(Strict):
    url: str = Field(pattern=r"^https://")
    # null only while a new entry is being added; `fetch` refuses unpinned downloads unless asked.
    sha256: str | None = Field(default=None, pattern=SHA256)
    bytes: int | None = None
    # immutable: the URL serves the same bytes forever (versioned PDF, tagged file).
    # live: an HTML page that may change; the committed snapshot of its text is authoritative and a
    # changed hash is reported as drift instead of an error.
    stability: Literal["immutable", "live"] = "immutable"
    retrieved: str | None = None  # date, required for live downloads
    optional: bool = False  # large or not yet used: fetched only with --all

    @model_validator(mode="after")
    def _live_has_date(self) -> Download:
        if self.stability == "live" and not self.retrieved:
            raise ValueError("live downloads need a retrieval date")
        return self


class Extract(Strict):
    # pdftotext: poppler, `args` e.g. ["-layout"]; html: visible text; xlsx: one TSV block per
    # sheet; raw: the bytes are already text (csv, json, md).
    method: Literal["pdftotext", "html", "xlsx", "raw"]
    args: tuple[str, ...] = ()


class ReferencePart(Strict):
    """A part of a mixed document that belongs to the answer key."""

    marker: str  # how to find it in the extracted text (heading or table title)
    note: str


class Document(Strict):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    title: str
    publisher: str
    version: str
    kind: Literal[
        "specification", "standard", "regulation", "guidance", "test_procedure", "catalog", "system"
    ]
    role: Role
    language: Literal["en", "tr"]
    # exactly one of: a download (optionally a member or member glob inside a zip) or a path in
    # the repository (synthetic system documents written for the project)
    download: str | None = None
    member: str | None = None
    path: str | None = None  # may be a glob (one text file per match)
    origin: str = ""  # for path documents: where the committed copy came from (URL, commit, date)
    extract: Extract
    license: str
    license_evidence: str  # where the primary source states the licence or copyright
    repo_text: RepoText
    reference_parts: tuple[ReferencePart, ...] = ()
    snapshot: str | None = None  # committed extracted text (live downloads, repo_text != no)
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> Document:
        if (self.download is None) == (self.path is None):
            raise ValueError(f"{self.id}: give exactly one of download or path")
        if self.member and not self.download:
            raise ValueError(f"{self.id}: member needs a download")
        if self.path and self.kind != "system" and not self.origin:
            raise ValueError(f"{self.id}: committed copies of external documents need an origin")
        if (self.role == Role.mixed) != bool(self.reference_parts):
            raise ValueError(f"{self.id}: reference_parts are required exactly for mixed documents")
        if self.snapshot and self.repo_text == RepoText.no:
            raise ValueError(f"{self.id}: snapshot of a document whose text may not be committed")
        return self


class Manifest(Strict):
    project: str = Field(pattern=r"^[A-Z]{2,5}$")
    downloads: dict[str, Download] = {}
    documents: tuple[Document, ...]
    excluded: dict[str, str] = {}  # considered and left out, with the reason

    @model_validator(mode="after")
    def _references(self) -> Manifest:
        ids = [d.id for d in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate document ids")
        for d in self.documents:
            if d.download is not None and d.download not in self.downloads:
                raise ValueError(f"{d.id}: unknown download {d.download}")
            dl = self.downloads.get(d.download or "")
            if dl and dl.stability == "live" and d.repo_text != RepoText.no and not d.snapshot:
                raise ValueError(f"{d.id}: live download without a committed snapshot")
        used = {d.download for d in self.documents}
        if unused := sorted(set(self.downloads) - used):
            raise ValueError(f"downloads not used by any document: {unused}")
        return self

    def document(self, doc_id: str) -> Document:
        for d in self.documents:
            if d.id == doc_id:
                return d
        raise KeyError(doc_id)


def manifest_paths(root: Path = CORPUS_DIR) -> list[Path]:
    return sorted(root.glob("*/manifest.yaml"))


def load_manifest(path: Path) -> Manifest:
    return Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
