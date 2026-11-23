"""Paket 4 behind one seam: import (`services.importer.build_project`), the matrix view
(`core.matrix_view.matrix_rows`) and the xlsx export (`services.xlsx_export.matrix_xlsx`), with
the signatures of docs/paketler/paket-4-plan.md. Imported at call time, so the orchestrator works
before paket 4 is merged: the matrix is then empty and import and export raise
`Paket4Missing`."""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Mapping
from typing import Any

from core.graph import ProjectState
from core.nodes import NodeKind, StageConfig
from core.settings import StageSettings
from core.stages.base import Embed
from worker.contracts import ImportRequest, MatrixRowView


class Paket4Missing(RuntimeError):
    """The paket 4 module is not in this checkout yet."""


def _function(module: str, name: str) -> Any | None:
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name and module.startswith(exc.name):
            return None
        raise
    return getattr(mod, name, None)


def available() -> dict[str, bool]:
    return {
        "build_project": _function("services.importer", "build_project") is not None,
        "matrix_rows": _function("core.matrix_view", "matrix_rows") is not None,
        "matrix_xlsx": _function("services.xlsx_export", "matrix_xlsx") is not None,
    }


async def build_project(
    request: ImportRequest,
    data: bytes,
    filename: str,
    *,
    embed: Embed,
    settings: StageSettings,
    stage_configs: Mapping[NodeKind, StageConfig],
) -> ProjectState:
    fn = _function("services.importer", "build_project")
    if fn is None:
        raise Paket4Missing("services.importer.build_project (paket 4) is not available")
    out = fn(request, data, filename, embed=embed, settings=settings, stage_configs=stage_configs)
    if inspect.isawaitable(out):
        out = await out
    return out


def matrix_rows(state: ProjectState, test_method: str) -> tuple[MatrixRowView, ...]:
    fn = _function("core.matrix_view", "matrix_rows")
    if fn is None:
        return ()  # TODO(paket 4): tests/worker/test_service.py checks rows once merged
    return tuple(fn(state, test_method))


def matrix_xlsx(state: ProjectState, test_method: str) -> bytes:
    fn = _function("services.xlsx_export", "matrix_xlsx")
    if fn is None:
        raise Paket4Missing("services.xlsx_export.matrix_xlsx (paket 4) is not available")
    return fn(state, test_method)
