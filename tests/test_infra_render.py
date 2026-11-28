import os
import subprocess
from pathlib import Path

import pytest
import yaml

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


@pytest.mark.parametrize("engine", sorted(k for k, e in load_engines().items() if not e.external))
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
    body = pod_body("vllm", "qwen3.8-27b", "vol123", download=True, deadline=2000000000)
    assert body["gpu"]["id"] == "NVIDIA RTX PRO 6000 Blackwell Server Edition"
    assert body["cloud"] == "SECURE" and body["dataCenterIds"] == ["EU-RO-1"]
    assert body["mounts"]["network"] == [{"volumeId": "vol123", "path": "/models"}]
    assert body["env"]["HF_TOKEN"] == "{{ RUNPOD_SECRET_HF_TOKEN }}"
    assert "8000/http" in body["ports"] and "8001/http" in body["ports"]
    assert body["entrypoint"][:2] == ["bash", "-c"]
    no_dl = pod_body("sglang", "qwen3.8-27b", "vol123", download=False, deadline=2000000000)
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


def test_overrides_change_only_server_settings():
    from scripts.runpod import parse_overrides

    ov = parse_overrides(["max_num_seqs=64", "context_length=16384", "gpu_memory_utilization=0.85"])
    assert ov == {"max_num_seqs": 64, "context_length": 16384, "gpu_memory_utilization": 0.85}
    argv = engine_argv("vllm", "qwen3.8-27b", overrides=ov)
    assert argv[argv.index("--max-num-seqs") + 1] == "64"
    assert argv[argv.index("--max-model-len") + 1] == "16384"
    sg = engine_argv("sglang", "qwen3.8-27b", overrides=ov)
    assert sg[sg.index("--max-running-requests") + 1] == "64"
    with pytest.raises(ValueError):
        engine_argv("vllm", "qwen3.8-27b", overrides={"bogus": 1})


def _compose() -> dict:
    import yaml

    return yaml.safe_load(render_compose())


def test_external_profile_runs_only_postgres_and_the_app():
    """`harici` (paket 10): the model and embedding servers are elsewhere; nothing with a GPU
    or a model image starts."""
    services = _compose()["services"]
    harici = {name for name, svc in services.items() if "harici" in svc.get("profiles", [])}
    always = {name for name, svc in services.items() if "profiles" not in svc}
    assert always == {"postgres", "app"} and harici == set()
    for engine, spec in load_engines().items():
        if spec.external:  # e.g. Ollama: never a Compose service (issue #11)
            assert engine not in services
            continue
        assert engine in services["embedding"]["profiles"]
        assert services[engine]["networks"]["default"]["aliases"] == ["llm"]


def test_app_service_reads_secrets_from_env_only(monkeypatch):
    monkeypatch.setenv("TESTMENTOR_AUTH_SECRET", "gizli-deger-123")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pg-gizli-456")
    text = render_compose()
    assert "gizli-deger-123" not in text and "pg-gizli-456" not in text
    app = _compose()["services"]["app"]
    env = app["environment"]
    assert env["TESTMENTOR_PG_DSN"].startswith("postgresql://testmentor:${POSTGRES_PASSWORD}@")
    assert env["TESTMENTOR_AUTH_MODE"] == "${TESTMENTOR_AUTH_MODE:-password}"
    assert env["LLM_HOST"] == "llm" and env["LLM_BASE_URL"] == "${LLM_BASE_URL:-}"
    assert app["build"] == {"context": "..", "dockerfile": "infra/app.Dockerfile"}
    assert app["depends_on"] == {"postgres": {"condition": "service_healthy"}}
    assert "/auth/config" in " ".join(app["healthcheck"]["test"])
    assert (ROOT / "infra" / "app.Dockerfile").exists()


def test_llm_host_fills_the_base_url(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setenv("LLM_ENGINE", "vllm")
    monkeypatch.setenv("LLM_HOST", "llm")
    assert load_llm_settings().base_url == "http://llm:8000/v1"
    monkeypatch.delenv("LLM_HOST")
    assert load_llm_settings().base_url == "http://localhost:8000/v1"
    monkeypatch.setenv("LLM_BASE_URL", "http://gpu.kurum:8000/v1")
    monkeypatch.setenv("LLM_HOST", "llm")
    assert load_llm_settings().base_url == "http://gpu.kurum:8000/v1"


# Paket 12: internetsiz kurulum ------------------------------------------------------------


def _rendered(bundle=None) -> dict:
    text = render_compose(bundle=bundle)
    return yaml.safe_load(text)


def test_gpu_services_run_offline():
    infra = yaml.safe_load((ROOT / "config" / "infra.yaml").read_text(encoding="utf-8"))
    offline = infra["offline"]["env"]
    assert offline["HF_HUB_OFFLINE"] == "1" and "TRANSFORMERS_OFFLINE" in offline
    services = _rendered()["services"]
    gpu = [n for n, s in services.items() if "deploy" in s]
    assert "embedding" in gpu and len(gpu) >= 2
    for name in gpu:
        env = services[name]["environment"]
        for key, value in offline.items():
            assert env[key] == f"${{{key}:-{value}}}", (name, key)


def test_server_sizing_is_set_in_env_with_config_defaults():
    infra = yaml.safe_load((ROOT / "config" / "infra.yaml").read_text(encoding="utf-8"))
    names = infra["offline"]["sizing_env"]
    services = _rendered()["services"]
    runtime = yaml.safe_load((ROOT / "config" / "runtime.yaml").read_text(encoding="utf-8"))
    models = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
    model = models["models"][runtime["llm"]["model"]]
    line = services["vllm"]["command"][0]
    assert f"${{{names['context_length']}:-{model['context_length']}}}" in line
    assert f"${{{names['max_num_seqs']}:-{model['max_num_seqs']}}}" in line
    assert f"${{{names['gpu_memory_utilization']}:-" in line and "@@" not in line
    emb = services["embedding"]["command"][0]
    assert f"${{{infra['offline']['embedding_memory_env']}:-" in emb


def test_bundle_compose_never_builds_or_pulls():
    doc = _rendered(bundle={"app_image": "testmentor-app:abc123"})
    services = doc["services"]
    assert all(s.get("pull_policy") == "never" for s in services.values())
    assert all("build" not in s for s in services.values())
    app = services["app"]
    assert app["image"] == "testmentor-app:abc123"
    assert "./config:/app/config:ro" in app["volumes"]
    assert any(v.startswith("${TESTMENTOR_DATA_DIR:-./data}") for v in app["volumes"])
    assert "./initdb:/docker-entrypoint-initdb.d:ro" in services["postgres"]["volumes"]
    gpu = [s for s in services.values() if "deploy" in s]
    assert all("${MODELS_DIR:-./models}:/models" in s["volumes"] for s in gpu)


def test_offline_rehearsal_proxies_only_the_model_servers():
    script = render_pod_script("vllm", "qwen3.8-27b", offline_rehearsal=True)
    lines = script.splitlines()
    proxied = [ln for ln in lines if "HTTPS_PROXY=" in ln]
    assert len(proxied) == 2  # embedding and model server
    assert all(" serve " in ln for ln in proxied)
    watchdog = script[: script.index("export HF_HUB_OFFLINE")]
    assert "PROXY" not in watchdog and "self_delete" in watchdog  # the watchdog keeps its network
    assert "[refs]" in script
    normal = render_pod_script("vllm", "qwen3.8-27b")
    assert "PROXY" not in normal and "TRANSFORMERS_OFFLINE=1" in normal
