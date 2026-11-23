"""In-memory hybrid index, ingestion, retrieval and example pool wiring (paket 7)."""

from __future__ import annotations

import pytest

from core.kb.chunking import chunk_document
from core.kb.settings import KbSettings
from core.nodes import RequirementContent
from services.fake_llm import FakeEmbed
from services.kb_examples import ExampleEntry, ExamplePool
from services.kb_index import InMemoryIndex, ingest_document
from services.kb_retrieve import (
    make_example_source,
    make_passages,
    make_retrieve,
    make_select_examples,
)

SETTINGS = KbSettings(chunk_tokens=40, chunk_overlap_tokens=0, top_k=3, rrf_depth=10)


def chunks(doc: str, *paras: str):
    text = "# H\n\n" + "\n\n".join(paras)
    return chunk_document(doc, text, chunk_tokens=400, overlap_tokens=0)


def test_dense_and_keyword_results_are_fused():
    idx = InMemoryIndex(SETTINGS)
    cs = [
        chunk_document(f"D{i}", f"# H\n\n{t}", chunk_tokens=400, overlap_tokens=0)[0]
        for i, t in enumerate(("alpha beta", "gamma delta", "epsilon zeta"))
    ]
    vectors = [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]]
    idx.add("P", cs, vectors)
    # keyword hits chunk 1 only; the dense vector is closest to chunk 0
    out = idx.search("P", ["gamma"], 2, [1.0, 0.1])
    assert out[0] in {cs[0].passage_id, cs[1].passage_id}
    assert set(out) == {cs[0].passage_id, cs[1].passage_id}
    # keyword only (no vector) and dense only (no keyword match)
    assert idx.search("P", ["gamma"], 2) == [cs[1].passage_id]
    assert idx.search("P", ["yok"], 1, [0.0, 1.0]) == [cs[1].passage_id]
    assert idx.search("P", ["yok"], 1) == []
    assert idx.search("other", ["gamma"], 2, [1.0, 0.0]) == []


def test_texts_are_prompt_ready_and_project_scoped():
    idx = InMemoryIndex(SETTINGS)
    c = chunks("D", "alpha beta")[0]
    idx.add("P", [c], [[1.0, 0.0]])
    assert idx.texts("P", [c.passage_id]) == [c.prompt_text()]
    assert c.prompt_text().startswith("[D §H] ") and c.prompt_text().endswith("alpha beta")
    with pytest.raises(KeyError):
        idx.texts("Q", [c.passage_id])
    with pytest.raises(KeyError):
        idx.texts("P", ["D#0@00000000"])


def test_adding_a_document_again_replaces_it_and_bumps_the_version():
    idx = InMemoryIndex(SETTINGS)
    v0 = idx.version("P")
    old = chunks("D", "eski metin")[0]
    idx.add("P", [old], [[1.0, 0.0]])
    v1 = idx.version("P")
    new = chunks("D", "yeni metin")[0]
    idx.add("P", [new], [[1.0, 0.0]])
    assert len({v0, v1, idx.version("P")}) == 3
    assert idx.search("P", ["eski"], 3) == []
    assert idx.search("P", ["yeni"], 3) == [new.passage_id]
    idx.remove_document("P", "D")
    assert idx.search("P", ["yeni"], 3) == []
    assert idx.version("Q") == v0  # other projects are not touched


def test_search_is_deterministic_with_ties():
    idx = InMemoryIndex(SETTINGS)
    cs = [
        chunk_document(f"D{i}", "# H\n\naynı metin", chunk_tokens=400, overlap_tokens=0)[0]
        for i in range(4)
    ]
    idx.add("P", cs, [[1.0, 0.0]] * 4)
    first = idx.search("P", ["aynı metin"], 4, [1.0, 0.0])
    assert first == idx.search("P", ["aynı metin"], 4, [1.0, 0.0])
    assert first == sorted(first)


async def test_ingest_document_chunks_and_embeds():
    idx = InMemoryIndex(SETTINGS)
    embed = FakeEmbed()
    text = "# Kilitleme\n\n" + " ".join(f"hesap kilitleme kuralı {i}." for i in range(60))
    made = await ingest_document(idx, "P", "KURAL", text, embed, SETTINGS)
    assert len(made) > 1 and all(c.document_id == "KURAL" for c in made)
    members = [RequirementContent(id="R1", text="Hesap kilitleme kuralı uygulanmalıdır.")]
    retrieve = make_retrieve(idx, "P", embed, 3)
    ids = await retrieve(members)
    assert len(ids) == 3 and set(ids) <= {c.passage_id for c in made}
    by_id = {c.passage_id: c.prompt_text() for c in made}
    assert make_passages(idx, "P")(ids) == [by_id[i] for i in ids]


async def test_retrieve_uses_member_texts_only_and_averages_their_vectors():
    idx = InMemoryIndex(SETTINGS)
    a = chunk_document("A", "# H\n\nbirinci konu", chunk_tokens=400, overlap_tokens=0)[0]
    b = chunk_document("B", "# H\n\nikinci konu", chunk_tokens=400, overlap_tokens=0)[0]
    idx.add("P", [a, b], [[1.0, 0.0], [0.0, 1.0]])
    seen: list[list[str]] = []

    async def embed(texts):
        seen.append(list(texts))
        return [[1.0, 0.0] if "x" in t else [0.0, 1.0] for t in texts]

    retrieve = make_retrieve(idx, "P", embed, 1)
    members = [
        RequirementContent(id="R1", text="x one"),
        RequirementContent(id="R2", text="x two"),
        RequirementContent(id="R3", text="x three"),
    ]
    assert await retrieve(members) == [a.passage_id]
    assert seen == [["x one", "x two", "x three"]]  # no cluster name, no ids
    assert await retrieve([]) == []


