"""The single entry point through which the application talks to a language model.

The client speaks the OpenAI-compatible chat completions protocol only. Engine and model
specifics (served model name, how thinking is switched, which extra request fields an engine
needs) come from `config/` so that switching engine or model never changes calling code.

Every request is sent as a stream internally so that time to first token is always measured;
`chat()` collects the stream, `chat_stream()` exposes it.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from services.settings import LLMSettings, load_llm_settings

Message = Mapping[str, Any]
Schema = type[BaseModel] | Mapping[str, Any]


class LLMError(RuntimeError):
    """The server rejected the request or the response could not be read."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RequestCancelled(LLMError):
    """The request was cancelled through `LLMClient.cancel`."""


class CallMetrics(BaseModel):
    """Measurements recorded for every call."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # None when the engine does not report prefix cache hits.
    cached_tokens: int | None = None
    # Seconds from sending the request to the first generated token (content or reasoning).
    ttft_s: float | None = None
    total_s: float

    @property
    def output_tokens_per_s(self) -> float | None:
        if not self.completion_tokens or self.ttft_s is None:
            return None
        decode = self.total_s - self.ttft_s
        return self.completion_tokens / decode if decode > 0 else None


class ChatResult(BaseModel):
    content: str
    reasoning: str | None = None
    finish_reason: str | None = None
    # Set when a schema was given: the validated object (pydantic model or dict).
    parsed: Any = None
    # Set when a schema was given and the content did not conform to it.
    schema_error: str | None = None
    metrics: CallMetrics


class StreamDelta(BaseModel):
    kind: Literal["content", "reasoning"]
    text: str


class _Usage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None


class LLMClient:
    """Asynchronous OpenAI-compatible chat client.

    Construct with `LLMClient.from_config()` in application code. The explicit constructor
    exists for tests and tools; `transport` lets tests replace the network.
    """

    def __init__(
        self,
        settings: LLMSettings,
        *,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.AsyncClient(
            base_url=settings.base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(settings.request_timeout_s, connect=settings.connect_timeout_s),
            transport=transport,
        )
        self._active: dict[str, asyncio.Task[None]] = {}

    @classmethod
    def from_config(
        cls,
        config_dir: str | Path = "config",
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> LLMClient:
        settings = load_llm_settings(config_dir)
        api_key = os.environ.get(settings.api_key_env) if settings.api_key_env else None
        return cls(settings, api_key=api_key, transport=transport)

    @property
    def settings(self) -> LLMSettings:
        return self._settings

    async def aclose(self) -> None:
        for task in list(self._active.values()):
            task.cancel()
        await self._http.aclose()

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # Public API ---------------------------------------------------------------------------

    async def chat(
        self,
        messages: Sequence[Message],
        schema: Schema | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        thinking: bool | None = None,
        *,
        request_id: str | None = None,
    ) -> ChatResult:
        """Send one request and return the complete answer."""
        result: ChatResult | None = None
        async for item in self.chat_stream(
            messages,
            schema=schema,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking=thinking,
            request_id=request_id,
        ):
            if isinstance(item, ChatResult):
                result = item
        if result is None:  # pragma: no cover - chat_stream always ends with a result
            raise LLMError("stream ended without a result")
        return result

    async def chat_stream(
        self,
        messages: Sequence[Message],
        schema: Schema | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        thinking: bool | None = None,
        *,
        request_id: str | None = None,
    ) -> AsyncIterator[StreamDelta | ChatResult]:
        """Yield text deltas as they arrive; the last item is always the `ChatResult`.

        Leaving the loop early (break, exception, task cancellation) aborts the request and
        closes the connection, which makes the engine drop the sequence.
        """
        request_id = request_id or uuid.uuid4().hex
        if request_id in self._active:
            raise ValueError(f"request_id already running: {request_id}")
        body = self._build_body(messages, schema, max_tokens, temperature, thinking)
        queue: asyncio.Queue[StreamDelta | ChatResult | BaseException] = asyncio.Queue()
        task = asyncio.create_task(self._run(request_id, body, schema, queue))
        self._active[request_id] = task
        try:
            while True:
                getter = asyncio.ensure_future(queue.get())
                done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
                if getter not in done:
                    getter.cancel()
                    if task.cancelled():
                        raise RequestCancelled(f"request {request_id} cancelled")
                    # The worker finished; drain what it queued before it ended.
                    if queue.empty():
                        exc = task.exception()
                        raise exc or LLMError("worker ended without a result")
                    item = queue.get_nowait()
                else:
                    item = getter.result()
                if isinstance(item, BaseException):
                    raise item
                yield item
                if isinstance(item, ChatResult):
                    return
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self._active.pop(request_id, None)

    def cancel(self, request_id: str) -> bool:
        """Abort a running request. Returns False when no such request is running."""
        task = self._active.get(request_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def running(self) -> list[str]:
        return [rid for rid, task in self._active.items() if not task.done()]

    # Internals ----------------------------------------------------------------------------

    def _build_body(
        self,
        messages: Sequence[Message],
        schema: Schema | None,
        max_tokens: int | None,
        temperature: float | None,
        thinking: bool | None,
    ) -> dict[str, Any]:
        s = self._settings
        body: dict[str, Any] = {
            "model": s.served_model_name,
            "messages": [dict(m) for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": max_tokens if max_tokens is not None else s.default_max_tokens,
        }
        temp = temperature if temperature is not None else s.default_temperature
        if temp is not None:
            body["temperature"] = temp
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": _schema_name(schema),
                    "schema": _json_schema(schema),
                    "strict": True,
                },
            }
        _deep_merge(body, s.extra_body)
        if thinking is not None:
            _deep_merge(body, s.thinking_on if thinking else s.thinking_off)
        return body

    async def _run(
        self,
        request_id: str,
        body: dict[str, Any],
        schema: Schema | None,
        queue: asyncio.Queue[StreamDelta | ChatResult | BaseException],
    ) -> None:
        started = time.perf_counter()
        first_token_at: float | None = None
        content: list[str] = []
        reasoning: list[str] = []
        finish_reason: str | None = None
        usage = _Usage()
        try:
            async with self._http.stream("POST", "/chat/completions", json=body) as resp:
                if resp.status_code >= 400:
                    text = (await resp.aread()).decode("utf-8", "replace")
                    raise LLMError(f"HTTP {resp.status_code}: {text[:2000]}", resp.status_code)
                async for data in _sse_data(resp):
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if "error" in chunk:
                        raise LLMError(f"engine error: {chunk['error']}")
                    if chunk.get("usage"):
                        usage = _parse_usage(chunk["usage"])
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        r_text = delta.get("reasoning_content") or delta.get("reasoning")
                        c_text = delta.get("content")
                        for kind, text in (("reasoning", r_text), ("content", c_text)):
                            if not text:
                                continue
                            if first_token_at is None:
                                first_token_at = time.perf_counter()
                            (reasoning if kind == "reasoning" else content).append(text)
                            await queue.put(StreamDelta(kind=kind, text=text))
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
        except (LLMError, asyncio.CancelledError):
            raise
        except httpx.HTTPError as exc:
            raise LLMError(f"transport error: {exc!r}") from exc
        except json.JSONDecodeError as exc:
            raise LLMError(f"malformed stream chunk: {exc}") from exc

        metrics = CallMetrics(
            request_id=request_id,
            model=body["model"],
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cached_tokens=usage.cached_tokens,
            ttft_s=(first_token_at - started) if first_token_at is not None else None,
            total_s=time.perf_counter() - started,
        )
        text = "".join(content)
        parsed, schema_error = (None, None)
        if schema is not None:
            parsed, schema_error = _validate(text, schema)
        await queue.put(
            ChatResult(
                content=text,
                reasoning="".join(reasoning) or None,
                finish_reason=finish_reason,
                parsed=parsed,
                schema_error=schema_error,
                metrics=metrics,
            )
        )


async def _sse_data(resp: httpx.Response) -> AsyncIterator[str]:
    async for line in resp.aiter_lines():
        if line.startswith("data:"):
            yield line[5:].strip()


def _parse_usage(raw: Mapping[str, Any]) -> _Usage:
    details = raw.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens")
    if cached is None:
        cached = raw.get("cached_tokens")
    return _Usage(
        prompt_tokens=raw.get("prompt_tokens"),
        completion_tokens=raw.get("completion_tokens"),
        cached_tokens=cached,
    )


def _schema_name(schema: Schema) -> str:
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.__name__
    return str(schema.get("title") or "output")


def _json_schema(schema: Schema) -> dict[str, Any]:
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema.model_json_schema()
    return dict(schema)


def _validate(text: str, schema: Schema) -> tuple[Any, str | None]:
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        try:
            return schema.model_validate_json(text), None
        except ValidationError as exc:
            return None, str(exc)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    error = _check_json_schema(value, schema)
    return (value, None) if error is None else (None, error)


def _check_json_schema(value: Any, schema: Mapping[str, Any]) -> str | None:
    """Minimal structural check for raw dict schemas (types, required keys).

    Pydantic schemas are the norm in this code base; raw schemas are only used by tools.
    """
    expected = schema.get("type")
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
    }
    if expected in types and not isinstance(value, types[expected]):
        return f"expected {expected}, got {type(value).__name__}"
    if expected == "object":
        for key in schema.get("required", []):
            if key not in value:
                return f"missing required key: {key}"
        for key, sub in (schema.get("properties") or {}).items():
            if key in value:
                err = _check_json_schema(value[key], sub)
                if err:
                    return f"{key}: {err}"
    if expected == "array" and "items" in schema:
        for i, item in enumerate(value):
            err = _check_json_schema(item, schema["items"])
            if err:
                return f"[{i}]: {err}"
    return None


def _deep_merge(target: dict[str, Any], extra: Mapping[str, Any]) -> None:
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = json.loads(json.dumps(value))


__all__ = [
    "CallMetrics",
    "ChatResult",
    "LLMClient",
    "LLMError",
    "RequestCancelled",
    "StreamDelta",
]
