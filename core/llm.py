"""Model call contract of the stage producers (docs/tasarim.md, Kod düzeni; paket 3).

`core/` imports no model client. A producer receives a `Complete` callable and sends it
`LLMRequest`s; `services/stage_llm.py` implements it over `LLMClient` (OpenAI-compatible API,
streaming, cancellable), tests implement it with scripted replies. Cancelling the producer's task
cancels the call in flight.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from core.nodes import NodeKind

Message = dict[str, str]


class LLMParams(BaseModel):
    """Generation parameters of one model stage (from config/pipeline.yaml). They enter the
    stage's `StageConfig.params` and therefore `input_hash`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    temperature: float = 0.0
    thinking: bool = False
    max_tokens: int = Field(default=4096, ge=1)


@dataclass(frozen=True)
class LLMRequest:
    stage: NodeKind
    unit: str
    """Free-form label for logs and measurements, e.g. `A/full`, `A/repair`, `methods/0`."""
    messages: tuple[Message, ...]
    schema: type[BaseModel]
    """Output is bound to this model's JSON schema (structured outputs)."""
    params: LLMParams


class LLMUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    ttft_s: float | None = None
    total_s: float | None = None


@dataclass(frozen=True)
class LLMReply:
    content: str
    parsed: BaseModel | None
    """Validated instance of `LLMRequest.schema`; None when the output did not conform."""
    schema_error: str | None = None
    usage: LLMUsage | None = None


class Complete(Protocol):
    async def __call__(self, request: LLMRequest) -> LLMReply: ...
