"""Local record of the Runpod resources this package created (infra/.runpod-state.json).

Only resources listed here are ever stopped or deleted by our scripts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "infra" / ".runpod-state.json"
ENV_PATH = ROOT / ".env"


def read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def proxy_url(pod_id: str, port: int) -> str:
    return f"https://{pod_id}-{port}.proxy.runpod.net"


def base_urls_from_state() -> dict[str, str] | None:
    pod = read_state().get("pod")
    if not pod:
        return None
    return {
        "llm": proxy_url(pod["id"], pod["llm_port"]) + "/v1",
        "embedding": proxy_url(pod["id"], pod["embedding_port"]) + "/v1",
    }


def read_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    out = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def ensure_env_secret(name: str) -> str:
    """Return a value from .env, generating and storing a random one when missing."""
    import secrets

    env = read_env()
    if env.get(name):
        return env[name]
    value = secrets.token_urlsafe(32)
    with ENV_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{name}={value}\n")
    ENV_PATH.chmod(0o600)
    return value