async def test_reranker_reorders_the_candidates():
    idx = InMemoryIndex(SETTINGS)
    cs = [
        chunk_document(f"D{i}", f"# H\n\nmetin {w}", chunk_tokens=400, overlap_tokens=0)[0]
        for i, w in enumerate(("bir", "iki", "üç", "dört"))
    ]
    idx.add("P", cs, [[1.0, 0.0], [0.9, 0.1], [0.8, 0.2], [0.0, 1.0]])
    asked: list[tuple[str, int, int]] = []

    class Reverse:
        async def rerank(self, query, candidates, k):
            asked.append((query, len(candidates), k))
            return [pid for pid, _ in reversed(candidates)][:k]

    async def embed(texts):
        return [[1.0, 0.0] for _ in texts]

    retrieve = make_retrieve(idx, "P", embed, 2, reranker=Reverse(), candidates=2, query_chars=50)
    out = await retrieve([RequirementContent(id="R1", text="metin sorgusu")])
    assert asked == [("metin sorgusu", 4, 2)]
    assert len(out) == 2


# Example pool ---------------------------------------------------------------------------------


def entry(key: str, text: str, vector, rendered: str | None = None) -> ExampleEntry:
    return ExampleEntry(
        key=key, requirement_text=text, text=rendered or f"örnek {key}", vector=tuple(vector)
    )


def test_pool_selects_most_similar_and_keys_follow_the_text():
    pool = ExamplePool()
    pool.add(
        "P",
        [entry("TC-1", "a", [1, 0]), entry("TC-2", "b", [0, 1]), entry("TC-3", "c", [0.6, 0.8])],
    )
    keys = pool.select("P", [1.0, 0.1], 2)
    assert [k.split("@")[0] for k in keys] == ["TC-1", "TC-3"]
    assert pool.select("P", [1.0, 0.1], 0) == []
    assert pool.select("Q", [1.0, 0.1], 2) == []
    assert pool.texts("P", keys) == ["örnek TC-1", "örnek TC-3"]
    # an edited example is a new key; the old key is gone
    pool.add("P", [entry("TC-1", "a", [1, 0], rendered="düzeltilmiş")])
    new = pool.select("P", [1.0, 0.1], 1)
    assert new[0].split("@")[0] == "TC-1" and new[0] != keys[0]
    with pytest.raises(KeyError):
        pool.texts("P", [keys[0]])
    with pytest.raises(KeyError):
        pool.texts("Q", new)


def test_pool_version_changes_with_content():
    pool = ExamplePool()
    v0 = pool.version("P")
    pool.add("P", [entry("TC-1", "a", [1, 0])])
    v1 = pool.version("P")
    pool.remove("P", "TC-1")
    assert len({v0, v1, pool.version("P")}) == 3


async def test_select_examples_wiring():
    pool = ExamplePool()
    pool.add("P", [entry("TC-1", "a", [1, 0]), entry("TC-2", "b", [0, 1])])

    async def embed(texts):
        return [[1.0, 0.0] for _ in texts]

    assert make_select_examples(pool, "P", embed, 0) is None
    select = make_select_examples(pool, "P", embed, 1)
    assert select is not None
    keys = await select([RequirementContent(id="R1", text="x")])
    assert make_example_source(pool, "P")(keys) == ["örnek TC-1"]


def test_pool_skips_examples_covering_a_member():
    """An example covering a cluster member is already a fixed test there (paket 11)."""
    pool = ExamplePool()
    near = ExampleEntry(
        key="TC-1",
        requirement_text="a",
        text="örnek TC-1",
        vector=(1.0, 0.0),
        excluded_with=frozenset({"R1"}),
    )
    pool.add("P", [near, entry("TC-2", "b", [0.6, 0.8])])
    assert [k.split("@")[0] for k in pool.select("P", [1.0, 0.0], 2)] == ["TC-1", "TC-2"]
    assert [k.split("@")[0] for k in pool.select("P", [1.0, 0.0], 2, exclude=["R1"])] == ["TC-2"]
    assert pool.select("P", [1.0, 0.0], 2, exclude=["R1", "R9"]) == pool.select(
        "P", [1.0, 0.0], 2, exclude=["R1"]
    )


async def test_build_entry_excludes_covered_and_extra_ids_and_selection_uses_members():
    from core.nodes import Step, TestCaseContent
    from services.kb_examples import build_entry

    async def embed(texts):
        return [[1.0, 0.0] for _ in texts]

    case = TestCaseContent(
        id="TC-1",
        title="t",
        covers=("R1",),
        type="Normal",
        priority="Orta",
        steps=(Step(no=1, action="a", expected="b"),),
    )
    e = await build_entry("TC-1", case, ["metin"], embed, excluded_with=["R7"])
    assert e.excluded_with == frozenset({"R1", "R7"})
    pool = ExamplePool()
    pool.add("P", [e])
    select = make_select_examples(pool, "P", embed, 1)
    assert select is not None
    assert await select([RequirementContent(id="R7", text="x")]) == []
    assert len(await select([RequirementContent(id="R2", text="x")])) == 1
