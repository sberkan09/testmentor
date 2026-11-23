"""Shared layout for the stage producer tests (paket 3; no model, no network).

- `SETTINGS`: `StageSettings` from config/pipeline.yaml and the examples file, built here by hand
  (not through `services.settings`, which has its own tests).
- `ScriptedComplete`: a `core.llm.Complete` that records requests and answers with `smart_reply`
  (one case per Test requirement, Test for every method, ...) unless a test gives a handler.
- `drive`: a minimal wave driver (the eval driver and the paket 5 queue do the same job): produce
  every ready node, real producers for the kinds in `real`, the paket 2 fake producer for the
  rest; `settle_many` per wave; failed nodes marked failed.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

import core.stages  # noqa: F401  (registers the stages)
from core import stages
from core.graph import ProjectState, new_project
from core.invalidation import Hint, analyze, mark_failed, settle_many
from core.llm import LLMParams, LLMReply, LLMRequest
from core.nodes import (
    MethodDef,
    NodeKind,
    NodeRef,
    RequirementContent,
    TestCaseContent,
)
from core.settings import StageSettings
from core.stages.base import (
    Embed,
    ExampleSource,
    PassageSource,
    ProduceContext,
    ProduceOutcome,
    Retrieve,
    SelectExamples,
)
from tests.core.helpers import CONFIGS, fake_result

ROOT = Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
EXAMPLES = yaml.safe_load((ROOT / CFG["examples_file"]).read_text(encoding="utf-8"))

CARD_METHODS = tuple(MethodDef(name=m["name"], criterion=m["criterion"]) for m in CFG["methods"])
CARD_TEXT = "Project: Örnek portal (P)\nDomain: Kamu hizmeti"

SETTINGS = StageSettings(
    test_method=CFG["test_method"],
    test_types=tuple(CFG["test_types"]),
    priorities=tuple(CFG["priorities"]),
    examples=EXAMPLES,
    llm={
        NodeKind.METHOD: LLMParams(temperature=0.0, thinking=False, max_tokens=4096),
        NodeKind.CLUSTER_LABEL: LLMParams(temperature=0.0, thinking=False, max_tokens=512),
        NodeKind.TEST_SET: LLMParams(temperature=0.0, thinking=False, max_tokens=8192),
    },
)

REQS = {
    "R1": (
        "tr",
        "Sistem, kullanıcı girişini 3 başarısız denemeden sonra 15 dakika kilitlemelidir.",
    ),
    "R2": ("tr", "Sistem, parola sıfırlama bağlantısını 30 dakika geçerli tutmalıdır."),
    "R3": ("en", "The system shall log every configuration change with user and timestamp."),
    "R4": ("en", "The system shall export the audit log as CSV."),
    "R5": ("tr", "Sistem, rapor ekranını 2 saniye içinde açmalıdır."),
    "R6": ("en", "The system shall support 200 concurrent users."),
}
CLUSTERS = {"A": ("R1", "R2"), "B": ("R3", "R4"), "C": ("R5", "R6")}

TEST_KINDS = frozenset({NodeKind.TEST_SET})


def project(
    reqs: Mapping[str, tuple[str, str]] = REQS,
    clusters: Mapping[str, Sequence[str]] = CLUSTERS,
) -> ProjectState:
    """New project (every derived node a stale placeholder), card with the config methods."""
    return new_project(
        "P",
        requirements=[
            RequirementContent(id=k, language=lang, text=t) for k, (lang, t) in reqs.items()
        ],
        clusters=clusters,
        card=CARD_TEXT,
        index_version="v1",
        stage_configs=CONFIGS,
        methods=CARD_METHODS,
    )


def many_reqs(n: int, prefix: str = "Q") -> dict[str, tuple[str, str]]:
    return {
        f"{prefix}{i:03d}": ("tr", f"Sistem, {i} numaralı işlemi 2 saniye içinde tamamlamalıdır.")
        for i in range(1, n + 1)
    }


# Scripted model ---------------------------------------------------------------------------------

_ROW = re.compile(r"^([\w.-]+) \((\w*)\)(?: \[methods: ([^\]]*)\])?:", re.M)


def requirement_rows(req: LLMRequest) -> list[tuple[str, list[str]]]:
    """(id, methods) of the layer 5 block of the last user message."""
    user = req.messages[-1]["content"]
    block = user[user.rindex("# Requirements\n") :]
    nxt = block.find("\n\n#", 1)
    block = block if nxt < 0 else block[:nxt]
    return [(m[0], m[2].split(", ") if m[2] else []) for m in _ROW.findall(block)]


def tail(req: LLMRequest) -> str:
    """Everything after the layer 5 requirement block."""
    user = req.messages[-1]["content"]
    block_start = user.rindex("# Requirements\n")
    nxt = user.find("\n\n#", block_start + 1)
    return "" if nxt < 0 else user[nxt:]


def listed_ids(text: str, label: str) -> list[str]:
    m = re.search(rf"^{label}:? (.+)$", text, re.M)
    return [i.strip(" .") for i in m.group(1).split(",")] if m else []


def case_json(rid: str, *, cid: str | None = None, covers: Sequence[str] | None = None) -> dict:
    return {
        "id": cid or f"X-{rid}",
        "title": f"{rid} davranışı",
        "covers": list(covers or [rid]),
        "type": "Normal",
        "priority": "Orta",
        "preconditions": "",
        "test_inputs": "",
        "assumptions": "",
        "steps": [{"no": 1, "action": f"{rid} işlemini yap", "expected": "Sonuç görülür"}],
    }


def smart_reply(req: LLMRequest) -> Any:
    name = req.schema.__name__
    if name == "TestCaseSet":
        rows = requirement_rows(req)
        repair = re.search(r"The requirements (.+) are not covered yet", tail(req))
        if repair:
            ids = [i.strip() for i in repair.group(1).split(",")]
        else:
            ids = [rid for rid, methods in rows if SETTINGS.test_method in methods]
        return {"test_cases": [case_json(i) for i in ids]}
    if name == "TestCaseDelta":
        return {"add": [case_json(i) for i in listed_ids(tail(req), "Added")], "update": []}
    if name == "MergeDecision":
        return {"drop": []}
    if name == "ClusterLabel":
        return {
            "name": "Giriş ve parola kuralları",
            "rationale": "Hepsi kimlik doğrulama ile ilgili.",
        }
    if name == "MethodBatch":
        return {
            "decisions": [
                {"requirement_id": rid, "methods": ["Test"], "rationale": "Gözlenebilir."}
                for rid, _ in requirement_rows(req)
            ]
        }
    raise AssertionError(f"no scripted reply for schema {name}")


@dataclass
class ScriptedComplete:
    handler: Callable[[LLMRequest], Any] = smart_reply
    requests: list[LLMRequest] = field(default_factory=list)

    async def __call__(self, request: LLMRequest) -> LLMReply:
        self.requests.append(request)
        out = self.handler(request)
        content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        try:
            parsed = request.schema.model_validate_json(content)
            error = None
        except ValidationError as exc:
            parsed, error = None, str(exc)
        return LLMReply(content=content, parsed=parsed, schema_error=error)

    def of(self, kind: NodeKind) -> list[LLMRequest]:
        return [r for r in self.requests if r.stage == kind]


def sequence(*handlers: Callable[[LLMRequest], Any]) -> Callable[[LLMRequest], Any]:
    """Use the handlers in order for successive calls, then `smart_reply`."""
    queue = list(handlers)

    def handle(req: LLMRequest) -> Any:
        return (queue.pop(0) if queue else smart_reply)(req)

    return handle


# Driver -----------------------------------------------------------------------------------------


@dataclass
class Drive:
    state: ProjectState
    outcomes: list[ProduceOutcome]

    def stats(self, ref: NodeRef) -> Mapping[str, Any]:
        for o in self.outcomes:
            if ref in o.stats:
                return o.stats[ref]
        raise KeyError(ref)

    def failed(self) -> set[NodeRef]:
        return {r for o in self.outcomes for r in o.failed}


async def drive(
    state: ProjectState,
    complete: ScriptedComplete,
    *,
    real: Iterable[NodeKind] = TEST_KINDS,
    settings: StageSettings = SETTINGS,
    hints: Mapping[NodeRef, Hint] | None = None,
    sources: Mapping[NodeRef, Sequence[TestCaseContent]] | None = None,
    embed: Embed | None = None,
    retrieve: Retrieve | None = None,
    passages: PassageSource | None = None,
    select_examples: SelectExamples | None = None,
    example_texts: ExampleSource | None = None,
    max_rounds: int = 20,
) -> Drive:
    real = frozenset(real)
    hints = dict(hints or {})
    outcomes: list[ProduceOutcome] = []
    for _ in range(max_rounds):
        ready = analyze(state).ready
        if not ready:
            return Drive(state, outcomes)
        results = [(r, fake_result(state, r, {})) for r in ready if r.kind not in real]
        jobs = []
        by_kind: dict[NodeKind, list[NodeRef]] = {}
        for r in ready:
            if r.kind in real:
                by_kind.setdefault(r.kind, []).append(r)
        for kind, refs in by_kind.items():
            spec = stages.get(kind)
            assert spec.produce is not None, kind
            groups = [tuple(refs)] if spec.batched else [(r,) for r in refs]
            for g in groups:
                ctx = ProduceContext(
                    state=state,
                    refs=g,
                    settings=settings,
                    hint=hints.get(g[0]) if len(g) == 1 else None,
                    sources=sources or {},
                    embed=embed,
                    retrieve=retrieve,
                    passages=passages,
                    select_examples=select_examples,
                    example_texts=example_texts,
                )
                jobs.append(spec.produce(ctx, complete))
        outs = list(await asyncio.gather(*jobs))
        outcomes += outs
        results += [x for o in outs for x in o.results]
        out = settle_many(state, results)
        assert not out.rejected, f"rejected: {sorted(map(str, out.rejected))}"
        state = out.state
        for o in outs:
            for r in o.failed:
                state = mark_failed(state, r)
    raise AssertionError("drive did not converge")


def cases_of(
    state: ProjectState, cluster: str, *, pinned: bool | None = None
) -> list[TestCaseContent]:
    """The set's cases in `TestSetContent.case_keys` order (pinned first, then generated), not
    key order (`TC-10` sorts before `TC-2`)."""
    from core.nodes import TestSetContent, ref

    content = state.node(ref(NodeKind.TEST_SET, cluster)).content
    keys = content.case_keys if isinstance(content, TestSetContent) else ()
    out = []
    for k in keys:
        node = state.node(ref(NodeKind.TEST_CASE, k))
        if pinned is None or node.pinned == pinned:
            assert isinstance(node.content, TestCaseContent)
            out.append(node.content)
    return out


def covered(state: ProjectState, cluster: str) -> set[str]:
    return {i for c in cases_of(state, cluster) for i in c.covers}
