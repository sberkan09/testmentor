"""Project card draft (paket 7): schema, prompt layout, budget, fake model."""

from __future__ import annotations

import pytest

from core.kb.chunking import chunk_document
from core.kb.settings import KbSettings
from core.nodes import MethodDef, NodeKind, ProjectCardContent
from core.prompts import CARD_DRAFT_VERSION, SYSTEM
from core.stages.calls import CallFailed
from services.card_draft import draft_card, excerpts
from services.fake_llm import FakeComplete
from tests.stages.helpers import CARD_METHODS, ScriptedComplete

KB = KbSettings(card_tokens=50, chars_per_token=4)


async def test_draft_with_the_fake_model():
    complete = FakeComplete()
    docs = [("B", "İkinci belge metni."), ("A", "Birinci belge metni.")]
    draft = await draft_card(complete, docs, CARD_METHODS, KB)
    assert isinstance(draft.content(), ProjectCardContent)
    assert draft.text and draft.methods and draft.template_version == CARD_DRAFT_VERSION
    (req,) = complete.requests
    assert req.stage == NodeKind.PROJECT_CARD and req.schema.__name__ == "CardDraft"
    assert req.messages[0] == {"role": "system", "content": SYSTEM}  # the shared system prompt
    user = req.messages[1]["content"]
    assert user.index("## A") < user.index("## B")  # id order, deterministic
    assert all(f"- {m.name}: {m.criterion}" in user for m in CARD_METHODS)
    assert "at most 50 tokens" in user
    assert req.schema.model_json_schema()["properties"]["text"]["maxLength"] == 200


async def test_text_over_the_token_limit_is_a_schema_error_with_one_retry():
    def handler(req):
        return {"text": "x" * 201, "methods": [{"name": "Test", "criterion": "c"}]}

    complete = ScriptedComplete(handler)
    with pytest.raises(CallFailed):
        await draft_card(complete, [("A", "metin")], CARD_METHODS, KB)
    assert (
        len(complete.requests) == 2
        and "# Correction" in complete.requests[1].messages[-1]["content"]
    )


async def test_duplicate_method_names_are_merged():
    def handler(req):
        m = [{"name": "Test", "criterion": "bir"}, {"name": "Test", "criterion": "iki"}]
        return {"text": "Kart", "methods": m}

    draft = await draft_card(ScriptedComplete(handler), [("A", "m")], CARD_METHODS, KB)
    assert draft.methods == (MethodDef(name="Test", criterion="bir"),)


def test_excerpts_take_the_start_of_every_document_within_the_budget():
    def chunks(doc, n):
        text = "\n\n".join(f"{doc} bölüm {i} " + "söz " * 20 for i in range(n))
        return chunk_document(doc, text, chunk_tokens=30, overlap_tokens=0)

    by_doc = {"B": chunks("B", 6), "A": chunks("A", 6)}
    out = excerpts(by_doc, budget_tokens=100, chars_per_token=4)  # 400 characters
    assert [d for d, _ in out] == ["A", "B"]
    assert sum(len(t) for _, t in out) <= 400 + 8
    assert out[0][1].startswith("A bölüm 0") and out[1][1].startswith("B bölüm 0")
    assert excerpts({}, 100) == []
    assert excerpts(by_doc, 10_000) == excerpts(by_doc, 10_000)  # deterministic
