"""D10 (paket 11): the leak-free reference example pool, the experiment arms and the batch.

No network, no model: fake model and fake embeddings; golden v1 KDH with the committed corpus."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from eval.example_pool import (
    ExampleLeak,
    build_reference_pool,
    leak_check,
    reference_case,
    related,
)
from services.fake_llm import FakeEmbed
from services.kb_examples import ExamplePool

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "pipeline.yaml").read_text(encoding="utf-8"))


def req(rid: str, sources: list[str], checks: int = 2) -> dict:
    return {
        "id": rid,
        "text": f"{rid} gereksinim metni",
        "reference_candidates": sources,
        "reference_preconditions": f"{rid} ön koşul",
        "reference_checks": [
            {"action": f"{rid} eylem {i}", "expected": f"{rid} sonuç {i}"} for i in range(checks)
        ],
    }


PROJECT = {
    "requirements": [
        req("R1", ["SRC-A"]),
        req("R2", ["SRC-A", "SRC-B"]),  # shares SRC-A with R1
        req("R3", ["SRC-C"]),
        req("R4", []),
        req("R5", ["SRC-D"], checks=0),  # no reference: not pooled
    ]
}


def test_reference_case_has_one_step_per_check_and_its_preconditions():
    case = reference_case(PROJECT["requirements"][0], "Normal", "Orta")
    assert case is not None
    assert case.id == "REF-R1" and case.covers == ("R1",)
    assert [(s.no, s.action, s.expected) for s in case.steps] == [
        (1, "R1 eylem 0", "R1 sonuç 0"),
        (2, "R1 eylem 1", "R1 sonuç 1"),
    ]
    assert case.preconditions == "R1 ön koşul"
    assert reference_case(PROJECT["requirements"][4], "Normal", "Orta") is None


def test_related_requirements_share_a_reference_source():
    rel = related(PROJECT["requirements"])
    assert rel["R1"] == {"R2"} and rel["R2"] == {"R1"}
    assert rel["R3"] == rel["R4"] == frozenset()


async def test_pool_never_offers_a_members_reference_or_a_shared_source():
    entries = await build_reference_pool(PROJECT, FakeEmbed(), test_type="Normal", priority="Orta")
    assert sorted(e.key for e in entries) == ["REF-R1", "REF-R2", "REF-R3", "REF-R4"]
    pool = ExamplePool()
    pool.add("P", entries)
    picked = pool.select("P", [1.0] * FakeEmbed().dim, 10, exclude=["R1"])
    rids = {k.split("@")[0] for k in picked}
    assert rids == {"REF-R3", "REF-R4"}  # R1 itself and R2 (shares SRC-A) are out
    expected = [k.split("@")[0].removeprefix("REF-") for k in picked]
    assert leak_check(PROJECT, {"c": ("R1",)}, {"c": picked}) == {"c": expected}


def test_leak_check_catches_a_member_and_a_shared_source():
    with pytest.raises(ExampleLeak, match="covers member"):
        leak_check(PROJECT, {"c": ("R1", "R3")}, {"c": ["REF-R3@abc"]})
    with pytest.raises(ExampleLeak, match="shares reference source"):
        leak_check(PROJECT, {"c": ("R1",)}, {"c": ["REF-R2@abc"]})
    assert leak_check(PROJECT, {"c": ("R1",)}, {"c": ["REF-R4@abc"]}) == {"c": ["R4"]}


async def test_golden_v1_kdh_with_examples_runs_without_leaks(tmp_path, monkeypatch):
    """Two examples per cluster over golden v1 KDH (reference clusters, committed corpus): every
    test set prompt carries the examples section, and the run's own leak check passes."""
    from eval.golden_v1 import load_golden_v1
    from tests.test_kb_eval import EXAMPLES, kk_pipeline

    corpus = ROOT / "eval" / "corpus" / "kdh"
    files = sorted((corpus / "system").glob("*.md")) + sorted((corpus / "snapshots").rglob("*.md"))
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
    assert EXAMPLES
    golden = load_golden_v1(projects=["KDH"])
    pipe, fake = kk_pipeline(
        tmp_path,
        {"passages": "index", "example_pool": "reference", "kb": {**CFG["kb"], "examples": 2}},
    )
    res = await pipe.run(golden)
    project = next(r for r in res.records if r.get("type") == "project")
    assert not project["errors"]
    examples = project["examples"]
    clusters = project["generation_clusters"]
    assert len(examples) == len(clusters)
    assert all(len(rids) == 2 for rids in examples.values())
    for members, rids in zip(clusters, examples.values(), strict=True):
        assert not set(members) & set(rids)
    prompts = [
        r.messages[-1]["content"] for r in fake.requests if r.schema.__name__ == "TestCaseSet"
    ]
    assert prompts and all("# Project examples" in p for p in prompts)


def merged(name: str) -> dict:
    from eval.run import load_experiment

    return load_experiment(ROOT / "config" / "experiments" / f"{name}.yaml")[1]


def test_paket11_arms_change_exactly_one_setting():
    base = merged("d10-base")
    assert base["passages"] == "index" and base["example_pool"] == "reference"
    assert base["kb"] == {**CFG["kb"], "examples": 0}  # the decided D9 settings otherwise
    arms = {
        "d10-ex2": ("examples", 2),
        "d10-ex4": ("examples", 4),
        "d9-rerank": ("reranker", "BAAI/bge-reranker-v2-m3"),
    }
    for name, (key, value) in arms.items():
        expected = json.loads(json.dumps(base))
        expected["kb"][key] = value
        assert merged(name) == expected, name


def test_paket11_batch_lists_existing_experiments_base_first():
    batch = yaml.safe_load((ROOT / "config" / "batches" / "paket11.yaml").read_text("utf-8"))
    names = [s["experiment"] for s in batch["steps"]]
    # the reranker arm first: its CPU reranking falls in the watchdog's first 30 (uncounted) minutes
    assert names[0] == "d9-rerank" and "d10-base" in names and len(set(names)) == len(names) == 4
    assert batch["max_hours"] <= 1.5
    for n in names:
        assert (ROOT / "config" / "experiments" / f"{n}.yaml").exists()


def test_style_shape_and_distance():
    from eval.style import distance, reference_cases, shape

    gen = shape([{"steps": [{"action": "ab", "expected": "abcd"}], "preconditions": "x"}] * 2)
    assert gen == {"steps": 1, "action_chars": 2, "expected_chars": 4, "precondition_chars": 1}
    ref = shape(reference_cases({"requirements": [req("R1", [])]}))
    assert ref["steps"] == 2 and ref["precondition_chars"] == len("R1 ön koşul")
    assert distance(ref, ref) == 0 and distance(gen, ref) > 0


def test_paket11b_repeats_the_two_arms_unchanged():
    batch = yaml.safe_load((ROOT / "config" / "batches" / "paket11b.yaml").read_text("utf-8"))
    assert [s["experiment"] for s in batch["steps"]] == ["d10-base-r3", "d10-ex4-r3"]
    for name in ("d10-base", "d10-ex4"):
        once = yaml.safe_load((ROOT / "config" / "experiments" / f"{name}.yaml").read_text("utf-8"))
        rep = yaml.safe_load(
            (ROOT / "config" / "experiments" / f"{name}-r3.yaml").read_text("utf-8")
        )
        assert rep["repeat"] == 3 and rep["pipeline"] == once["pipeline"]
        assert merged(f"{name}-r3") == merged(name)
