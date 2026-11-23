"""REST and WebSocket API (paket 6) over `worker.contracts.ProjectService`.

The app knows only the service interface; bodies and events are the contract models.
Rejected commands answer with a `CommandResult` body (`accepted: false`) and the HTTP code of
the reason: `version_conflict` and `nothing_to_undo` 409, `locked` 423, `invalid` 422.

Every endpoint is `async def`: the service is single-threaded on the server's event loop, and a
plain `def` endpoint would run in FastAPI's thread pool.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any
from urllib.parse import unquote

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, TypeAdapter, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.websockets import WebSocketDisconnect

from api.models import (
    AuthConfig,
    KbDocumentView,
    KbRemoveResult,
    KbUploadResult,
    LoginRequest,
    LoginResult,
)
from core.nodes import NodeRef
from worker.contracts import (
    CommandRequest,
    CommandResult,
    ImportRequest,
    ProjectService,
    ServerEvent,
    Snapshot,
)

if TYPE_CHECKING:
    from api.auth import Authenticator
    from services.kb_documents import DocumentInfo, KbDocuments

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_STATUS = {
    "version_conflict": 409,
    "nothing_to_undo": 409,
    "locked": 423,
    "invalid": 422,
}
NON_PERSISTENT = {"job_progress"}
"""Live only: no sequence number of their own, never replayed."""


class LockBody(BaseModel):
    ref: NodeRef


def rejection_status(reason: str) -> int:
    head = reason.split(":", 1)[0].split(" ", 1)[0]
    return _STATUS.get(head, 422)


class _SpaFiles(StaticFiles):
    """Static files with `index.html` as the fallback for client-side routes."""

    async def get_response(self, path: str, scope: Any) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def _document_view(info: DocumentInfo) -> KbDocumentView:
    return KbDocumentView(
        id=info.id,
        name=info.name,
        chunks=info.chunks,
        added_by=info.added_by,
        added_at=info.added_at,
    )


def create_app(
    service: ProjectService,
    *,
    kb: KbDocuments | None = None,
    auth: Authenticator | None = None,
    static_dir: Path | None = None,
    ping_interval_s: float = 20.0,
) -> FastAPI:
    """`kb`: the knowledge base uploads (paket 10); without it the `/kb/documents` endpoints
    answer 404. `auth`: login (paket 10, `api/auth.py`); None or mode `header` reads the actor
    from `X-User`. In mode `password` every `/projects` request needs a valid token (401
    otherwise): `Authorization: Bearer`, or `?token=` for the xlsx link and the WebSocket."""
    app = FastAPI(title="testmentor")
    password_mode = auth is not None and auth.mode == "password"

    if password_mode:
        assert auth is not None

        @app.middleware("http")
        async def require_token(request: Request, call_next: Any) -> Response:
            path = request.url.path
            if path == "/projects" or path.startswith("/projects/"):
                header = request.headers.get("authorization", "")
                token = header[7:].strip() if header.lower().startswith("bearer ") else None
                if token is None and path.endswith("/matrix.xlsx"):
                    token = request.query_params.get("token")
                user = auth.verify(token)
                if user is None:
                    return JSONResponse(
                        {"detail": "login required"},
                        status_code=401,
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                request.state.user = user
            return await call_next(request)

    @app.get("/auth/config")
    async def auth_config() -> AuthConfig:
        return AuthConfig(mode="password" if password_mode else "header")

    @app.post("/auth/login")
    async def login(body: LoginRequest) -> LoginResult:
        if not password_mode or auth is None:
            raise HTTPException(404, "password login is off (auth.mode: header)")
        issued = await auth.login(body.user, body.password)
        if issued is None:
            raise HTTPException(401, "kullanıcı adı ya da parola yanlış")
        token, expires = issued
        return LoginResult(token=token, user=body.user.strip(), expires_at=expires)

    command_adapter: TypeAdapter[CommandRequest] = TypeAdapter(CommandRequest)

    def is_known(project_id: str) -> bool:
        return project_id in {pid for pid, _ in service.projects()}

    def known(project_id: str) -> None:
        if not is_known(project_id):
            raise HTTPException(404, f"unknown project {project_id}")

    def actor_of(request: Request, x_user: str | None) -> str:
        """Password mode: the token's user (`X-User` is ignored). Header mode: the `X-User`
        header, percent-encoded UTF-8 (HTTP headers carry Latin-1 only, and user names like
        "Ayşe" do not fit); a plain ASCII name decodes to itself."""
        if password_mode:
            return str(request.state.user)
        name = unquote(x_user or "").strip()
        if not name:
            raise HTTPException(400, "X-User header is required")
        return name

    @app.get("/projects")
    async def list_projects() -> list[dict[str, str]]:
        return [{"id": pid, "name": name} for pid, name in service.projects()]

    @app.post("/projects")
    async def create_project(
        meta: Annotated[str, Form()], file: Annotated[UploadFile, File()]
    ) -> Snapshot:
        try:
            request = ImportRequest.model_validate_json(meta)
        except ValidationError as exc:
            raise HTTPException(422, f"meta: {exc.errors(include_url=False)}") from exc
        data = await file.read()
        try:
            return await service.create_project(request, data, file.filename or "")
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/projects/{project_id}/snapshot")
    async def snapshot(project_id: str) -> Snapshot:
        known(project_id)
        return service.snapshot(project_id)

    @app.post("/projects/{project_id}/commands")
    async def command(
        project_id: str, request: Request, x_user: str | None = Header(default=None)
    ) -> Response:
        actor = actor_of(request, x_user)
        known(project_id)
        try:
            body = command_adapter.validate_python(await request.json())
        except (ValidationError, ValueError) as exc:
            detail = (
                str(exc.errors(include_url=False)) if isinstance(exc, ValidationError) else str(exc)
            )
            rejected = CommandResult(
                accepted=False,
                seq=service.snapshot(project_id).seq,
                reason=f"invalid: {detail}",
            )
            return JSONResponse(rejected.model_dump(mode="json"), status_code=422)
        result = await service.command(project_id, body, actor)
        code = 200 if result.accepted else rejection_status(result.reason)
        return JSONResponse(result.model_dump(mode="json"), status_code=code)

    @app.post("/projects/{project_id}/locks")
    async def lock(
        project_id: str,
        body: LockBody,
        request: Request,
        x_user: str | None = Header(default=None),
    ) -> JSONResponse:
        actor = actor_of(request, x_user)
        known(project_id)
        ok = service.lock(project_id, body.ref, actor)
        return JSONResponse({"locked": ok}, status_code=200 if ok else 423)

    @app.get("/projects/{project_id}/matrix.xlsx")
    async def matrix(project_id: str) -> Response:
        known(project_id)
        return Response(
            service.matrix_xlsx(project_id),
            media_type=XLSX_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{project_id}-matrix.xlsx"'},
        )

    def kb_or_404() -> KbDocuments:
        if kb is None:
            raise HTTPException(404, "knowledge base is not configured")
        return kb

    @app.get("/projects/{project_id}/kb/documents")
    async def kb_documents(project_id: str) -> list[KbDocumentView]:
        docs = kb_or_404()
        known(project_id)
        return [_document_view(d) for d in docs.list(project_id)]

    @app.post("/projects/{project_id}/kb/documents")
    async def kb_upload(
        project_id: str,
        file: Annotated[UploadFile, File()],
        request: Request,
        x_user: str | None = Header(default=None),
    ) -> KbUploadResult:
        from services.kb_documents import UploadRejected

        actor = actor_of(request, x_user)
        docs = kb_or_404()
        known(project_id)
        data = await file.read()
        try:
            info, seq = await docs.add(project_id, file.filename or "", data, actor)
        except UploadRejected as exc:
            raise HTTPException(422, str(exc)) from exc
        return KbUploadResult(document=_document_view(info), seq=seq)

    @app.delete("/projects/{project_id}/kb/documents/{document_id}")
    async def kb_remove(
        project_id: str,
        document_id: str,
        request: Request,
        x_user: str | None = Header(default=None),
    ) -> KbRemoveResult:
        actor = actor_of(request, x_user)
        docs = kb_or_404()
        known(project_id)
        try:
            seq = docs.remove(project_id, document_id, actor)
        except KeyError as exc:
            raise HTTPException(404, f"unknown document {document_id}") from exc
        return KbRemoveResult(seq=seq)

    @app.websocket("/projects/{project_id}/events")
    async def events(
        ws: WebSocket,
        project_id: str,
        after: int | None = None,
        user: str = "",
        token: str | None = None,
    ) -> None:
        if password_mode and (auth is None or auth.verify(token) is None):
            await ws.close(code=4401)
            return
        if not is_known(project_id):
            await ws.close(code=4404)
            return
        await ws.accept()
        send_lock = asyncio.Lock()

        async def send(payload: dict[str, Any]) -> None:
            async with send_lock:
                await ws.send_text(json.dumps(payload, ensure_ascii=False))

        queue: asyncio.Queue[ServerEvent] = asyncio.Queue()

        async def pump() -> None:
            live: AsyncIterator[ServerEvent] = service.subscribe(project_id)
            async for event in live:
                queue.put_nowait(event)

        async def listen() -> None:
            while True:
                text = await ws.receive_text()
                try:
                    kind = json.loads(text).get("type")
                except (ValueError, AttributeError):
                    continue
                if kind == "ping":
                    await send({"type": "pong"})

        async def ping() -> None:
            while True:
                await asyncio.sleep(ping_interval_s)
                await send({"type": "ping"})

        last = 0

        async def forward() -> None:
            nonlocal last
            while True:
                event = await queue.get()
                if event.type not in NON_PERSISTENT:
                    if event.seq <= last:
                        continue  # already replayed
                    last = event.seq
                await send(event.model_dump(mode="json"))

        pump_task = asyncio.create_task(pump())
        tasks: list[asyncio.Task[None]] = [pump_task]
        try:
            await asyncio.sleep(0)  # let the subscription register before the replay is read
            missed = service.events_after(project_id, after) if after is not None else None
            if missed is None:
                snap = service.snapshot(project_id)
                await send({"type": "snapshot", "snapshot": snap.model_dump(mode="json")})
                last = snap.seq
            else:
                last = after or 0
                for event in missed:
                    await send(event.model_dump(mode="json"))
                    last = max(last, event.seq)
            tasks += [
                asyncio.create_task(listen()),
                asyncio.create_task(ping()),
                asyncio.create_task(forward()),
            ]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                exc = t.exception()
                if exc is not None and not isinstance(exc, WebSocketDisconnect | RuntimeError):
                    raise exc
        except WebSocketDisconnect:
            pass
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
            with contextlib.suppress(Exception):
                await ws.close()

    default_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
    dist = static_dir if static_dir is not None else default_dist
    if dist.is_dir():
        app.mount("/", _SpaFiles(directory=dist, html=True), name="web")
    return app
