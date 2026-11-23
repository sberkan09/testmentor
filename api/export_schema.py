"""`python -m api.export_schema`: JSON schema of the API contract (`worker/contracts.py`, and
`api/models.py` for the endpoints added in paket 10) into
`api/schema.json`. The frontend (paket 8) generates its TypeScript types from it; a test checks
that the committed file is current."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from api.models import (
    AuthConfig,
    KbDocumentView,
    KbRemoveResult,
    KbUploadResult,
    LoginRequest,
    LoginResult,
)
from worker.contracts import (
    CommandRequest,
    CommandResult,
    ImportRequest,
    MatrixRowView,
    NodeView,
    ServerEvent,
    Snapshot,
)

OUT = Path(__file__).resolve().parent / "schema.json"


class ApiContract(BaseModel):
    """Container so that every model lands in one schema with shared `$defs`."""

    import_request: ImportRequest
    command_request: CommandRequest
    command_result: CommandResult
    snapshot: Snapshot
    server_event: ServerEvent
    node_view: NodeView
    matrix_row: MatrixRowView
    kb_document: KbDocumentView
    kb_upload_result: KbUploadResult
    kb_remove_result: KbRemoveResult
    auth_config: AuthConfig
    login_request: LoginRequest
    login_result: LoginResult


def render() -> str:
    return json.dumps(ApiContract.model_json_schema(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    OUT.write_text(render(), encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
