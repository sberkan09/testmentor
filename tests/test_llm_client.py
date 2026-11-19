import asyncio
import json

import pytest
from pydantic import BaseModel

from services.llm_client import (
    ChatResult,
    LLMClient,
    LLMError,
    RequestCancelled,
    StreamDelta,
)
from services.settings import LLMSettings
from tests.fake_openai import FakeReply, FakeServer


class Step(BaseModel):
    no: int
    action: str
    expected: str


class Case(BaseModel):
    title: str
    steps: list[Step]


VALID_CASE = json.dumps(
    {"title": "Oturum açma", "steps": [{"no": 1, "action": "Giriş", "expected": "Açılır"}]},
    ensure_ascii=False,
)

MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "u"}]


def make_settings(**overrides) -> LLMSettings:
    base = dict(
        engine="vllm",
        model="m",
        base_url="http://fake/v1",
        served_model_name="served-m",
        default_max_tokens=512,
        extra_body={"top_k": 20},
        thinking_on={"chat_template_kwargs": {"enable_thinking": True}},
        thinking_off={"chat_template_kwargs": {"enable_thinking": False}},
    )
    base.update(overrides)
    return LLMSettings(**base)


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
async def client(server: FakeServer):
    c = LLMClient(make_settings(), api_key="k", transport=server.transport())
    yield c
    await c.aclose()


async def test_chat_collects_content_and_metrics(server, client):
    server.reply = FakeReply(
        content="merhaba dünya", prompt_tokens=120, completion_tokens=7, cached_tokens=96
    )
    result = await client.chat(MESSAGES)
    assert result.content == "merhaba dünya"
    assert result.finish_reason == "stop"
    m = result.metrics
    assert (m.prompt_tokens, m.completion_tokens, m.cached_tokens) == (120, 7, 96)
    assert m.ttft_s is not None and 0 <= m.ttft_s <= m.total_s
    assert m.model == "served-m"


async def test_cached_tokens_none_when_not_reported(server, client):
    server.reply = FakeReply(content="x")
    result = await client.chat(MESSAGES)
    assert result.metrics.cached_tokens is None


async def test_cached_tokens_top_level_form(server, client):
    server.reply = FakeReply(content="x", cached_tokens=64, cached_top_level=True)
    result = await client.chat(MESSAGES)
    assert result.metrics.cached_tokens == 64


async def test_request_body(server, client):
    server.reply = FakeReply(content=VALID_CASE)
    await client.chat(MESSAGES, schema=Case, max_tokens=99, temperature=0.0, thinking=False)
    req = server.requests[0]
    assert req["path"] == "/v1/chat/completions"
    assert req["headers"]["authorization"] == "Bearer k"
    assert req["model"] == "served-m"
    assert req["messages"] == MESSAGES
    assert req["stream"] is True
    assert req["stream_options"] == {"include_usage": True}
    assert req["max_tokens"] == 99
    assert req["temperature"] == 0.0
    assert req["top_k"] == 20
    assert req["chat_template_kwargs"] == {"enable_thinking": False}
    rf = req["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "Case"
    assert rf["json_schema"]["schema"] == Case.model_json_schema()


async def test_defaults_and_thinking_unset(server, client):
    server.reply = FakeReply(content="x")
    await client.chat(MESSAGES)
    req = server.requests[0]
    assert req["max_tokens"] == 512
    assert "temperature" not in req
    assert "chat_template_kwargs" not in req
    assert "response_format" not in req


async def test_thinking_on(server, client):
    server.reply = FakeReply(content="x", reasoning="önce düşün")
    result = await client.chat(MESSAGES, thinking=True)
    assert server.requests[0]["chat_template_kwargs"] == {"enable_thinking": True}
    assert result.reasoning == "önce düşün"
    assert result.content == "x"


async def test_schema_valid_parsed(server, client):
    server.reply = FakeReply(content=VALID_CASE)
    result = await client.chat(MESSAGES, schema=Case)
    assert result.schema_error is None
    assert isinstance(result.parsed, Case)
    assert result.parsed.steps[0].expected == "Açılır"


async def test_schema_invalid_reported(server, client):
    server.reply = FakeReply(content='{"title": "x"}')
    result = await client.chat(MESSAGES, schema=Case)
    assert result.parsed is None
    assert "steps" in result.schema_error


async def test_raw_dict_schema(server, client):
    schema = {
        "title": "Out",
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "integer"}},
    }
    server.reply = FakeReply(content='{"a": 1}')
    ok = await client.chat(MESSAGES, schema=schema)
    assert ok.parsed == {"a": 1} and ok.schema_error is None
    server.reply = FakeReply(content='{"a": "1"}')
    bad = await client.chat(MESSAGES, schema=schema)
    assert bad.parsed is None and "a" in bad.schema_error


async def test_stream_yields_deltas_then_result(server, client):
    server.reply = FakeReply(content="abcdefgh", reasoning="rr", chunk_size=3)
    items = [item async for item in client.chat_stream(MESSAGES)]
    assert isinstance(items[-1], ChatResult)
    deltas = [i for i in items[:-1] if isinstance(i, StreamDelta)]
    assert "".join(d.text for d in deltas if d.kind == "content") == "abcdefgh"
    assert "".join(d.text for d in deltas if d.kind == "reasoning") == "rr"
    assert items[-1].content == "abcdefgh"


async def test_cancel_running_request(server, client):
    server.reply = FakeReply(content="x" * 200, chunk_size=1, delay_s=0.01)
    task = asyncio.create_task(client.chat(MESSAGES, request_id="r1"))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if "r1" in client.running():
            break
    await asyncio.sleep(0.05)
    assert client.cancel("r1") is True
    with pytest.raises(RequestCancelled):
        await task
    assert client.running() == []
    assert client.cancel("r1") is False
    assert server.finished_streams == 0


async def test_cancel_before_first_token(server, client):
    server.reply = FakeReply(content="x", first_delay_s=5)
    task = asyncio.create_task(client.chat(MESSAGES, request_id="slow"))
    await asyncio.sleep(0.05)
    assert client.cancel("slow")
    with pytest.raises(RequestCancelled):
        await asyncio.wait_for(task, 1)


async def test_breaking_stream_aborts_request(server, client):
    server.reply = FakeReply(content="x" * 100, chunk_size=1, delay_s=0.005)
    async for item in client.chat_stream(MESSAGES, request_id="b"):
        assert isinstance(item, StreamDelta)
        break
    await asyncio.sleep(0.02)
    assert client.running() == []
    assert server.finished_streams == 0


async def test_duplicate_request_id_rejected(server, client):
    server.reply = FakeReply(content="x", first_delay_s=0.2)
    task = asyncio.create_task(client.chat(MESSAGES, request_id="dup"))
    await asyncio.sleep(0.02)
    with pytest.raises(ValueError):
        await client.chat(MESSAGES, request_id="dup")
    await task


async def test_http_error(server, client):
    server.reply = FakeReply(status_code=400, error_body="max_tokens too large")
    with pytest.raises(LLMError) as info:
        await client.chat(MESSAGES)
    assert info.value.status_code == 400
    assert "max_tokens too large" in str(info.value)


async def test_concurrent_requests(server, client):
    server.reply = FakeReply(content=VALID_CASE, delay_s=0.001)
    results = await asyncio.gather(*(client.chat(MESSAGES, schema=Case) for _ in range(16)))
    assert all(r.schema_error is None for r in results)
    assert len({r.metrics.request_id for r in results}) == 16
