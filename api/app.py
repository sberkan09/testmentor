"""REST and WebSocket API (paket 6) over `worker.contracts.ProjectService`.

The app knows only the service interface; bodies and events are the contract models.
Rejected commands answer with a `CommandResult` body (`accepted: false`) and the HTTP code of
the reason: `version_conflict` and `nothing_to_undo` 409, `locked` 423, `invalid` 422.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, TypeAdapter, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.websockets import WebSocketDisconnect

from core.nodes import NodeRef
from worker.contracts import (
    CommandRequest,
    CommandResult,
    ImportRequest,
    ProjectService,
    ServerEvent,
    Snapshot,
)

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


def create_app(
    service: ProjectService,
    *,
    static_dir: Path | None = None,
    ping_interval_s: float = 20.0,
) -> FastAPI:
    app = FastAPI(title="testmentor")
    command_adapter: TypeAdapter[CommandRequest] = TypeAdapter(CommandRequest)

    def is_known(project_id: str) -> bool:
        return project_id in {pid for pid, _ in service.projects()}

    def known(project_id: str) -> None:
        if not is_known(project_id):
            raise HTTPException(404, f"unknown project {project_id}")

    def actor_of(x_user: str | None) -> str:
        """The `X-User` header is percent-encoded UTF-8 (HTTP headers carry Latin-1 only, and
        user names like "Ayşe" do not fit); a plain ASCII name decodes to itself."""
        name = unquote(x_user or "").strip()
        if not name:
            raise HTTPException(400, "X-User header is required")
        return name

    @app.get("/projects")
    def list_projects() -> list[dict[str, str]]:
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
    def snapshot(project_id: str) -> Snapshot:
        known(project_id)
        return service.snapshot(project_id)

    @app.post("/projects/{project_id}/commands")
    async def command(
        project_id: str, request: Request, x_user: str | None = Header(default=None)
    ) -> Response:
        actor = actor_of(x_user)
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
    def lock(
        project_id: str, body: LockBody, x_user: str | None = Header(default=None)
    ) -> JSONResponse:
        actor = actor_of(x_user)
        known(project_id)
        ok = service.lock(project_id, body.ref, actor)
        return JSONResponse({"locked": ok}, status_code=200 if ok else 423)

    @app.get("/projects/{project_id}/matrix.xlsx")
    def matrix(project_id: str) -> Response:
        known(project_id)
        return Response(
            service.matrix_xlsx(project_id),
            media_type=XLSX_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{project_id}-matrix.xlsx"'},
        )

    @app.websocket("/projects/{project_id}/events")
    async def events(
        ws: WebSocket, project_id: str, after: int | None = None, user: str = ""
    ) -> None:
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
