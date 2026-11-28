"""Issue #11: with Ollama as the model server, thinking is switched by the engine's own fields.

Ollama's OpenAI endpoint ignores `chat_template_kwargs` (the model's fields, which vLLM and SGLang
read) and reads `reasoning_effort` ("none" -> think=false). Thinking kept running, its tokens came
out of max_tokens and the 512-token cluster label call was truncated. Verified against Ollama
0.40.19 with qwen3:0.6b: chat_template_kwargs gave 608 characters of reasoning, reasoning_effort
"none" gave none."""

from __future__ import annotations

import logging

import pytest

from services.llm_client import LLMClient
from services.settings import load_engines, load_llm_settings
from tests.fake_openai import FakeReply, FakeServer
from tests.test_llm_client import MESSAGES, make_settings


def test_ollama_engine_settings(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "ollama")
    monkeypatch.setenv("LLM_BASE_URL", "http://gpu-sunucu:11434/v1")
    s = load_llm_settings()
    assert s.engine == "ollama" and s.base_url == "http://gpu-sunucu:11434/v1"
    assert s.thinking_off == {"reasoning_effort": "none"}
    assert s.thinking_on == {"reasoning_effort": "high"}
    assert s.served_model_name == "qwen3.8:27b"  # Ollama's tag, not the vLLM served name


def test_other_engines_keep_the_models_thinking_fields(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "vllm")
    s = load_llm_settings()
    assert s.thinking_off == {"chat_template_kwargs": {"enable_thinking": False}}
    assert s.served_model_name == "qwen3.8-27b"


def test_external_engine_is_never_launched():
    from scripts.infra_render import engine_argv, render_compose

    engines = load_engines()
    assert engines["ollama"].external and not engines["ollama"].image
    assert "ollama" not in render_compose()
    with pytest.raises(ValueError, match="external"):
        engine_argv("ollama", "qwen3.8-27b")


def test_a_launched_engine_needs_image_and_command():
    from services.settings import EngineSpec

    with pytest.raises(ValueError, match="image and command"):
        EngineSpec(port=1)
    assert EngineSpec(port=1, external=True).external


async def test_request_carries_reasoning_effort_and_not_chat_template_kwargs():
    server = FakeServer()
    settings = make_settings(
        engine="ollama",
        thinking_on={"reasoning_effort": "high"},
        thinking_off={"reasoning_effort": "none"},
    )
    client = LLMClient(settings, transport=server.transport())
    server.reply = FakeReply(content="x")
    await client.chat(MESSAGES, thinking=False)
    req = server.requests[0]
    assert req["reasoning_effort"] == "none" and "chat_template_kwargs" not in req
    await client.aclose()


async def test_reasoning_despite_thinking_off_is_logged_once(caplog):
    server = FakeServer()
    client = LLMClient(make_settings(engine="ollama"), transport=server.transport())
    server.reply = FakeReply(content="x", reasoning="yine de düşündü")
    with caplog.at_level(logging.WARNING, logger="services.llm_client"):
        await client.chat(MESSAGES, thinking=False)
        await client.chat(MESSAGES, thinking=False)
        await client.chat(MESSAGES, thinking=True)  # asked for: no warning
    warnings = [r for r in caplog.records if "reasoning" in r.getMessage()]
    assert len(warnings) == 1 and "'ollama'" in warnings[0].getMessage()
    await client.aclose()
