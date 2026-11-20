"""Loads service settings from `config/`.

Files:
- `runtime.yaml`: which engine and model are active, service addresses, timeouts.
- `models.yaml`: candidate models (repo id, precision, context, sequence limit, thinking switch).
- `engines.yaml`: serving engines (image, launch arguments, extra request fields).

Environment overrides (handy on a pod or in CI): `LLM_ENGINE`, `LLM_MODEL`, `LLM_BASE_URL`,
`EMBEDDING_BASE_URL`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from core.llm import LLMParams
from core.nodes import NodeKind, StageConfig
from core.settings import ClusteringSettings, StageSettings


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_id: str
    served_name: str
    precision: str
    context_length: int
    max_num_seqs: int
    # Extra launch arguments for this model, per engine (e.g. reasoning parser).
    engine_args: dict[str, list[str]] = Field(default_factory=dict)
    # Request fields merged into the body when thinking is switched on or off.
    thinking_on: dict[str, Any] = Field(default_factory=dict)
    thinking_off: dict[str, Any] = Field(default_factory=dict)
    gated: bool = False
    # Overrides config/infra.yaml gpu_memory.llm for this model (large weights leave little KV).
    gpu_memory_utilization: float | None = None
    # Repo files not needed for serving (e.g. duplicate checkpoints), skipped when downloading.
    download_ignore: list[str] = Field(default_factory=list)
    approx_size_gb: float | None = None
    notes: str = ""


class EngineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image: str
    port: int
    # Launch command; placeholders are filled by `infra` tooling (see scripts/engine_cmd.py).
    command: list[str]
    health_path: str = "/health"
    # Request fields every call to this engine carries.
    extra_body: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: str
    model: str
    base_url: str
    served_model_name: str
    api_key_env: str | None = None
    request_timeout_s: float = 600.0
    connect_timeout_s: float = 10.0
    default_max_tokens: int = 4096
    default_temperature: float | None = None
    extra_body: dict[str, Any] = Field(default_factory=dict)
    thinking_on: dict[str, Any] = Field(default_factory=dict)
    thinking_off: dict[str, Any] = Field(default_factory=dict)


class EmbeddingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    model: str
    model_version: str
    batch_size: int = 32
    api_key_env: str | None = None
    request_timeout_s: float = 120.0


def _read(config_dir: Path, name: str) -> dict[str, Any]:
    with (config_dir / name).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_models(config_dir: str | Path = "config") -> dict[str, ModelSpec]:
    raw = _read(Path(config_dir), "models.yaml")["models"]
    return {key: ModelSpec.model_validate(value) for key, value in raw.items()}


def load_engines(config_dir: str | Path = "config") -> dict[str, EngineSpec]:
    raw = _read(Path(config_dir), "engines.yaml")["engines"]
    return {key: EngineSpec.model_validate(value) for key, value in raw.items()}


def load_runtime(config_dir: str | Path = "config") -> dict[str, Any]:
    return _read(Path(config_dir), "runtime.yaml")


def load_llm_settings(config_dir: str | Path = "config") -> LLMSettings:
    config_dir = Path(config_dir)
    runtime = load_runtime(config_dir)["llm"]
    engine_key = os.environ.get("LLM_ENGINE", runtime["engine"])
    model_key = os.environ.get("LLM_MODEL", runtime["model"])
    models = load_models(config_dir)
    engines = load_engines(config_dir)
    if model_key not in models:
        raise KeyError(f"unknown model {model_key!r}; known: {sorted(models)}")
    if engine_key not in engines:
        raise KeyError(f"unknown engine {engine_key!r}; known: {sorted(engines)}")
    model, engine = models[model_key], engines[engine_key]
    base_url = os.environ.get("LLM_BASE_URL") or runtime["base_url"].format(port=engine.port)
    return LLMSettings(
        engine=engine_key,
        model=model_key,
        base_url=base_url,
        served_model_name=model.served_name,
        api_key_env=runtime.get("api_key_env"),
        request_timeout_s=runtime.get("request_timeout_s", 600.0),
        connect_timeout_s=runtime.get("connect_timeout_s", 10.0),
        default_max_tokens=runtime.get("default_max_tokens", 4096),
        default_temperature=runtime.get("default_temperature"),
        extra_body=engine.extra_body,
        thinking_on=model.thinking_on,
        thinking_off=model.thinking_off,
    )


def load_embedding_settings(config_dir: str | Path = "config") -> EmbeddingSettings:
    raw = dict(load_runtime(config_dir)["embedding"])
    if url := os.environ.get("EMBEDDING_BASE_URL"):
        raw["base_url"] = url
    return EmbeddingSettings.model_validate(raw)


def load_stage_settings(config_dir: str | Path = "config") -> StageSettings:
    """`core.settings.StageSettings` from config/pipeline.yaml (labels, `generation`,
    `classification`, `cluster_label`, `clustering`, `generation.max_unit_size`) and the examples
    file it names (paket 3)."""
    config_dir = Path(config_dir)
    cfg = _read(config_dir, "pipeline.yaml")
    examples_path = Path(cfg["examples_file"])
    if not examples_path.is_absolute():
        # Repo-relative (`config/prompts/...`): resolved against the parent of `config_dir`.
        examples_path = config_dir.resolve().parent / examples_path
    examples = yaml.safe_load(examples_path.read_text(encoding="utf-8"))

    def params(section: str) -> LLMParams:
        raw = cfg.get(section) or {}
        return LLMParams(**{k: raw[k] for k in LLM_PARAM_KEYS if k in raw})

    generation = cfg.get("generation") or {}
    return StageSettings(
        test_method=cfg["test_method"],
        test_types=tuple(cfg["test_types"]),
        priorities=tuple(cfg["priorities"]),
        examples=examples,
        llm={
            NodeKind.METHOD: params("classification"),
            NodeKind.CLUSTER_LABEL: params("cluster_label"),
            NodeKind.TEST_SET: params("generation"),
        },
        method_batch_size=(cfg.get("classification") or {}).get("batch_size", 25),
        max_unit_size=generation.get("max_unit_size", 25),
        repair=generation.get("repair", True),
        clustering=ClusteringSettings(**(cfg.get("clustering") or {})),
    )


LLM_PARAM_KEYS = ("temperature", "thinking", "max_tokens")


def stage_configs(
    settings: StageSettings,
    *,
    model: str,
    embedding_model_version: str,
) -> dict[NodeKind, StageConfig]:
    """One `StageConfig` per registered stage. Model stages: `prompt_version(stage, settings)`,
    `model`, params = `settings.llm[stage]` as plain JSON, plus the settings that change the
    stage's output without changing its prompt: `batch_size` for the method stage,
    `max_unit_size` (D7) and `repair` for the test set (core/settings.py: everything that changes
    an output reaches `input_hash`). Embedding: version = the embedding model version.
    Clustering: version `c1`, params = `settings.clustering` as plain JSON. Retrieval and matrix:
    fixed versions `r1` and `x1` (paket 7 and 4 change them)."""
    from core import stages
    from core.prompts import prompt_version

    def llm_stage(kind: NodeKind, **extra: Any) -> StageConfig:
        return StageConfig(
            prompt_version=prompt_version(kind, settings),
            model=model,
            params={**settings.llm[kind].model_dump(mode="json"), **extra},
        )

    out = {
        NodeKind.EMBEDDING: StageConfig(prompt_version=embedding_model_version),
        NodeKind.CLUSTERING: StageConfig(
            prompt_version=CLUSTERING_VERSION, params=settings.clustering.model_dump(mode="json")
        ),
        NodeKind.METHOD: llm_stage(NodeKind.METHOD, batch_size=settings.method_batch_size),
        NodeKind.CLUSTER_LABEL: llm_stage(NodeKind.CLUSTER_LABEL),
        NodeKind.RETRIEVAL: StageConfig(prompt_version=RETRIEVAL_VERSION),
        NodeKind.TEST_SET: llm_stage(
            NodeKind.TEST_SET, max_unit_size=settings.max_unit_size, repair=settings.repair
        ),
        NodeKind.MATRIX_ROW: StageConfig(prompt_version=MATRIX_VERSION),
    }
    missing = {s.kind for s in stages.all_specs()} - set(out)
    if missing:
        raise KeyError(f"no stage config for {sorted(missing)}")
    return out


CLUSTERING_VERSION = "c1"
RETRIEVAL_VERSION = "r1"  # paket 7 changes it
MATRIX_VERSION = "x1"  # paket 4 changes it
