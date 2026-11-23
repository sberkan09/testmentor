"""Orchestrator settings (`config/runtime.yaml`, `orchestrator:`; docs/tasarim.md, İş kuyruğu)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from services.settings import load_runtime


class OrchestratorSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    debounce_s: float = Field(default=1.5, ge=0)
    """Wait after an edit; successive edits of the same node collapse into one job (D11)."""
    concurrency: int = Field(default=16, ge=1)
    """Jobs running at once; the model server's sequence limit."""
    p2_share: float = Field(default=0.7, gt=0, le=1)
    """Largest share of the slots automatic (P2) jobs may hold (D11)."""
    event_buffer: int = Field(default=10_000, ge=1)
    """Server events kept per project for replay; older ones need a snapshot."""
    lock_s: float = Field(default=60.0, gt=0)
    """Edit lock lifetime without a refresh."""


def load_orchestrator_settings(config_dir: str | Path = "config") -> OrchestratorSettings:
    return OrchestratorSettings.model_validate(load_runtime(config_dir).get("orchestrator") or {})
