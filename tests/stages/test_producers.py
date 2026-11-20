"""Producers of the other stages: method (batched), cluster label, and the model-free ones."""

from __future__ import annotations

from core.invalidation import analyze
from core.nodes import (
    ClusteringContent,
    ClusterLabelContent,
    EmbeddingContent,
    MatrixRowContent,
    MethodContent,
    NodeKind,
    RetrievalContent,
    ref,
)
from core.prompts import SCHEMA_RETRY_INSTRUCTION, SYSTEM
from tests.stages.helpers import (
    CARD_METHODS,
    SETTINGS,
    ScriptedComplete,
    drive,
    many_reqs,
    project,
    requirement_rows,
    sequence,
    smart_reply,
)

LLM_KINDS = {NodeKind.METHOD, NodeKind.CLUSTER_LABEL}
FREE_KINDS = {NodeKind.EMBEDDING, NodeKind.CLUSTERING, NodeKind.RETRIEVAL, NodeKind.MATRIX_ROW}


async def fake_embed(texts):
    return [[float(len(t)), 1.0, 0.5] for t in texts]


async def no_retrieve(members):
    return []


# Method ---------------------------------------------------------------------------------------


async def test_methods_are_classified_in_batches_in_id_order():
    reqs = many_reqs(30)
    state = project(reqs, {"M": tuple(reqs)})
    complete = ScriptedComplete()
    out = await drive(state, complete, real={NodeKind.METHOD})
    calls = complete.of(NodeKind.METHOD)
    assert [[i for i, _ in requirement_rows(c)] for c in calls] == [
        sorted(reqs)[:25],
        sorted(reqs)[25:],
    ]
    assert {c.schema.__name__ for c in calls} == {"MethodBatch"}
    enum = calls[0].schema.model_json_schema()["$defs"]["Method"]["enum"]
    assert enum == [m.name for m in CARD_METHODS]  # values from the project card
    assert calls[0].params == SETTINGS.llm[NodeKind.METHOD]
    node = out.state.node(ref(NodeKind.METHOD, "Q001"))
    assert isinstance(node.content, MethodContent) and node.content.methods == ("Test",)


def drop_id(rid: str, times: int):
    left = [times]

    def handle(r):
        reply = smart_reply(r)
        if r.schema.__name__ == "MethodBatch" and left[0] > 0:
            left[0] -= 1
            reply["decisions"] = [
                {**d, "methods": ["Test", "İnceleme", "Test"]} if d["requirement_id"] == "R1" else d
                for d in reply["decisions"]
                if d["requirement_id"] != rid
            ] + [{"requirement_id": "R99", "methods": ["Test"], "rationale": "x"}]
        return reply

    return handle


async def test_missing_decision_is_retried_alone_then_settled():
    complete = ScriptedComplete(drop_id("R2", times=1))
    out = await drive(project(), complete, real={NodeKind.METHOD})
    calls = complete.of(NodeKind.METHOD)
    assert [[i for i, _ in requirement_rows(c)] for c in calls] == [
        ["R1", "R2", "R3", "R4", "R5", "R6"],
        ["R2"],
    ]
    assert out.state.node(ref(NodeKind.METHOD, "R1")).content.methods == ("Test", "İnceleme")
    assert not out.failed()


async def test_decision_missing_twice_fails_only_that_requirement():
    complete = ScriptedComplete(drop_id("R2", times=2))
    out = await drive(project(), complete, real={NodeKind.METHOD})
    assert out.failed() == {ref(NodeKind.METHOD, "R2")}
    assert out.state.node(ref(NodeKind.METHOD, "R3")).status.value == "fresh"


async def test_failed_missing_id_retry_keeps_the_decisions_already_in():
    def handle(r):
        rows = [i for i, _ in requirement_rows(r)]
        if r.schema.__name__ == "MethodBatch" and rows == ["R2"]:
            return '{"decisions": "x"}'  # the single retry fails the schema twice
        reply = smart_reply(r)
        if r.schema.__name__ == "MethodBatch":
            reply["decisions"] = [d for d in reply["decisions"] if d["requirement_id"] != "R2"]
        return reply

    complete = ScriptedComplete(handle)
    out = await drive(project(), complete, real={NodeKind.METHOD})
    assert out.failed() == {ref(NodeKind.METHOD, "R2")}
    assert len(complete.of(NodeKind.METHOD)) == 3  # batch, missing id, its schema retry
    assert out.state.node(ref(NodeKind.METHOD, "R1")).status.value == "fresh"


async def test_method_schema_error_retried_once():
    complete = ScriptedComplete(sequence(lambda r: '{"decisions": "x"}'))
    out = await drive(project(), complete, real={NodeKind.METHOD})
    assert SCHEMA_RETRY_INSTRUCTION in complete.of(NodeKind.METHOD)[1].messages[1]["content"]
    assert not out.failed()


# Cluster label --------------------------------------------------------------------------------


async def test_one_label_call_per_cluster_with_shared_prefix():
    complete = ScriptedComplete()
    out = await drive(project(), complete, real={NodeKind.CLUSTER_LABEL})
    calls = complete.of(NodeKind.CLUSTER_LABEL)
    assert len(calls) == 3
    assert all(c.messages[0] == {"role": "system", "content": SYSTEM} for c in calls)
    assert {c.schema.__name__ for c in calls} == {"ClusterLabel"}
    node = out.state.node(ref(NodeKind.CLUSTER_LABEL, "A"))
    assert isinstance(node.content, ClusterLabelContent)
    assert node.content.name == "Giriş ve parola kuralları"


# Model-free stages ----------------------------------------------------------------------------


async def test_model_free_stages_never_call_the_model():
    complete = ScriptedComplete()
    out = await drive(project(), complete, real=FREE_KINDS, embed=fake_embed, retrieve=no_retrieve)
    assert complete.requests == []
    s = out.state
    assert not analyze(s).stale
    emb = s.node(ref(NodeKind.EMBEDDING, "R1")).content
    assert isinstance(emb, EmbeddingContent) and len(emb.vector) == 3
    tree = s.node(ref(NodeKind.CLUSTERING, "tree")).content
    assert isinstance(tree, ClusteringContent) and tree.ids == ("R1", "R2", "R3", "R4", "R5", "R6")
    assert len(tree.linkage) == 5
    ret = s.node(ref(NodeKind.RETRIEVAL, "A")).content
    assert isinstance(ret, RetrievalContent) and ret.passage_ids == ()
    row = s.node(ref(NodeKind.MATRIX_ROW, "R1")).content
    assert isinstance(row, MatrixRowContent)
    assert row.methods == ("Test",) and row.covered and row.test_case_keys == ("A:TC-R1",)


async def test_embedding_is_one_batched_call():
    seen: list[int] = []

    async def counting(texts):
        seen.append(len(texts))
        return await fake_embed(texts)

    await drive(project(), ScriptedComplete(), real={NodeKind.EMBEDDING}, embed=counting)
    assert seen == [6]


async def test_retrieval_keeps_rank_order_without_duplicates():
    async def retrieve(members):
        assert [m.id for m in members] in (["R1", "R2"], ["R3", "R4"], ["R5", "R6"])
        return ["p3", "p1", "p3", "p2"]

    out = await drive(project(), ScriptedComplete(), real={NodeKind.RETRIEVAL}, retrieve=retrieve)
    assert out.state.node(ref(NodeKind.RETRIEVAL, "A")).content.passage_ids == ("p3", "p1", "p2")
