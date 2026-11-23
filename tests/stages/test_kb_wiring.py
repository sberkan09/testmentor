"""Knowledge base wiring through the real producers (paket 7; fake model, no network)."""

from __future__ import annotations

from core.events import KbDocumentAdded
from core.graph import content_hash
from core.hashing import plain_hash
from core.invalidation import analyze, apply
from core.kb.settings import KbSettings
from core.nodes import NodeKind, NodeRef, RetrievalContent, ref
from core.stages.test_generation import basis_of, choose_mode
from services.settings import RETRIEVAL_VERSION, stage_configs, stage_settings_from
from tests.stages.helpers import (
    CFG,
    EXAMPLES,
    SETTINGS,
    ScriptedComplete,
    drive,
    project,
)

REAL = {NodeKind.RETRIEVAL, NodeKind.TEST_SET}


def prompts(complete: ScriptedComplete) -> list[str]:
    return [r.messages[-1]["content"] for r in complete.of(NodeKind.TEST_SET)]


def layer4(prompt: str) -> str:
    return prompt[prompt.index("# Retrieved passages") : prompt.index("# Requirements")]


async def passages_for(members):
    return ["p2", "p1"]


def source(ids):
    return [f"[DOC §S] metin {i}" for i in ids]


async def select_two(members):
    return ["TC-9@aaaaaaaa", "TC-3@bbbbbbbb"]


def example_texts(keys):
    return [f"Requirement: x\nTest case: örnek {k}" for k in keys]


async def test_passages_and_examples_reach_layer_4_in_rank_order():
    complete = ScriptedComplete()
    out = await drive(
        project(),
        complete,
        real=REAL,
        retrieve=passages_for,
        passages=source,
        select_examples=select_two,
        example_texts=example_texts,
    )
    assert not out.failed()
    ret = out.state.node(ref(NodeKind.RETRIEVAL, "A")).content
    assert isinstance(ret, RetrievalContent)
    assert ret.passage_ids == ("p2", "p1") and ret.example_keys == ("TC-9@aaaaaaaa", "TC-3@bbbbbbbb")
    for p in prompts(complete):
        text = layer4(p)
        assert text.index("metin p2") < text.index("metin p1") < text.index("# Project examples")
        assert text.index("TC-9@aaaaaaaa") < text.index("TC-3@bbbbbbbb")


async def test_without_examples_the_prompt_is_the_paket_3_prompt():
    complete = ScriptedComplete()
    out = await drive(
        project(), complete, real=REAL, retrieve=passages_for, passages=source
    )
    ret = out.state.node(ref(NodeKind.RETRIEVAL, "A")).content
    assert isinstance(ret, RetrievalContent) and ret.example_keys == ()
    assert all("# Project examples" not in p for p in prompts(complete))


def test_empty_example_keys_do_not_change_the_content_hash_or_the_stored_form():
    old = RetrievalContent(passage_ids=("a", "b"))
    assert old.model_dump(mode="json") == {"kind": "retrieval", "passage_ids": ["a", "b"]}
    assert content_hash(old) == plain_hash({"kind": "retrieval", "passage_ids": ["a", "b"]})
    new = RetrievalContent(passage_ids=("a", "b"), example_keys=("k@1",))
    assert content_hash(new) != content_hash(old)
    assert RetrievalContent.model_validate(new.model_dump(mode="json")) == new
    assert RetrievalContent.model_validate({"kind": "retrieval", "passage_ids": ["a"]}).example_keys == ()


async def test_example_keys_without_a_source_fail_the_node():
    out = await drive(project(), ScriptedComplete(), real=REAL, select_examples=select_two)
    assert {r.kind for r in out.failed()} == {NodeKind.TEST_SET}


async def test_changed_examples_make_the_set_stale_and_force_a_full_regeneration():
    complete = ScriptedComplete()
    s = (
        await drive(
            project(),
            complete,
            real=REAL,
            retrieve=passages_for,
            passages=source,
            select_examples=select_two,
            example_texts=example_texts,
        )
    ).state
    assert not analyze(s).stale
    assert choose_mode(s, "A", None, {}) == "incremental"  # nothing changed
    before = basis_of(s, "A")
    assert before.examples == ("TC-9@aaaaaaaa", "TC-3@bbbbbbbb")

    async def other(members):
        return ["TC-9@cccccccc"]  # the user edited that example

    s, _ = apply(s, KbDocumentAdded(document_id="d", index_version="e1"))
    n = len(complete.of(NodeKind.TEST_SET))
    s = (
        await drive(
            s,
            complete,
            real=REAL,
            retrieve=passages_for,
            passages=source,
            select_examples=other,
            example_texts=example_texts,
        )
    ).state
    assert len(complete.of(NodeKind.TEST_SET)) == n * 2  # every set regenerated
    assert basis_of(s, "A").examples == ("TC-9@cccccccc",)


async def test_pool_change_with_the_same_selection_is_cut_off_early():
    complete = ScriptedComplete()
    kwargs = dict(
        real=REAL,
        retrieve=passages_for,
        passages=source,
        select_examples=select_two,
        example_texts=example_texts,
    )
    s = (await drive(project(), complete, **kwargs)).state
    calls = len(complete.requests)
    s, inv = apply(s, KbDocumentAdded(document_id="d", index_version="v2.e5"))
    stale = {r for r in analyze(s).stale}
    assert NodeRef(kind=NodeKind.RETRIEVAL, key="A") in stale
    s = (await drive(s, complete, **kwargs)).state
    assert not analyze(s).stale
    assert len(complete.requests) == calls  # retrieval ran again, the test sets did not


def test_retrieval_stage_config_follows_the_kb_settings():
    def configs(**kb):
        cfg = {**CFG, "kb": {**CFG["kb"], **kb}}
        s = stage_settings_from(cfg, EXAMPLES)
        return stage_configs(s, model="m", embedding_model_version="e1")

    base = configs()[NodeKind.RETRIEVAL]
    assert base.prompt_version == RETRIEVAL_VERSION == "r2"
    assert base.params["top_k"] == 8 and base.params["examples"] == 0
    assert configs(top_k=4)[NodeKind.RETRIEVAL] != base
    assert configs(chunk_tokens=300)[NodeKind.RETRIEVAL] != base
    assert configs(reranker="some-model")[NodeKind.RETRIEVAL] != base
    # the card draft settings do not stale retrievals; the test set config is untouched by kb
    assert configs(card_tokens=900)[NodeKind.RETRIEVAL] == base
    assert configs(top_k=4)[NodeKind.TEST_SET] == configs()[NodeKind.TEST_SET]
    assert SETTINGS.kb == KbSettings()
