"""Bodies of the endpoints added after the contract froze (paket 10): knowledge base documents.
`worker/contracts.py` (`Snapshot` and the rest) is unchanged; these models go into
`api/schema.json` next to it."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class KbDocumentView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    """Document id: the file name made safe; it starts every passage id (`<id>#<seq>@...`)."""
    name: str
    """Original file name."""
    chunks: int
    added_by: str = ""
    added_at: float = 0.0
    """Unix time; 0 when unknown."""


class KbUploadResult(BaseModel):
    document: KbDocumentView
    seq: int
    """Last event number after the upload (`kb_index` updated, retrievals re-checked)."""


class KbRemoveResult(BaseModel):
    seq: int
