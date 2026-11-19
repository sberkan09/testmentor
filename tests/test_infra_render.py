import os
import subprocess
from pathlib import Path

import pytest

from scripts.infra_render import (
    COMPOSE_PATH,
    embedding_argv,
    engine_argv,
    render_compose,
    render_pod_script,
)
from scripts.runpod import pod_body
from services.settings import load_engines, load_llm_settings, load_models

ROOT = Path(__file__).resolve().parent.parent


def test_committed_compose_is_up_to_date():
    assert COMPOSE_PATH.read_text(encoding="utf-8") == render_compose(), "make compose çalıştır"


@pytest.mark.parametrize("engine", sorted(load_engines()))
@pytest.mark.parametrize("model", sorted(load_models()))
def test_every_engine_model_pair_renders(engine, model):
    argv = engine_argv(engine, model)
    m = load_models()[model]
    assert m.repo_id in argv and m.served_name in argv
    assert str(m.context_length) in argv and str(m.max_num_seqs) in argv
    assert "$LLM_API_KEY" in argv
    assert not any("{" in a for a in argv), argv
    script = render_pod_script(engine, model)
    subprocess.run(["bash", "-n"], input=script, text=True, check=True)
    assert "export HF_HUB_OFFLINE=1" in script
    assert ("vllm serve BAAI/bge-m3" in script) == (engine == "vllm")


def test_download_script_lists_all_repos_and_goes_offline_after():
    script = render_pod_script("vllm", "qwen3.8-27b", download=True)
    for m in load_models().values():
        assert m.repo_id in script
    assert "BAAI/bge-m3" in script
    assert script.index("snapshot_download") < script.index("export HF_HUB_OFFLINE=1")


def test_api_key_never_rendered_literally(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "super-secret-value")
    text = render_compose() + render_pod_script("vllm", "qwen3.8-27b")
    assert "super-secret-value" not in text


def test_embedding_uses_pooling_runner():
    argv = embedding_argv()
    assert argv[argv.index("--runner") + 1] == "pooling"


def test_pod_body_shape(tmp_path, monkeypatch):
    import scripts.runpod_state as st

    monkeypatch.setattr(st, "ENV_PATH", tmp_path / ".env")
    body = pod_body("vllm", "qwen3.8-27b", "vol123", download=True)
    assert body["gpu"]["id"] == "NVIDIA RTX PRO 6000 Blackwell Server Edition"
    assert body["cloud"] == "SECURE" and body["dataCenterIds"] == ["EU-RO-1"]
    assert body["mounts"]["network"] == [{"volumeId": "vol123", "path": "/models"}]
    assert body["env"]["HF_TOKEN"] == "{{ RUNPOD_SECRET_HF_TOKEN }}"
    assert "8000/http" in body["ports"] and "8001/http" in body["ports"]
    assert body["entrypoint"][:2] == ["bash", "-c"]
    no_dl = pod_body("sglang", "qwen3.8-27b", "vol123", download=False)
    assert "HF_TOKEN" not in no_dl["env"]
    assert no_dl["image"].startswith("lmsysorg/sglang:")


def test_engine_switch_is_config_only(monkeypatch):
    """Switching engine changes settings, never the calling code."""
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setenv("LLM_ENGINE", "vllm")
    a = load_llm_settings()
    monkeypatch.setenv("LLM_ENGINE", "sglang")
    b = load_llm_settings()
    assert a.served_model_name == b.served_model_name
    assert a.base_url.endswith(":8000/v1") and b.base_url.endswith(":30000/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-oss-120b")
    c = load_llm_settings()
    assert c.thinking_off == {"reasoning_effort": "low"}


def test_no_engine_or_model_names_in_python_code():
    """CLAUDE.md: engine and model names live only in config/."""
    banned = ["Qwen/", "qwen3", "gemma", "gpt-oss", "lmsysorg", "vllm/vllm-openai"]
    for path in list((ROOT / "services").glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for word in banned:
            assert word.lower() not in text, f"{word} in {path}"
    assert os.path.exists(ROOT / "config" / "models.yaml")


def test_download_pod_body():
    from scripts.runpod import download_body

    body = download_body("vol1")
    assert body["cpu"]["id"] and body["cpu"]["vcpuCount"] in (2, 4, 8, 16, 32)
    assert "gpu" not in body
    assert body["env"]["HF_TOKEN"] == "{{ RUNPOD_SECRET_HF_TOKEN }}"
    script = body["entrypoint"][2]
    subprocess.run(["bash", "-n"], input=script, text=True, check=True)
    assert "[download] DONE" in script
