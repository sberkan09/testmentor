"""`passages: index` in the measurement pipeline (paket 7): corpus loading, vector cache, run.

No network, no model: a temporary corpus cache, the fake model and fake embeddings."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from eval.golden import load_golden
from eval.kb_corpus import ChunkVectorCache, CorpusMissing, load_corpus
from eval.pipeline import EmbeddingCache, Pipeline
from services.fake_llm import FakeComplete, FakeEmbed

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
EXAMPLES = yaml.safe_load((ROOT / CFG["examples_file"]).read_text(encoding="utf-8"))


def write_cache(root: Path, project: str = "kk") -> Path:
    """A corpus cache like `python -m eval.corpus fetch` writes: a corpus document, a zip member
    document, a mixed document with a stripped view, a reference document (answer key)."""
    base = root / "cache" / project
    (base / "text" / "MULTI").mkdir(parents=True)
    (base / "text" / "SPEC.txt").write_text("# Kilitleme\n\nHesap kilitleme kuralı geçerlidir.\n")
    (base / "text" / "MULTI" / "ch1.txt").write_text("# Bölüm\n\nParola uzunluğu kuralı.\n")
    (base / "text" / "MIXED.txt").write_text("# M\n\nANSWERKEY test prosedürü.\n\nGenel metin.\n")
    (base / "text" / "MIXED.writer.txt").write_text("# M\n\nGenel metin.\n")
    (base / "text" / "REF.txt").write_text("# R\n\nANSWERKEY referans test.\n")
    (base / "text" / "CAT.txt").write_text(
        json.dumps({"controls": [{"title": "Erişim denetimi", "parts": ["Kullanıcı kimliği"]}]})
    )
    index = {
        "SPEC": {"role": "corpus", "language": "tr", "texts": [{"file": "text/SPEC.txt"}]},
        "MULTI": {
            "role": "corpus",
            "language": "tr",
            "texts": [{"file": "text/MULTI/ch1.txt", "member": "ch1.xml"}],
        },
        "MIXED": {
            "role": "mixed",
            "language": "tr",
            "texts": [{"file": "text/MIXED.txt", "writer_file": "text/MIXED.writer.txt"}],
        },
        "REF": {"role": "reference", "language": "tr", "texts": [{"file": "text/REF.txt"}]},
        "CAT": {"role": "corpus", "language": "en", "texts": [{"file": "text/CAT.txt"}]},
    }
    (base / "index.json").write_text(json.dumps(index))
    visible = ["text/CAT.txt", "text/MIXED.writer.txt", "text/MULTI/ch1.txt", "text/SPEC.txt"]
    (base / "writer_visible.txt").write_text("".join(f + "\n" for f in visible))
    return base


def test_only_writer_visible_documents_are_loaded(tmp_path):
    write_cache(tmp_path)
    docs = dict(load_corpus("KK", root=tmp_path))
    assert sorted(docs) == ["CAT", "MIXED", "MULTI/ch1", "SPEC"]
    joined = "\n".join(docs.values())
    assert "ANSWERKEY" not in joined  # reference documents and reference parts stay out
    assert "Genel metin" in docs["MIXED"]
    assert "Erişim denetimi" in docs["CAT"] and "{" not in docs["CAT"]  # JSON flattened to text


def test_missing_cache_raises_instead_of_falling_back(tmp_path):
    with pytest.raises(CorpusMissing, match="eval.corpus fetch"):
        load_corpus("KK", root=tmp_path)


def test_a_listed_reference_document_is_refused(tmp_path):
    base = write_cache(tmp_path)
    (base / "writer_visible.txt").write_text("text/REF.txt\n")
    with pytest.raises(CorpusMissing, match="reference"):
        load_corpus("KK", root=tmp_path)


async def test_chunk_vectors_are_cached_on_disk(tmp_path):
    calls: list[int] = []

    async def embed(texts):
        calls.append(len(texts))
        return await FakeEmbed().__call__(texts)

    from core.kb.chunking import chunk_document

    chunks = chunk_document("D", "# A\n\n" + "söz " * 400, chunk_tokens=50, overlap_tokens=0)
    cache = ChunkVectorCache(tmp_path / "kb", "bge-m3@1", embed)
    first = await cache.get("KK", chunks)
    again = await ChunkVectorCache(tmp_path / "kb", "bge-m3@1", embed).get("KK", chunks)
    assert np.allclose(first, again) and len(first) == len(chunks)
    assert sum(calls) == len(chunks)  # embedded once, then read from disk
    other = ChunkVectorCache(tmp_path / "kb", "other-model@1", embed)
    await other.get("KK", chunks)
    assert sum(calls) == 2 * len(chunks)  # a new model version does not reuse vectors


def kk_pipeline(tmp_path, cfg_over: dict) -> tuple[Pipeline, FakeComplete]:
    cfg = {**CFG, **cfg_over}
    emb = FakeEmbed()
    cache = EmbeddingCache(tmp_path / "emb.json", "fake@1", emb)
    fake = FakeComplete()
    kb_cache = ChunkVectorCache(tmp_path / "kb", "fake@1", emb)
    pipe = Pipeline(None, cache, cfg, EXAMPLES, complete=fake, kb_vectors=kb_cache)
    return pipe, fake


async def test_index_mode_retrieves_from_the_corpus_into_layer_4(tmp_path, monkeypatch):
    golden = load_golden(projects=["KK"])
    write_cache(tmp_path, "kk")
    import eval.kb_corpus as kc

    monkeypatch.setattr(kc, "CORPUS_DIR", tmp_path)
    pipe, fake = kk_pipeline(tmp_path, {"passages": "index", "kb": {**CFG["kb"], "top_k": 3}})
    await pipe.run(golden)
    user = [r.messages[-1]["content"] for r in fake.requests if r.schema.__name__ == "TestCaseSet"]
    assert user
    layers = [u[u.index("# Retrieved passages") : u.index("# Requirements")] for u in user]
    assert all("(none)" not in layer for layer in layers)
    assert all("[SPEC §Kilitleme]" in layer or "[MULTI/ch1 " in layer for layer in layers)
    assert all("ANSWERKEY" not in u for u in user)


async def test_index_mode_without_a_cache_fails_before_any_model_call(tmp_path, monkeypatch):
    import eval.kb_corpus as kc

    monkeypatch.setattr(kc, "CORPUS_DIR", tmp_path)
    golden = load_golden(projects=["KK"])
    pipe, fake = kk_pipeline(tmp_path, {"passages": "index"})
    with pytest.raises(CorpusMissing):  # never a silent fall back to "(none)"
        await pipe.run(golden)
    assert fake.requests == []


async def test_card_methods_only_empties_the_card_text(tmp_path):
    golden = load_golden(projects=["KK"])
    pipe, fake = kk_pipeline(tmp_path, {"card": "methods_only"})
    await pipe.run(golden)
    user = next(
        r.messages[-1]["content"] for r in fake.requests if r.schema.__name__ == "TestCaseSet"
    )
    assert user.startswith("# Project card\n\nVerification methods")
    pipe2, fake2 = kk_pipeline(tmp_path, {})
    await pipe2.run(golden)
    full = next(
        r.messages[-1]["content"] for r in fake2.requests if r.schema.__name__ == "TestCaseSet"
    )
    assert full.startswith("# Project card\nProject:") and "Domain:" in full


def test_unknown_modes_and_example_settings_are_refused(tmp_path):
    with pytest.raises(ValueError, match="passages"):
        kk_pipeline(tmp_path, {"passages": "bogus"})
    with pytest.raises(ValueError, match="card"):
        kk_pipeline(tmp_path, {"card": "bogus"})
    with pytest.raises(ValueError, match="example pool"):
        kk_pipeline(tmp_path, {"kb": {**CFG["kb"], "examples": 2}})


async def test_golden_v1_kdh_runs_in_index_mode_over_the_committed_documents(tmp_path, monkeypatch):
    """The batch runs golden v1: build a corpus cache from the committed KDH texts (the system
    documents and the snapshots) and run the whole project once with the fakes."""
    from eval.golden_v1 import load_golden_v1

    corpus = ROOT / "eval" / "corpus" / "kdh"
    files = sorted((corpus / "system").glob("*.md")) + sorted((corpus / "snapshots").rglob("*.md"))
    assert len(files) > 10
    base = tmp_path / "cache" / "kdh"
    (base / "text").mkdir(parents=True)
    index, visible = {}, []
    for f in files:
        doc = "-".join(f.relative_to(corpus).with_suffix("").parts)
        rel = f"text/{doc}.txt"
        (base / rel).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        index[doc] = {"role": "corpus", "language": "en", "texts": [{"file": rel}]}
        visible.append(rel)
    (base / "index.json").write_text(json.dumps(index))
    (base / "writer_visible.txt").write_text("".join(f + "\n" for f in sorted(visible)))
    import eval.kb_corpus as kc

    monkeypatch.setattr(kc, "CORPUS_DIR", tmp_path)
    golden = load_golden_v1(projects=["KDH"])
    pipe, fake = kk_pipeline(tmp_path, {"passages": "index"})
    res = await pipe.run(golden)
    kb = next(r for r in res.records if r.get("type") == "kb")
    assert kb["chunks"] > 500
    project = next(r for r in res.records if r.get("type") == "project")
    assert not project["errors"]
    retrieved = [ids for ids in project["retrieval"].values()]
    assert retrieved and all(len(ids) == 8 for ids in retrieved)  # kb.top_k at the default
    prompts = [
        r.messages[-1]["content"] for r in fake.requests if r.schema.__name__ == "TestCaseSet"
    ]
    assert prompts and all(
        "(none)" not in p[p.index("# Retrieved") : p.index("# Requirements")] for p in prompts
    )


def test_d9_experiment_arms_change_exactly_one_setting():
    from eval.run import load_experiment

    def merged(name: str) -> dict:
        return load_experiment(ROOT / "config" / "experiments" / f"{name}.yaml")[1]

    base = merged("d9-index-base")
    assert base["passages"] == "index" and base["card"] == "full"
    assert base["kb"] == CFG["kb"]  # the base arm runs at the working assumptions
    arms = {
        "d9-chunk300": ("kb", "chunk_tokens", 300),
        "d9-chunk500": ("kb", "chunk_tokens", 500),
        "d9-chunk800": ("kb", "chunk_tokens", 800),
        "d9-top4": ("kb", "top_k", 4),
        "d9-top12": ("kb", "top_k", 12),
        "d9-card-off": (None, "card", "methods_only"),
    }
    for name, (section, key, value) in arms.items():
        expected = json.loads(json.dumps(base))
        if section:
            expected[section][key] = value
        else:
            expected[key] = value
        assert merged(name) == expected, name  # nothing else differs, no new keys


def test_paket7_batch_lists_existing_experiments():
    batch = yaml.safe_load((ROOT / "config" / "batches" / "paket7.yaml").read_text("utf-8"))
    assert batch["max_hours"] == 1.5
    names = [s["experiment"] for s in batch["steps"]]
    assert names[0] == "d9-index-base" and len(set(names)) == len(names) == 7
    for n in names:
        assert (ROOT / "config" / "experiments" / f"{n}.yaml").exists()
