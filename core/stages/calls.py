"""Shared pieces of the producers: one model call with the schema retry, and result building."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from core.llm import LLMParams, LLMRequest, LLMUsage, Message
from core.nodes import NodeContent, NodeKind, NodeRef, ProducedBy, Result, TestCaseContent
from core.prompts import append_tail, schema_retry_section
from core.schemas import plain

if TYPE_CHECKING:
    from core.graph import ProjectState
    from core.llm import Complete


class CallFailed(Exception):
    """The output did not match the schema after the one retry."""


@dataclass
class CallLog:
    """Model calls of one node (or one batch), for `ProduceOutcome.stats`."""

    calls: int = 0
    usage: list[LLMUsage] = field(default_factory=list)

    def stats(self) -> dict[str, Any]:
        def total(name: str) -> int | None:
            values = [getattr(u, name) for u in self.usage if getattr(u, name) is not None]
            return sum(values) if values else None

        return {
            "calls": self.calls,
            "prompt_tokens": total("prompt_tokens"),
            "completion_tokens": total("completion_tokens"),
            "cached_tokens": total("cached_tokens"),
        }


async def call(
    complete: Complete,
    log: CallLog,
    *,
    stage: NodeKind,
    unit: str,
    messages: Sequence[Message],
    schema: type[BaseModel],
    params: LLMParams,
) -> Any:
    """One call; on a schema error one retry with `schema_retry_section` appended. Returns the
    parsed output as plain JSON; raises `CallFailed` after a second schema error, or at once when
    the output was truncated (`finish_reason == "length"`: a retry doubles the cost and most
    likely repeats the degeneration)."""
    msgs = list(messages)
    error = ""
    for attempt in range(2):
        reply = await complete(
            LLMRequest(
                stage=stage,
                unit=unit if attempt == 0 else f"{unit}/retry",
                messages=tuple(msgs),
                schema=schema,
                params=params,
            )
        )
        log.calls += 1
        if reply.usage is not None:
            log.usage.append(reply.usage)
        if reply.parsed is not None:
            return plain(reply.parsed)
        error = reply.schema_error or "output does not match the schema"
        if reply.finish_reason == "length":
            # Cut at max_tokens: a retry doubles the costliest call and most likely degenerates
            # again (KDH-030, paket 3); no retry.
            raise CallFailed(f"output truncated at max_tokens ({params.max_tokens}): {error}")
        msgs = append_tail(messages, schema_retry_section(error))
    raise CallFailed(error)


def result(
    state: ProjectState,
    ref: NodeRef,
    content: NodeContent,
    *,
    mode: str,
    extra_params: dict[str, Any] | None = None,
    cases: Sequence[TestCaseContent] = (),
) -> Result:
    """A result keyed to `state` (expected hash and cache key of the job's snapshot), with the
    stage config as `produced_by`."""
    from core.graph import cache_key, expected_hash  # core.graph imports core.stages

    cfg = state.stage_configs[ref.kind]
    return Result(
        input_hash=expected_hash(state, ref),
        cache_key=cache_key(state, ref),
        content=content,
        produced_by=ProducedBy(
            mode=mode,
            model=cfg.model,
            prompt_version=cfg.prompt_version,
            params={**cfg.params, **(extra_params or {})},
        ),
        cases=tuple(cases),
    )
