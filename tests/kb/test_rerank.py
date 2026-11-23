"""Reranker behind a scorer interface (no model, no download)."""

from __future__ import annotations

from services.kb_rerank import CrossEncoderReranker, make_reranker


async def test_scores_decide_the_order_and_ties_keep_input_order():
    seen: list[list[tuple[str, str]]] = []

    def scorer(pairs):
        seen.append(pairs)
        return [0.1, 0.9, 0.9, 0.5]

    r = CrossEncoderReranker(scorer)
    cands = [("a", "ta"), ("b", "tb"), ("c", "tc"), ("d", "td")]
    assert await r.rerank("q", cands, 3) == ["b", "c", "d"]
    assert seen == [[("q", "ta"), ("q", "tb"), ("q", "tc"), ("q", "td")]]
    assert await r.rerank("q", [], 3) == []


def test_none_means_no_reranker_and_no_import():
    assert make_reranker("none") is None
    assert make_reranker("") is None
