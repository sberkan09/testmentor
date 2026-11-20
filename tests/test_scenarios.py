"""D8 scenario runner and D7 unit packing over the stage pipeline (fake model, no network)."""

from __future__ import annotations

import json
import re

import httpx
import yaml

from core.metrics import ProjectOutcome, duplicate_tests
from eval.golden import load_golden
from eval.pipeline import EmbeddingCache, Pipeline, pack_units
from eval.run import deep_merge
from eval.scenarios import ScenarioPipeline, similarity
from services.llm_client import LLMClient
from services.settings import LLMSettings

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
EXAMPLES = yaml.safe_load((ROOT / CFG["examples_file"]).read_text(encoding="utf-8"))
ROW = re.compile(r"^([\w.-]+) \((\w*)\)(?: \[methods: ([^\]]*)\])?:", re.M)


def case(rid: str, n: int = 0) -> dict:
    return {
        "id": f"T{n}",
        "title": f"{rid} davranışı",
        "covers": [rid],
        "type": "Normal",
        "priority": "Orta",
        "preconditions": "",
        "test_inputs": "",
        "assumptions": "",
        "steps": [{"no": 1, "action": f"{rid} işlemini yap", "expected": "Sonuç görülür"}],
    }


class SchemaFake:
    """Answers by the requested schema: methods all Test; a test per Test row; incremental adds
    for the `Added:` ids; merge drops nothing."""

    def __init__(self) -> None:
        self.names: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        name = body["response_format"]["json_schema"]["name"]
        self.names.append(name)
        user = body["messages"][-1]["content"]
        block = user[user.rindex("# Requirements\n") :].split("\n\n#")[0]
        rows = ROW.findall(block)
        if name == "MethodBatch":
            out = {
                "decisions": [
                    {"requirement_id": r[0], "methods": ["Test"], "rationale": "x"} for r in rows
                ]
            }
        elif name == "TestCaseSet":
            m = re.search(r"The requirements (.+) are not covered yet", user)
            ids = m.group(1).split(", ") if m else [r[0] for r in rows if "Test" in r[2]]
            out = {"test_cases": [case(i, n) for n, i in enumerate(ids)]}
        elif name == "TestCaseDelta":
            m = re.search(r"^Added: (.+)$", user, re.M)
            out = {"add": [case(i) for i in (m.group(1).split(", ") if m else [])], "update": []}
        else:
            out = {"drop": []}
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": json.dumps(out, ensure_ascii=False)}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 10}},
        ]
        sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse.encode()
        )


def llm_settings() -> LLMSettings:
    return LLMSettings(engine="vllm", model="m", base_url="http://fake/v1", served_model_name="m")


async def fake_embed(texts):
    return [[1.0, 0.0] if len(t) % 2 else [0.0, 1.0] for t in texts]


async def run_scenario(tmp_path, scenario: dict, over: dict | None = None):
    fake = SchemaFake()
    golden = load_golden()
    cfg = deep_merge(CFG, over or {})
    cache = EmbeddingCache(tmp_path / "e.json", "v", fake_embed)
    async with LLMClient(llm_settings(), transport=httpx.MockTransport(fake.handle)) as client:
        res = await ScenarioPipeline(client, cache, cfg, EXAMPLES, scenario=scenario).run(golden)
    return res, fake


async def test_add_arms_share_the_baseline(tmp_path):
    res, fake = await run_scenario(
        tmp_path,
        {
            "kind": "add",
            "min_test_members": 2,
            "arms": {
                "incremental": {"regeneration": "incremental"},
                "full": {"regeneration": "full"},
            },
        },
    )
    inc, full = res.extra["arms"]["incremental"], res.extra["arms"]["full"]
    assert inc["units"] == full["units"] > 0 and not inc["errors"] and not full["errors"]
    assert inc["preservation_rate"] == 1.0 and inc["identical_rate"] == 1.0
    assert inc["pinned_kept_rate"] == full["pinned_kept_rate"] == 1.0
    assert inc["pinned_repeats"] == 0 and inc["new_coverage_before_repair"] == 1.0
    assert {r["mode"] for r in inc["rows"]} == {"incremental"}
    assert {r["mode"] for r in full["rows"]} == {"full"}
    assert inc["change_calls"] == full["change_calls"] == inc["units"]  # one call per set
    # one baseline for both arms: its calls are counted once
    phases = [r["phase"] for r in res.records if r.get("type") == "call"]
    assert set(phases) == {"baseline", "change:incremental", "change:full"}
    assert res.extra["baseline_calls"] == phases.count("baseline")
    arms = [r["arm"] for r in res.records if r.get("type") == "scenario_project"]
    assert sorted(arms) == sorted(["incremental", "full"] * 5)


async def test_remove_prune_needs_no_call(tmp_path):
    res, _ = await run_scenario(
        tmp_path,
        {
            "kind": "remove",
            "min_test_members": 2,
            "arms": {"call": {"prune_removals": False}, "prune": {"prune_removals": True}},
        },
    )
    call, prune = res.extra["arms"]["call"], res.extra["arms"]["prune"]
    assert call["change_calls"] == call["units"] > 0
    assert prune["change_calls"] == 0
    assert prune["preservation_rate"] == call["preservation_rate"] == 1.0


