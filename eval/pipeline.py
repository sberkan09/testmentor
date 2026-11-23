"""Measurement pipeline over the real stages (paket 3; paket 1 had a bare pipeline here). The
runner only depends on `Pipeline.run`.

Per project: a `core` project state is built from the golden project and produced by the wave
driver (`eval.stage_driver`) with the real producers; every model call goes through a recording
`Complete` (call stats, raw outputs, concurrency limit).

- `generation_inputs: reference`: clusters are the golden reference clusters; the method stage
  still runs once for the method accuracy, then the reference methods are written as user edits
  (`MethodEdited`: pinned and fresh), so test generation is measured apart from classification.
- `generation_inputs: predicted`: clusters from the first cut over the embeddings
  (`initial_membership`), methods from the model (end to end).
- `passages: none | gold | index`: no knowledge base; the support passages of golden set v1 for
  the cluster's requirements (oracle retrieval, D9 pilot; same text and order as in paket 1); or
  (paket 7) real hybrid search over the project's writer-visible corpus documents, chunked and
  embedded per the `kb:` settings and loaded into an `InMemoryIndex` (`eval/kb_corpus.py`). The
  corpus cache must exist: a missing one aborts the run before any model call.
- `card: full | methods_only`: the card as before, or without its text (D9 arm "card off": the
  eval card is only the project name and domain, plus the method list the method schema needs).

Cluster names (`cluster_label`) are not produced: nothing measured depends on them.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import core.stages  # noqa: F401  (registers the stages)
from core.events import MethodEdited
from core.graph import ProjectState, new_project
from core.hashing import input_hash
from core.invalidation import apply
from core.kb.chunking import chunk_document
from core.llm import Complete, LLMReply, LLMRequest
from core.metrics import CallStat, ProjectOutcome
from core.nodes import (
    MethodContent,
    MethodDef,
    NodeKind,
    NodeRef,
    RequirementContent,
    TestCaseContent,
    TestSetContent,
    ref,
)
from core.prompts import card_text
from core.schemas import Requirement
from core.stages import method as method_stage
from core.stages.base import ProduceContext
from core.stages.clustering import cut, initial_membership
from eval.example_pool import build_reference_pool, leak_check
from eval.golden import Golden, GoldenProject
from eval.kb_corpus import ChunkVectorCache, load_corpus
from eval.stage_driver import drive
from services.kb_examples import ExamplePool
from services.kb_index import InMemoryIndex
from services.kb_rerank import make_reranker
from services.kb_retrieve import build_retrieval, make_example_source, make_select_examples
from services.llm_client import LLMClient, LLMError
from services.settings import stage_configs, stage_settings_from
from services.stage_llm import ClientComplete

EmbedFn = Callable[[Sequence[str]], Awaitable[list[list[float]]]]
SKIP = frozenset({NodeKind.CLUSTER_LABEL})


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
    raw_outputs: list[str] = field(default_factory=list)
    """Schema-valid test set outputs as the model wrote them (before covers filtering): the
    no-test violations are counted on these (paket 3)."""
    extra: dict[str, Any] = field(default_factory=dict)
    """Scenario metrics (D8, `eval.scenarios`)."""


def call_kind(request: LLMRequest) -> str:
    if request.stage == NodeKind.METHOD:
        return "classification"
    if request.stage == NodeKind.CLUSTER_LABEL:
        return "label"
    for mode in ("repair", "incremental", "merge"):
        if f"/{mode}" in request.unit:
            return mode
    return "generation"


class Recorder:
    """`Complete` that limits concurrency and records every call (stats, outputs)."""

    def __init__(
        self,
        inner: Complete,
        sem: asyncio.Semaphore,
        model: str,
        configs: dict[NodeKind, Any],
    ) -> None:
        self.inner, self.sem, self.model, self.configs = inner, sem, model, configs
        self.records: list[dict[str, Any]] = []
        self.calls: list[CallStat] = []
        self.raw_outputs: list[str] = []

    def for_project(self, project: str, phase: str = "") -> Complete:
        async def complete(request: LLMRequest) -> LLMReply:
            return await self._call(project, request, phase)

        return complete

    async def _call(self, project: str, request: LLMRequest, phase: str = "") -> LLMReply:
        kind = call_kind(request)
        params = request.params.model_dump(mode="json")
        h = input_hash(
            inputs=list(request.messages),
            prompt_version=self.configs[request.stage].prompt_version,
            model=self.model,
            params=params,
        )
        reply: LLMReply | None = None
        error: str | None = None
        async with self.sem:
            started = time.perf_counter()
            try:
                reply = await self.inner(request)
            except LLMError as exc:
                error = str(exc)[:2000]
            elapsed = time.perf_counter() - started
        u = reply.usage if reply else None
        valid = reply is not None and reply.parsed is not None
        self.calls.append(
            CallStat(
                kind=kind,
                schema_valid=valid,
                error=error is not None,
                prompt_tokens=(u.prompt_tokens or 0) if u else 0,
                completion_tokens=(u.completion_tokens or 0) if u else 0,
                cached_tokens=u.cached_tokens if u else None,
                ttft_s=u.ttft_s if u else None,
                total_s=(u.total_s if u and u.total_s is not None else elapsed),
            )
        )
        self.records.append(
            {
                "type": "call",
                "kind": kind,
                "stage": request.stage.value,
                "project": project,
                "phase": phase,
                "unit": request.unit,
                "input_hash": h,
                "params": params,
                "error": error,
                "content": reply.content if reply else None,
                "finish_reason": reply.finish_reason if reply else None,
                "schema_error": reply.schema_error if reply else None,
                "metrics": u.model_dump() if u else None,
            }
        )
        if valid and request.stage == NodeKind.TEST_SET:
            self.raw_outputs.append(reply.content)  # type: ignore[union-attr]
        if error is not None:
            raise LLMError(error)
        assert reply is not None
        return reply


class Pipeline:
    def __init__(
        self,
        llm: LLMClient | None,
        embeddings: EmbeddingCache,
        cfg: dict[str, Any],
        examples: dict[str, Any],
        *,
        complete: Complete | None = None,
        kb_vectors: ChunkVectorCache | None = None,
        example_pool: ExamplePool | None = None,
    ) -> None:
        self.embeddings, self.cfg = embeddings, cfg
        # reference: generation gets the golden clusters and methods, so its quality is measured
        # apart from clustering (D6) and classification; predicted: end to end.
        self.generation_inputs = cfg.get("generation_inputs", "reference")
        self.passage_mode = cfg.get("passages", "none")
        if self.passage_mode not in ("none", "gold", "index"):
            raise ValueError(f"unknown passages mode {self.passage_mode!r}")
        self.card_mode = cfg.get("card", "full")
        if self.card_mode not in ("full", "methods_only"):
            raise ValueError(f"unknown card mode {self.card_mode!r}")
        self.settings = stage_settings_from(cfg, examples)
        self.example_pool = example_pool
        # D10 (paket 11): `example_pool: reference` builds a per-project pool from the golden
        # reference checks with the leak rule of eval.example_pool
        self.example_pool_mode = cfg.get("example_pool")
        if self.example_pool_mode not in (None, "reference"):
            raise ValueError(f"unknown example_pool {self.example_pool_mode!r}")
        if self.example_pool_mode == "reference" and self.example_pool is None:
            self.example_pool = ExamplePool()
        if self.settings.kb.examples and self.example_pool is None:
            raise ValueError("kb.examples > 0 needs an example pool (example_pool: reference)")
        self.index = InMemoryIndex(self.settings.kb)
        self.kb_vectors = kb_vectors or ChunkVectorCache(
            None, embeddings.model_version, embeddings.embed
        )
        self.reranker = make_reranker(self.settings.kb.reranker, self.settings.kb.rerank_max_tokens)
        self.model = llm.settings.served_model_name if llm is not None else "model"
        self.configs = stage_configs(
            self.settings, model=self.model, embedding_model_version=embeddings.model_version
        )
        self.card_methods = tuple(
            MethodDef(name=m["name"], criterion=m["criterion"]) for m in cfg["methods"]
        )
        if complete is None:
            if llm is None:
                raise ValueError("either llm or complete is needed")
            complete = ClientComplete(llm)
        self.recorder = Recorder(
            complete, asyncio.Semaphore(int(cfg["concurrency"])), self.model, self.configs
        )
        self.records = self.recorder.records
        self.calls = self.recorder.calls

    def prompt_versions(self) -> dict[str, str]:
        return {k.value: c.prompt_version for k, c in self.configs.items()}

    # Project state ------------------------------------------------------------------------

    def project_state(self, p: GoldenProject, clusters: dict[str, tuple[str, ...]]) -> ProjectState:
        return new_project(
            p.key,
            requirements=[
                RequirementContent(id=r.id, text=r.text, language=r.language)
                for r in p.requirements
            ],
            clusters=clusters,
            card="" if self.card_mode == "methods_only" else card_text(p.key, p.name, p.domain),
            index_version="v1",
            stage_configs=self.configs,
            methods=self.card_methods,
        )

    def gold_passages(self, p: GoldenProject):
        """Retrieve and passage source for `passages: gold`."""
        texts: dict[str, str] = {}

        async def retrieve(members: Sequence[RequirementContent]) -> list[str]:
            rows = gold_passages(p, [m.id for m in members])
            texts.update(rows)
            return [pid for pid, _ in rows]

        def source(ids: Sequence[str]) -> list[str]:
            return [texts[i] for i in ids]

        return retrieve, source

    async def load_kb(self, p: GoldenProject) -> int:
        """`passages: index`: chunk the project's corpus documents, embed the chunks (cached on
        disk) and add them to the index under the project's key. Returns the chunk count."""
        kb = self.settings.kb
        chunks = []
        for doc_id, text in load_corpus(p.key):
            chunks += chunk_document(
                doc_id,
                text,
                chunk_tokens=kb.chunk_tokens,
                overlap_tokens=kb.chunk_overlap_tokens,
                chars_per_token=kb.chars_per_token,
            )
        vectors = await self.kb_vectors.get(p.key, chunks)
        self.index.add(p.key, chunks, vectors)
        return len(chunks)

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await self.embeddings.get(texts)

    # Whole run ------------------------------------------------------------------------------

    async def run_project(self, p: GoldenProject) -> ProjectOutcome:
        ids = [r.id for r in p.requirements]
        vectors = await self.embeddings.get([r.text for r in p.requirements])
        predicted_cut = cut(ids, vectors, self.settings.clustering)
        complete = self.recorder.for_project(p.key)
        if self.generation_inputs == "reference":
            units = p.reference_clusters()
            if self.cfg.get("unit_packing"):
                units = pack_units(units, self.settings.max_unit_size)
            clusters = {f"c{i:03d}": tuple(c) for i, c in enumerate(units)}
        else:
            counter = itertools.count()
            clusters = initial_membership(
                ids, vectors, self.settings.clustering, lambda: f"c{next(counter):03d}"
            )
        state = self.project_state(p, clusters)
        predicted: dict[str, list[str]] = {}
        errors: dict[str, str] = {}
        if self.generation_inputs == "reference":
            state, predicted, errors = await self._reference_methods(p, state, complete)
        retrieve, passages = None, None
        if self.passage_mode == "gold":
            retrieve, passages = self.gold_passages(p)
        elif self.passage_mode == "index":
            retrieve, passages = build_retrieval(
                self.index, p.key, self._embed, self.settings.kb, self.reranker
            )
        select_examples = example_texts = None
        if self.example_pool is not None and self.example_pool_mode == "reference":
            self.example_pool.add(
                p.key,
                await build_reference_pool(
                    p.raw,
                    self._embed,
                    test_type=self.settings.test_types[0],
                    priority=self.settings.priorities[len(self.settings.priorities) // 2],
                ),
            )
        if self.example_pool is not None:
            select_examples = make_select_examples(
                self.example_pool, p.key, self._embed, self.settings.kb.examples
            )
            example_texts = make_example_source(self.example_pool, p.key)

        async def embed(texts: Sequence[str]) -> list[list[float]]:
            return await self.embeddings.get(texts)

        driven = await drive(
            state,
            complete,
            settings=self.settings,
            skip=SKIP,
            embed=embed,
            retrieve=retrieve,
            passages=passages,
            select_examples=select_examples,
            example_texts=example_texts,
        )
        state = driven.state
        errors |= {str(r): why for r, why in driven.errors.items()}
        example_keys = {
            c: list(getattr(state.node(ref(NodeKind.RETRIEVAL, c)).content, "example_keys", ()))
            for c in state.keys_of(NodeKind.CLUSTER)
        }
        examples = (
            leak_check(p.raw, clusters, example_keys)
            if self.example_pool_mode == "reference"
            else {}
        )
        if self.generation_inputs != "reference":
            for rid in ids:
                content = state.node(ref(NodeKind.METHOD, rid)).content
                if isinstance(content, MethodContent):
                    predicted[rid] = list(content.methods)
        stats = driven.stats()
        tests: list[dict[str, Any]] = []
        covered: set[str] = set()
        for c in state.keys_of(NodeKind.CLUSTER):
            tests += case_dicts(state, c)
            covered |= set(
                stats.get(ref(NodeKind.TEST_SET, c), {}).get("covered_before_repair", [])
            )
        self.records.append(
            {
                "type": "project",
                "project": p.key,
                "clusters": [list(c) for c in predicted_cut],
                "methods": predicted,
                "generation_inputs": self.generation_inputs,
                "generation_clusters": [list(m) for m in clusters.values()],
                "test_cases": tests,
                "retrieval": {
                    c: list(
                        getattr(state.node(ref(NodeKind.RETRIEVAL, c)).content, "passage_ids", ())
                    )
                    for c in state.keys_of(NodeKind.CLUSTER)
                },
                "examples": examples,
                "covered_before_repair": sorted(covered),
                "stage_stats": {
                    str(r): dict(s)
                    for r, s in sorted(stats.items(), key=lambda x: x[0].sort_key())
                    if r.kind == NodeKind.TEST_SET
                },
                "errors": errors,
            }
        )
        return ProjectOutcome(p.key, [list(c) for c in predicted_cut], predicted, tests, covered)

    async def _reference_methods(
        self,
        p: GoldenProject,
        state: ProjectState,
        complete: Complete,
        *,
        predict: bool = True,
    ) -> tuple[ProjectState, dict[str, list[str]], dict[str, str]]:
        """Run the method stage once for its accuracy (`predict`), then pin the reference
        methods."""
        refs = tuple(ref(NodeKind.METHOD, r.id) for r in p.requirements)
        errors: dict[str, str] = {}
        predicted: dict[str, list[str]] = {}
        try:
            if not predict:
                raise _NoPrediction
            out = await method_stage.produce(
                ProduceContext(state=state, refs=refs, settings=self.settings), complete
            )
            predicted = {
                r.key: list(res.content.methods)  # type: ignore[union-attr]
                for r, res in out.results
            }
            errors = {str(r): why for r, why in out.failed.items()}
        except _NoPrediction:
            pass
        except Exception as exc:  # noqa: BLE001 - measured as missing predictions
            predicted, errors = {}, {str(r): f"{type(exc).__name__}: {exc}" for r in refs}
        for r in p.raw["requirements"]:
            state, _ = apply(
                state,
                MethodEdited(
                    requirement=r["id"],
                    methods=tuple(sorted(r["verification_methods"])),
                    rationale="altın set referansı",
                ),
            )
        return state, predicted, errors

    async def run(self, golden: Golden) -> PipelineResult:
        started = time.perf_counter()
        if self.passage_mode == "index":
            for p in golden.projects:  # fail on a missing corpus before the first model call
                n = await self.load_kb(p)
                self.records.append({"type": "kb", "project": p.key, "chunks": n})
        outcomes = await asyncio.gather(*(self.run_project(p) for p in golden.projects))
        return PipelineResult(
            list(outcomes),
            self.records,
            self.calls,
            time.perf_counter() - started,
            raw_outputs=self.recorder.raw_outputs,
        )


def gold_passages(p: GoldenProject, cluster: Sequence[str]) -> list[tuple[str, str]]:
    """(passage id, prompt text) of the golden v1 support passages of the cluster's requirements,
    de-duplicated by normalised text, in document, section, text order (paket 1 text and order;
    prompt prefix rules)."""
    by_id = {r["id"]: r for r in p.raw["requirements"]}
    seen: dict[str, tuple] = {}
    for rid in sorted(cluster):
        for ps in by_id[rid].get("support_passages", []):
            key = " ".join(ps["text"].split())
            seen.setdefault(key, (ps["doc"], ps["section"], ps["text"]))
    return [
        (f"{d}§{sec}#{hashlib.sha256(t.encode('utf-8')).hexdigest()[:12]}", f"[{d} §{sec}] {t}")
        for d, sec, t in sorted(seen.values())
    ]


class _NoPrediction(Exception):
    pass


def pack_units(clusters: Sequence[Sequence[str]], limit: int) -> list[list[str]]:
    """D7: reference clusters in reference order (neighbouring document sections) packed greedily
    into units of at most `limit` requirements; a cluster larger than `limit` stays alone (the
    producer splits it into balanced parts)."""
    out: list[list[str]] = []
    current: list[str] = []
    for c in clusters:
        if len(c) > limit:
            if current:
                out.append(current)
                current = []
            out.append(sorted(c))
        elif len(current) + len(c) > limit:
            out.append(current)
            current = sorted(c)
        else:
            current = sorted([*current, *c])
    if current:
        out.append(current)
    return out


def case_dicts(state: ProjectState, cluster: str) -> list[dict[str, Any]]:
    """The set's cases in `case_keys` order as plain dicts; `id` is the node key (unique in the
    project), `case_id` the id inside the set."""
    content = state.node(ref(NodeKind.TEST_SET, cluster)).content
    keys = content.case_keys if isinstance(content, TestSetContent) else ()
    out = []
    for k in keys:
        node = state.node(NodeRef(kind=NodeKind.TEST_CASE, key=k))
        if isinstance(node.content, TestCaseContent):
            d = node.content.model_dump(mode="json", exclude={"kind"})
            out.append(d | {"id": k, "case_id": d["id"], "cluster": cluster, "pinned": node.pinned})
    return out


def requirement_texts(golden: Golden) -> list[Requirement]:
    return [r for p in golden.projects for r in p.requirements]
