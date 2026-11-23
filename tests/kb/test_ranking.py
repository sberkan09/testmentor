"""BM25 and rank fusion (paket 7)."""

from __future__ import annotations

from core.kb.ranking import Bm25Index, rrf, tokenize


def test_tokenize_folds_case_and_turkish_letters():
    assert tokenize("Parola, ŞİFRE; ışık! Login-Attempt 3x") == [
        "parola",
        "sifre",
        "isik",
        "login",
        "attempt",
        "3x",
    ]
    assert tokenize("İstanbul ISPARTA") == ["istanbul", "isparta"]
    assert tokenize("") == []


def test_bm25_ranks_rare_terms_and_is_deterministic():
    idx = Bm25Index(k1=1.2, b=0.75)
    idx.add("a", "hesap kilitleme başarısız deneme")
    idx.add("b", "hesap oluşturma ve hesap silme")
    idx.add("c", "günlük kaydı zaman damgası")
    hits = idx.search("başarısız deneme kilitleme", 5)
    assert [h for h, _ in hits] == ["a"]
    assert [h for h, _ in idx.search("hesap", 5)] == ["b", "a"]  # tf 2 beats tf 1
    assert idx.search("yok böyle bir sözcük", 5) == []
    assert idx.search("hesap", 5) == idx.search("hesap", 5)


def test_bm25_ties_break_by_id_and_remove():
    idx = Bm25Index()
    for i in ("z", "m", "a"):
        idx.add(i, "aynı metin")
    assert [h for h, _ in idx.search("metin", 5)] == ["a", "m", "z"]
    idx.remove("a")
    assert [h for h, _ in idx.search("metin", 5)] == ["m", "z"]
    idx.add("m", "tamamen başka")  # replace
    assert [h for h, _ in idx.search("metin", 5)] == ["z"]


def test_rrf_fuses_ranks():
    fused = rrf([["a", "b", "c"], ["d", "b", "c"]], k=60)
    assert fused[:2] == ["b", "c"]  # ranks 2 and 2 beat 3 and 3, and both beat single hits
    assert set(fused) == {"a", "b", "c", "d"}
    assert rrf([["a"], []], k=60) == ["a"]
    assert rrf([], k=60) == []


def test_rrf_scores_and_tie_order():
    assert rrf([["a", "b"], ["b"]], k=60) == ["b", "a"]  # b: 1/62 + 1/61 beats a: 1/61
    assert rrf([["x"], ["y"]], k=60) == ["x", "y"]  # tie: first list's order, then id