async def test_merge_with_and_without_sources(tmp_path):
    res, _ = await run_scenario(
        tmp_path,
        {
            "kind": "merge",
            "arms": {"prompt": {"merge_sources": True}, "full": {"merge_sources": False}},
        },
    )
    prompt, full = res.extra["arms"]["prompt"], res.extra["arms"]["full"]
    assert {r["mode"] for r in prompt["rows"]} == {"merge"}
    assert {r["mode"] for r in full["rows"]} == {"full"}
    assert prompt["coverage"] == full["coverage"] == 1.0


def test_unknown_arm_key_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="unknown keys"):
        ScenarioPipeline(
            None,
            EmbeddingCache(ROOT / "x.json", "v", None),
            CFG,
            EXAMPLES,
            complete=lambda r: None,
            scenario={"kind": "add", "arms": {"x": {"temperature": 1}}},
        )


def test_pack_units_keeps_order_and_limit():
    clusters = [["A1", "A2"], ["B1"], ["C1", "C2", "C3"], ["D1"] * 6, ["E1"]]
    assert pack_units(clusters, 4) == [["A1", "A2", "B1"], ["C1", "C2", "C3"], ["D1"] * 6, ["E1"]]
    assert pack_units([["A"], ["B"]], 1) == [["A"], ["B"]]


async def test_unit_packing_merges_reference_clusters(tmp_path):
    fake = SchemaFake()
    golden = load_golden(projects=["KK"])
    cfg = deep_merge(CFG, {"unit_packing": True, "generation": {"max_unit_size": 8}})
    cache = EmbeddingCache(tmp_path / "e.json", "v", fake_embed)
    async with LLMClient(llm_settings(), transport=httpx.MockTransport(fake.handle)) as client:
        res = await Pipeline(client, cache, cfg, EXAMPLES).run(golden)
    project = next(r for r in res.records if r.get("type") == "project")
    assert project["generation_clusters"] == [sorted(r.id for r in golden.projects[0].requirements)]
    assert fake.names.count("TestCaseSet") == 1


def test_duplicate_tests_and_similarity():
    a = case("R1") | {"id": "1"}
    b = case("R1") | {"id": "2", "title": "Başka başlık"}
    c = case("R2") | {"id": "3"}
    out = duplicate_tests([ProjectOutcome("P", [], {}, [a, b, c])])
    assert out == {"duplicate_pairs": 1, "duplicate_test_rate": round(2 / 3, 4)}
    assert similarity(a, a) == 1.0 and similarity(a, c) < 1.0


async def test_runner_main_writes_outputs_metrics_report(tmp_path, monkeypatch):
    """`eval.run.main` end to end (fake model): plain and scenario experiments write outputs,
    metrics and the report, and the judge's loader reads the outputs."""
    import sys as _sys

    import eval.run as run
    from eval.golden_v1 import load_golden_v1
    from eval.judge import judge_prompt, load_projects, reference_checks

    fake = SchemaFake()

    def from_config(cls, *a, **kw):
        return LLMClient(llm_settings(), transport=httpx.MockTransport(fake.handle))

    async def served(client):
        return "m"

    monkeypatch.setattr(run.LLMClient, "from_config", classmethod(from_config))
    monkeypatch.setattr(run, "check_served", served)
    monkeypatch.setattr(
        run,
        "EmbeddingCache",
        lambda path, version, embed: EmbeddingCache(tmp_path / "e.json", version, fake_embed),
    )
    monkeypatch.setattr(run, "read_state", lambda: {})
    for k, v in {
        "LLM_BASE_URL": "http://fake/v1",
        "LLM_ENGINE": "vllm",
        "LLM_MODEL": "qwen3.8-27b",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)

    for name in ("p3-smoke-v0", "p3-smoke-d8"):
        out = tmp_path / name
        monkeypatch.setattr(
            _sys,
            "argv",
            [
                "run",
                "--config",
                str(ROOT / "config/experiments" / f"{name}.yaml"),
                "--out",
                str(out),
            ],
        )
        assert await run.main() == 0
        run_dir = next(out.iterdir())
        metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
        report = (run_dir / "report.md").read_text(encoding="utf-8")
        assert metrics["meta"]["prompt_versions"]["test_set"].startswith("s1.g3+")
        assert "no_test_violations_raw" in metrics["runs"][0]["all"]
        projects = load_projects(run_dir)[0]
        assert projects and all(p["test_cases"] for p in projects.values())
        if name == "p3-smoke-d8":
            assert set(metrics["runs"][0]["scenario"]["arms"]) == {"incremental", "full"}
            assert "Senaryo (add" in report
            golden = load_golden_v1(projects=["ETC"])
            checks = reference_checks(golden)
            rid = next(r for r in checks if r.startswith("ETC"))
            tests = [t for t in projects["ETC"]["test_cases"] if rid in t["covers"]]
            raw = next(r for r in golden.projects[0].raw["requirements"] if r["id"] == rid)
            assert judge_prompt(raw, checks[rid], tests)
