"""Deterministic stand-ins for the model and the embedding service (no GPU, no network).

Shared by every package's end-to-end tests, the API's development mode (`TESTMENTOR_FAKE_LLM=1`)
and the frontend's Playwright tests. The replies follow the prompts' structure the same way
tests/stages/helpers.py does: one test case per requirement whose methods include the test
method, repair calls answer only the listed ids, incremental calls add a case per added id.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from core.llm import LLMReply, LLMRequest, LLMUsage

_ROW = re.compile(r"^([\w.-]+) \((\w*)\)(?: \[methods: ([^\]]*)\])?:", re.M)


def _rows(req: LLMRequest) -> list[tuple[str, list[str]]]:
    user = req.messages[-1]["content"]
    block = user[user.rindex("# Requirements\n") :]
    nxt = block.find("\n\n#", 1)
    block = block if nxt < 0 else block[:nxt]
    return [(m[0], m[2].split(", ") if m[2] else []) for m in _ROW.findall(block)]


def _case(rid: str, n: int, language: str = "tr") -> dict[str, Any]:
    tr = language != "en"
    return {
        "id": f"T{n}",
        "title": f"{rid} {'temel davranışı' if tr else 'basic behaviour'}",
        "covers": [rid],
        "type": "Normal",
        "priority": "Orta",
        "preconditions": "",
        "test_inputs": "",
        "assumptions": "",
        "steps": [
            {
                "no": 1,
                "action": f"{rid} {'işlemini başlat' if tr else 'start the operation'}",
                "expected": "Sistem gereksinimde tanımlanan davranışı gösterir"
                if tr
                else "The system shows the behaviour the requirement states",
            }
        ],
    }


class FakeComplete:
    """`core.llm.Complete`. `delay_s` simulates generation time (cancellation tests)."""

    def __init__(self, test_method: str = "Test", delay_s: float = 0.0) -> None:
        self.test_method = test_method
        self.delay_s = delay_s
        self.requests: list[LLMRequest] = []

    def reply(self, req: LLMRequest) -> Any:
        name = req.schema.__name__
        user = req.messages[-1]["content"]
        if name == "TestCaseSet":
            rows = _rows(req)
            m = re.search(r"The requirements (.+) are not covered yet", user)
            ids = (
                [i.strip() for i in m.group(1).split(",")]
                if m
                else [rid for rid, methods in rows if self.test_method in methods]
            )
            return {"test_cases": [_case(i, n) for n, i in enumerate(ids or [rows[0][0]])]}
        if name == "TestCaseDelta":
            m = re.search(r"^Added: (.+)$", user, re.M)
            added = [i.strip() for i in m.group(1).split(",")] if m else []
            return {"add": [_case(i, n) for n, i in enumerate(added)], "update": []}
        if name == "MergeDecision":
            return {"drop": []}
        if name == "ClusterLabel":
            ids = [rid for rid, _ in _rows(req)]
            return {"name": f"Öbek {ids[0]}" if ids else "Öbek", "rationale": "Ortak konu."}
        if name == "MethodBatch":
            return {
                "decisions": [
                    {"requirement_id": rid, "methods": [self.test_method], "rationale": "x"}
                    for rid, _ in _rows(req)
                ]
            }
        raise ValueError(f"no fake reply for schema {name}")

    async def __call__(self, request: LLMRequest) -> LLMReply:
        self.requests.append(request)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        content = json.dumps(self.reply(request), ensure_ascii=False)
        try:
            parsed = request.schema.model_validate_json(content)
            error = None
        except ValidationError as exc:
            parsed, error = None, str(exc)
        return LLMReply(
            content=content,
            parsed=parsed,
            schema_error=error,
            usage=LLMUsage(prompt_tokens=100, completion_tokens=len(content) // 4),
            finish_reason="stop",
        )


class FakeEmbed:
    """`core.stages.base.Embed`: bag-of-words hashed into `dim` buckets, L2-normalised, so that
    texts sharing words are close (clustering behaves plausibly)."""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim
        self.calls = 0

    def vector(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for w in re.findall(r"\w+", text.lower()):
            if len(w) < 3:
                continue
            h = int(hashlib.sha256(w.encode()).hexdigest()[:8], 16)
            v[h % self.dim] += 1.0
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / norm for x in v]

    async def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [self.vector(t) for t in texts]
