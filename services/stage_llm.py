"""`core.llm.Complete` over `LLMClient` (paket 3): the only way stage producers reach the model."""

from __future__ import annotations

from core.llm import LLMReply, LLMRequest, LLMUsage
from services.llm_client import ChatResult, LLMClient, LLMError


class ClientComplete:
    """Streams `request` through `LLMClient.chat_stream` with the request's schema and params;
    returns content, the parsed pydantic instance (or None and the schema error) and usage from
    `CallMetrics`. `LLMError` propagates; cancelling the awaiting task aborts the stream."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def __call__(self, request: LLMRequest) -> LLMReply:
        p = request.params
        result: ChatResult | None = None
        async for item in self.client.chat_stream(
            list(request.messages),
            schema=request.schema,
            max_tokens=p.max_tokens,
            temperature=p.temperature,
            thinking=p.thinking,
        ):
            if isinstance(item, ChatResult):
                result = item
        if result is None:  # pragma: no cover - chat_stream always ends with a result
            raise LLMError("stream ended without a result")
        m = result.metrics
        return LLMReply(
            content=result.content,
            parsed=result.parsed,
            schema_error=result.schema_error,
            usage=LLMUsage(
                prompt_tokens=m.prompt_tokens,
                completion_tokens=m.completion_tokens,
                cached_tokens=m.cached_tokens,
                ttft_s=m.ttft_s,
                total_s=m.total_s,
            ),
        )
