"""The simplest pipeline for measurement (paket 1). Paket 3 replaces it with the real stages; the
runner only depends on `Pipeline.run`.

Order per project: embed and cluster → classify verification methods in batches → generate test
cases per cluster in parallel (tests only for requirements whose method includes Test) → one
repair call per cluster for Test requirements left uncovered.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.clustering import build_tree
from core.hashing import input_hash
from core.metrics import CallStat, ProjectOutcome
from core.prompts import (
    TEMPLATE_VERSION,
    Method,
    ProjectCard,
    classification_messages,
    generation_messages,
)
from core.schemas import Requirement, case_set_model, method_batch_model, plain
from eval.golden import Golden, GoldenProject
from services.llm_client import ChatResult, LLMClient, LLMError, StreamDelta

EmbedFn = Callable[[Sequence[str]], Awaitable[list[list[float]]]]


class EmbeddingCache:
    """Embeddings keyed by model version and text, stored on disk so that runs on an engine
    without an embedding server (SGLang profile) cluster identically."""

    def __init__(self, path: Path, model_version: str, embed: EmbedFn | None) -> None:
        self.path, self.model_version, self.embed = path, model_version, embed
        self.data: dict[str, list[float]] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model_version}\n{text}".encode()).hexdigest()

    async def get(self, texts: Sequence[str]) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if self._key(t) not in self.data]
        if missing:
            if self.embed is None:
                raise RuntimeError(f"{len(missing)} embeddings missing and no embedding service")
            for t, v in zip(missing, await self.embed(missing), strict=True):
                self.data[self._key(t)] = [round(x, 6) for x in v]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, sort_keys=True), encoding="utf-8")
        return [self.data[self._key(t)] for t in texts]


@dataclass
class PipelineResult:
    outcomes: list[ProjectOutcome]
    records: list[dict[str, Any]]
    calls: list[CallStat]
    wall_s: float
    stage_wall_s: dict[str, float] = field(default_factory=dict)


class Pipeline:
    def __init__(
        self,
        llm: LLMClient,
        embeddings: EmbeddingCache,
        cfg: dict[str, Any],
        examples: dict[str, Any],
        clusters: str = "predicted",
    ) -> None:
        self.llm, self.embeddings, self.cfg, self.examples = llm, embeddings, cfg, examples
        self.clusters_mode = clusters
        self.methods = tuple(m["name"] for m in cfg["methods"])
        self.case_model = case_set_model(tuple(cfg["test_types"]), tuple(cfg["priorities"]))
        self.method_model = method_batch_model(self.methods)
        self.sem = asyncio.Semaphore(int(cfg["concurrency"]))
        self.records: list[dict[str, Any]] = []
        self.calls: list[CallStat] = []

    def card(self, p: GoldenProject) -> ProjectCard:
        return ProjectCard(
            p.key,
            p.name,
            p.domain,
            tuple(Method(m["name"], m["criterion"]) for m in self.cfg["methods"]),
        )

    # Model calls ----------------------------------------------------------------------------

    async def _call(
        self,
        kind: str,
        project: str,
        unit: str,
        messages: list[dict[str, str]],
        schema: type,
        stage: dict[str, Any],
        first_token: asyncio.Event | None = None,
        wait_for: asyncio.Event | None = None,
    ) -> ChatResult | None:
        params = {k: stage[k] for k in ("temperature", "thinking", "max_tokens")}
        h = input_hash(
            inputs=messages,
            prompt_version=f"{self.cfg['prompt_version']}/{TEMPLATE_VERSION}",
            model=self.llm.settings.served_model_name,
            params=params,
        )
        if wait_for is not None:
            await wait_for.wait()
        result: ChatResult | None = None
        error: str | None = None
        async with self.sem:
            started = time.perf_counter()
            try:
                async for item in self.llm.chat_stream(
                    messages,
                    schema=schema,
                    max_tokens=stage["max_tokens"],
                    temperature=stage["temperature"],
                    thinking=stage["thinking"],
                ):
                    if isinstance(item, StreamDelta):
                        if first_token is not None and not first_token.is_set():
                            first_token.set()
                    else:
                        result = item
            except LLMError as exc:
                error = str(exc)[:2000]
            finally:
                if first_token is not None:
                    first_token.set()
        m = result.metrics if result else None
        self.calls.append(
            CallStat(
                kind=kind,
                schema_valid=bool(result and result.schema_error is None),
                error=error is not None,
                prompt_tokens=(m.prompt_tokens or 0) if m else 0,
                completion_tokens=(m.completion_tokens or 0) if m else 0,
                cached_tokens=m.cached_tokens if m else None,
                ttft_s=m.ttft_s if m else None,
                total_s=m.total_s if m else time.perf_counter() - started,
            )
        )
        self.records.append(
            {
                "type": "call",
                "kind": kind,
                "project": project,
                "unit": unit,
                "input_hash": h,
                "params": params,
                "error": error,
                "content": result.content if result else None,
                "reasoning_chars": len(result.reasoning or "") if result else 0,
                "finish_reason": result.finish_reason if result else None,
                "schema_error": result.schema_error if result else None,
                "metrics": m.model_dump() if m else None,
            }
        )
        return result

    # Stages ---------------------------------------------------------------------------------

    async def cluster(self, p: GoldenProject) -> list[list[str]]:
        if self.clusters_mode == "reference":
            return p.reference_clusters()
        c = self.cfg["clustering"]
        vectors = await self.embeddings.get([r.text for r in p.requirements])
        tree = build_tree([r.id for r in p.requirements], vectors, method=c["linkage"])
        return tree.cut(float(c["distance_threshold"]), int(c["max_cluster_size"]))

    async def classify(self, p: GoldenProject) -> dict[str, list[str]]:
        stage = self.cfg["classification"]
        schema = self.method_model.model_json_schema()
        size = int(stage["batch_size"])
        reqs = list(p.requirements)
        batches = [reqs[i : i + size] for i in range(0, len(reqs), size)]
        results = await asyncio.gather(
            *(
                self._call(
                    "classification",
                    p.key,
                    f"{p.key}/methods/{i}",
                    classification_messages(self.card(p), batch, schema=schema),
                    self.method_model,
                    stage,
                )
                for i, batch in enumerate(batches)
            )
        )
        decided: dict[str, list[str]] = {}
        for res in results:
            if res and res.parsed is not None:
                for d in plain(res.parsed)["decisions"]:
                    if d["requirement_id"] in {r.id for r in reqs}:
                        decided[d["requirement_id"]] = sorted(set(d["methods"]))
        return decided

    async def generate(
        self,
        p: GoldenProject,
        clusters: list[list[str]],
        methods: dict[str, list[str]],
    ) -> tuple[list[dict[str, Any]], set[str]]:
        stage = self.cfg["generation"]
        test_method = self.cfg["test_method"]
        by_id = {r.id: r for r in p.requirements}
        schema = self.case_model.model_json_schema()
        # Unclassified requirements default to Test so they are not silently skipped.
        eff = {rid: methods.get(rid) or [test_method] for rid in by_id}
        warm = asyncio.Event() if self.cfg.get("prefix_warmup") else None

        def msgs(cluster: list[str], only: Sequence[str] = ()) -> list[dict[str, str]]:
            return generation_messages(
                self.card(p),
                [by_id[i] for i in cluster],
                {i: eff[i] for i in cluster},
                schema=schema,
                examples=self.examples,
                test_method=test_method,
                types=self.cfg["test_types"],
                priorities=self.cfg["priorities"],
                only_ids=only,
            )

        async def one(idx: int, cluster: list[str]) -> tuple[list[dict[str, Any]], set[str]]:
            need = {i for i in cluster if test_method in eff[i]}
            if not need:
                return [], set()
            first = warm if (warm is not None and idx == 0) else None
            wait = warm if (warm is not None and idx > 0) else None
            unit = f"{p.key}/c{idx}"
            res = await self._call(
                "generation",
                p.key,
                unit,
                msgs(cluster),
                self.case_model,
                stage,
                first_token=first,
                wait_for=wait,
            )
            tests = self._accept(res, cluster, unit)
            covered_first = {i for t in tests for i in t["covers"]} & need
            missing = sorted(need - covered_first)
            if missing and stage.get("repair", True):
                rep = await self._call(
                    "repair",
                    p.key,
                    f"{unit}/repair",
                    msgs(cluster, missing),
                    self.case_model,
                    stage,
                )
                tests += self._accept(rep, cluster, f"{unit}/r", start=len(tests))
            return tests, covered_first

        order = [i for i, c in enumerate(clusters) if any(test_method in eff[r] for r in c)]
        if warm is not None and order and order[0] != 0:
            # The warm-up leader is the first cluster that actually needs tests.
            clusters = [clusters[order[0]]] + [c for i, c in enumerate(clusters) if i != order[0]]
        if warm is not None and not order:
            warm.set()
        parts = await asyncio.gather(*(one(i, c) for i, c in enumerate(clusters)))
        tests = [t for part, _ in parts for t in part]
        covered = set().union(*(c for _, c in parts)) if parts else set()
        return tests, covered

    def _accept(
        self, res: ChatResult | None, cluster: list[str], unit: str, start: int = 0
    ) -> list[dict[str, Any]]:
        if res is None or res.parsed is None:
            return []
        out = []
        allowed = set(cluster)
        for n, tc in enumerate(plain(res.parsed)["test_cases"], start=start + 1):
            covers = [i for i in dict.fromkeys(tc["covers"]) if i in allowed]
            invalid = [i for i in tc["covers"] if i not in allowed]
            if not covers:
                self.records.append({"type": "dropped_test", "unit": unit, "covers": tc["covers"]})
                continue
            out.append(tc | {"id": f"{unit}-{n}", "covers": covers, "invalid_covers": invalid})
        return out

    # Whole run ------------------------------------------------------------------------------

    async def run_project(self, p: GoldenProject) -> ProjectOutcome:
        clusters, methods = await asyncio.gather(self.cluster(p), self.classify(p))
        tests, covered = await self.generate(p, clusters, methods)
        self.records.append(
            {
                "type": "project",
                "project": p.key,
                "clusters": clusters,
                "methods": methods,
                "test_cases": tests,
                "covered_before_repair": sorted(covered),
            }
        )
        return ProjectOutcome(p.key, clusters, methods, tests, covered)

    async def run(self, golden: Golden) -> PipelineResult:
        started = time.perf_counter()
        outcomes = await asyncio.gather(*(self.run_project(p) for p in golden.projects))
        return PipelineResult(
            list(outcomes), self.records, self.calls, time.perf_counter() - started
        )


def requirement_texts(golden: Golden) -> list[Requirement]:
    return [r for p in golden.projects for r in p.requirements]
