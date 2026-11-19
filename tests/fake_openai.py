"""A fake OpenAI-compatible chat endpoint for unit tests (no model, no network)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class FakeReply:
    content: str = ""
    reasoning: str = ""
    prompt_tokens: int = 100
    completion_tokens: int = 10
    cached_tokens: int | None = None
    # Report cached tokens SGLang-style (top level) instead of prompt_tokens_details.
    cached_top_level: bool = False
    chunk_size: int = 4
    delay_s: float = 0.0
    first_delay_s: float = 0.0
    status_code: int = 200
    error_body: str = ""


@dataclass
class FakeServer:
    reply: FakeReply = field(default_factory=FakeReply)
    requests: list[dict[str, Any]] = field(default_factory=list)
    finished_streams: int = 0
    aborted_streams: int = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"path": request.url.path, "headers": dict(request.headers), **body})
        r = self.reply
        if r.status_code >= 400:
            return httpx.Response(r.status_code, text=r.error_body or "bad request")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=self._stream(body["model"]),
        )

    async def _stream(self, model: str) -> AsyncIterator[bytes]:
        r = self.reply
        try:
            if r.first_delay_s:
                await asyncio.sleep(r.first_delay_s)
            for kind, text in (("reasoning_content", r.reasoning), ("content", r.content)):
                for i in range(0, len(text), r.chunk_size):
                    piece = text[i : i + r.chunk_size]
                    yield _event(model, {"delta": {kind: piece}, "finish_reason": None})
                    if r.delay_s:
                        await asyncio.sleep(r.delay_s)
            yield _event(model, {"delta": {}, "finish_reason": "stop"})
            usage: dict[str, Any] = {
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.prompt_tokens + r.completion_tokens,
            }
            if r.cached_tokens is not None:
                if r.cached_top_level:
                    usage["cached_tokens"] = r.cached_tokens
                else:
                    usage["prompt_tokens_details"] = {"cached_tokens": r.cached_tokens}
            yield _sse({"id": "x", "model": model, "choices": [], "usage": usage})
            yield b"data: [DONE]\n\n"
            self.finished_streams += 1
        except (asyncio.CancelledError, GeneratorExit):
            self.aborted_streams += 1
            raise


def _event(model: str, choice: dict[str, Any]) -> bytes:
    return _sse({"id": "x", "model": model, "choices": [{"index": 0, **choice}]})


def _sse(obj: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()
