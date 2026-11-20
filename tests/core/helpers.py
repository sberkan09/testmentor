"""Shared layout for the core tests: project P, requirements R1–R6, clusters A{R1,R2},
B{R3,R4}, C{R5,R6}, produced to a fully fresh state by fake producers (no model call)."""

from __future__ import annotations

from collections.abc import Mapping

import core.stages  # noqa: F401  (registers the stages)
from core.graph import ProjectState, cache_key, expected_hash, new_project
from core.invalidation import analyze, settle
from core.nodes import (
    CLUSTERING_KEY,
    ClusteringContent,
    ClusterLabelContent,
    EmbeddingContent,
    MatrixRowContent,
    MethodContent,
    NodeKind,
    NodeRef,
    ProducedBy,
    RequirementContent,
    Result,
    RetrievalContent,
    StageConfig,
    TestCaseContent,
    TestSetContent,
    case_key,
    ref,
)
from core.schemas import Step
from core.store import InMemoryStore, OutputCache

PID = "P"
REQ_TEXTS = {
    "R1": "Sistem, kullanıcı girişini 3 başarısız denemeden sonra 15 dakika kilitlemelidir.",
    "R2": "Sistem, parola sıfırlama bağlantısını 30 dakika geçerli tutmalıdır.",
    "R3": "The system shall log every configuration change with user and timestamp.",
    "R4": "The system shall export the audit log as CSV.",
    "R5": "Sistem, rapor ekranını 2 saniye içinde açmalıdır.",
    "R6": "The system shall support 200 concurrent users.",
}
CLUSTERS = {"A": ("R1", "R2"), "B": ("R3", "R4"), "C": ("R5", "R6")}
PASSAGES = {"A": ("doc1#1",), "B": ("doc1#2",), "C": ("doc1#3",)}

CONFIGS = {
    NodeKind.EMBEDDING: StageConfig(prompt_version="e1", model="embedder"),
    NodeKind.CLUSTERING: StageConfig(
        prompt_version="c1", params={"linkage": "average", "distance_threshold": 0.35}
    ),
    NodeKind.METHOD: StageConfig(prompt_version="m1", model="llm", params={"temperature": 0.0}),
    NodeKind.CLUSTER_LABEL: StageConfig(prompt_version="l1", model="llm"),
    NodeKind.RETRIEVAL: StageConfig(prompt_version="r1", params={"top_k": 6}),
    NodeKind.TEST_SET: StageConfig(prompt_version="t1", model="llm", params={"temperature": 0.0}),
    NodeKind.MATRIX_ROW: StageConfig(prompt_version="x1"),
}


# Refs ------------------------------------------------------------------------------------------


def REQ(k: str) -> NodeRef:
    return ref(NodeKind.REQUIREMENT, k)


def EMB(k: str) -> NodeRef:
    return ref(NodeKind.EMBEDDING, k)


def METHOD(k: str) -> NodeRef:
    return ref(NodeKind.METHOD, k)


def MX(k: str) -> NodeRef:
    return ref(NodeKind.MATRIX_ROW, k)


def CL(k: str) -> NodeRef:
    return ref(NodeKind.CLUSTER, k)


def LABEL(k: str) -> NodeRef:
    return ref(NodeKind.CLUSTER_LABEL, k)


def RET(k: str) -> NodeRef:
    return ref(NodeKind.RETRIEVAL, k)


def SET(k: str) -> NodeRef:
    return ref(NodeKind.TEST_SET, k)


def TC(cluster: str, req: str) -> NodeRef:
    """The fake producer writes one case `TC-<req>` per member."""
    return ref(NodeKind.TEST_CASE, case_key(cluster, f"TC-{req}"))


TREE = ref(NodeKind.CLUSTERING, CLUSTERING_KEY)


def case(req: str, covers: tuple[str, ...] | None = None, title: str | None = None):
    return TestCaseContent(
        id=f"TC-{req}",
        title=title or f"{req} temel davranış",
        covers=covers or (req,),
        type="Normal",
        priority="Orta",
        steps=(Step(no=1, action=f"{req} işlemini yap", expected="Beklenen sonuç görülür"),),
    )


# Fake producers --------------------------------------------------------------------------------


def fake_result(
    state: ProjectState, r: NodeRef, passages: Mapping[str, tuple[str, ...]] = PASSAGES
) -> Result:
    cases: tuple[TestCaseContent, ...] = ()
    if r.kind == NodeKind.EMBEDDING:
        content = EmbeddingContent(vector=(float(len(state.requirement(r.key).text)), 1.0))
    elif r.kind == NodeKind.CLUSTERING:
        content = ClusteringContent(ids=tuple(state.keys_of(NodeKind.REQUIREMENT)))
    elif r.kind == NodeKind.METHOD:
        content = MethodContent(methods=("Test",), rationale="Davranış gözlenebilir.")
    elif r.kind == NodeKind.CLUSTER_LABEL:
        content = ClusterLabelContent(name="Öbek " + " ".join(state.members(r.key)))
    elif r.kind == NodeKind.RETRIEVAL:
        content = RetrievalContent(passage_ids=passages.get(r.key, ()))
    elif r.kind == NodeKind.TEST_SET:
        cases = tuple(case(m) for m in state.members(r.key))
        content = TestSetContent()
    elif r.kind == NodeKind.MATRIX_ROW:
        method = state.node(METHOD(r.key)).content
        keys = tuple(c.key for c in state.cases_covering(r.key))
        content = MatrixRowContent(
            requirement_id=r.key,
            methods=method.methods if isinstance(method, MethodContent) else (),
            test_case_keys=keys,
            covered=bool(keys),
        )
    else:
        raise AssertionError(f"no fake producer for {r}")
    cfg = state.stage_configs[r.kind]
    return Result(
        input_hash=expected_hash(state, r),
        cache_key=cache_key(state, r),
        content=content,
        produced_by=ProducedBy(
            mode="full", model=cfg.model, prompt_version=cfg.prompt_version, params=cfg.params
        ),
        cases=cases,
    )


def produce_all(
    state: ProjectState,
    cache: OutputCache | None = None,
    passages: Mapping[str, tuple[str, ...]] = PASSAGES,
    max_rounds: int = 20,
) -> ProjectState:
    """Produce every ready node until nothing is ready; writes each result to `cache`."""
    for _ in range(max_rounds):
        ready = analyze(state).ready
        if not ready:
            return state
        for r in ready:
            result = fake_result(state, r, passages)
            out = settle(state, r, result)
            assert out.accepted, r
            state = out.state
            if cache is not None:
                cache.put(state.project_id, result.cache_key, result)
    raise AssertionError("produce_all did not converge")


def fresh_project() -> tuple[ProjectState, InMemoryStore]:
    state = new_project(
        PID,
        requirements=[RequirementContent(id=k, text=v) for k, v in REQ_TEXTS.items()],
        clusters=CLUSTERS,
        card="Proje: Örnek portal. Doğrulama yöntemleri: Test, Analiz, İnceleme, Gösterim.",
        index_version="v1",
        stage_configs=CONFIGS,
    )
    cache = InMemoryStore()
    return produce_all(state, cache), cache


def all_cases() -> set[NodeRef]:
    return {TC(c, r) for c, members in CLUSTERS.items() for r in members}
