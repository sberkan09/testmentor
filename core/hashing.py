"""Content addressing: `input_hash` = SHA-256 over ordered inputs, prompt version, model id and
generation parameters (docs/tasarim.md, Veri modeli)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def plain_hash(obj: Any) -> str:
    """SHA-256 of strictly plain JSON (dict, list, str, int, float, bool, None).

    Unlike `canonical`, nothing is stringified on the way: a set, a custom object or a
    numpy array raises `TypeError`, so a hash never silently depends on `str()` of a value.
    For plain data the digest equals `sha256(canonical(obj))`. Pydantic models are hashed via
    `model_dump(mode="json")` by the caller.
    """
    raise NotImplementedError


# `canonical` and `input_hash` must keep their exact output: the judge cache
# (eval/judge.py) and recorded run outputs are keyed by it. tests/core/test_hashing.py pins it.
def input_hash(*, inputs: Any, prompt_version: str, model: str, params: dict[str, Any]) -> str:
    payload = {"inputs": inputs, "prompt_version": prompt_version, "model": model, "params": params}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()
