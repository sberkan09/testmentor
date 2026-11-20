"""`core.llm.Complete` over `LLMClient` (paket 3): the only way stage producers reach the model."""

from __future__ import annotations

from core.llm import LLMReply, LLMRequest
from services.llm_client import LLMClient


class ClientComplete:
    """Streams `request` through `LLMClient.chat_stream` with the request's schema and params;
    returns content, the parsed pydantic instance (or None and the schema error) and usage from
    `CallMetrics`. `LLMError` propagates; cancelling the awaiting task aborts the stream."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def __call__(self, request: LLMRequest) -> LLMReply:
        raise NotImplementedError("paket 3 adım 4")
