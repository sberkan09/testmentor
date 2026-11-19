"""Content addressing: `input_hash` = SHA-256 over ordered inputs, prompt version, model id and
generation parameters (docs/tasarim.md, Veri modeli)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def input_hash(*, inputs: Any, prompt_version: str, model: str, params: dict[str, Any]) -> str:
    payload = {"inputs": inputs, "prompt_version": prompt_version, "model": model, "params": params}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()
