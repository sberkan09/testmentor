"""Settings the stage producers and prompts read (paket 3). Plain data: `core/` reads no files;
`services/settings.load_stage_settings` builds this from config/pipeline.yaml and the examples
file. Everything here that changes an output also reaches `input_hash`, either through the
prompt fingerprint (`core.prompts.prompt_version`) or through `StageConfig.params`."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.llm import LLMParams
from core.nodes import NodeKind

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ClusteringSettings(BaseModel):
    """D6 working assumption: agglomerative, average linkage, cosine distance 0.35."""

    model_config = _FROZEN

    method: Literal["agglomerative", "hdbscan"] = "agglomerative"
    linkage: str = "average"
    distance_threshold: float = 0.35
    max_cluster_size: int = Field(default=25, ge=1)
    """Cut-time limit: clusters shown in the UI are chunked to this size."""
    min_cluster_size: int = Field(default=2, ge=2)
    """HDBSCAN only."""


class StageSettings(BaseModel):
    model_config = _FROZEN

    test_method: str
    """Requirements whose methods include this get test cases."""
    test_types: tuple[str, ...]
    priorities: tuple[str, ...]
    examples: dict[str, Any]
    """Generation examples (`requirements`, `output`), layer 3 of the test prompt."""
    llm: dict[NodeKind, LLMParams]
    """Parameters per model stage: METHOD, CLUSTER_LABEL, TEST_SET."""
    method_batch_size: int = Field(default=25, ge=1)
    max_unit_size: int = Field(default=25, ge=1)
    """Generation-time limit (`generation.max_unit_size`, D7): a larger cluster is produced in
    balanced parts. Independent of `clustering.max_cluster_size`."""
    repair: bool = True
    """One coverage repair call for Test requirements left uncovered."""
    clustering: ClusteringSettings = ClusteringSettings()
