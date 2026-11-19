import json
import re

import httpx
import yaml

from core.metrics import layer1
from eval.golden import load_golden
from eval.pipeline import EmbeddingCache, Pipeline
from eval.run import deep_merge, layer1_diff
from services.llm_client import LLMClient
from services.settings import LLMSettings

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
EXAMPLES = yaml.safe_load((ROOT / CFG["examples_file"]).read_text(encoding="utf-8"))


class FakeModel:
    """Answers classification with Test for everything; generation covers Test requirements,
    except that the first generation call for KK skips one requirement (exercises repair)."""

    def __init__(self):
        self.bodies = []
        self.skipped = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        user = body["messages"][-1]["content"]
        reqs_block = user[user.rindex("# Requirements") :]
        rows = re.findall(r"^(\w+-\d+) \((\w*)\)(?: \[methods: ([^\]]*)\])?:", reqs_block, re.M)
        if "# Task: verification method" in user:
            out = {
                "decisions": [
                    {"requirement_id": r[0], "methods": ["Test"], "rationale": "x"} for r in rows
                ]
            }
        else:
            need = [r[0] for r in rows if r[2] and "Test" in r[2].split(", ")]
            if "# Additional instruction" in user:
                need = re.findall(r"The requirements (.*) are not covered", user)[0].split(", ")
            elif need and need[0].startswith("KK") and not self.skipped:
                self.skipped = True
                need = need[1:] or need
            out = {
                "test_cases": [
                    {
                        "id": f"T{i}",
                        "title": "t",
                        "covers": [rid],
                        "type": "Normal",
                        "priority": "Orta",
                        "preconditions": "",
                        "test_inputs": "",
                        "assumptions": "",
                        "steps": [{"no": 1, "action": "a", "expected": "e"}],
                    }
                    for i, rid in enumerate(need)
                ]
            }
        text = json.dumps(out, ensure_ascii=False)
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 500},
        }
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": text}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            {"choices": [], "usage": usage},
        ]
        sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse.encode()
        )


def settings():
    return LLMSettings(
        engine="vllm",
        model="m",
        base_url="http://fake/v1",
        served_model_name="m",
        thinking_off={"chat_template_kwargs": {"enable_thinking": False}},
    )


async def fake_embed(texts):
    # Deterministic pseudo-embeddings: one-hot on the first character class.
    return [[1.0, 0.0] if len(t) % 2 else [0.0, 1.0] for t in texts]


async def test_pipeline_end_to_end(tmp_path):
    fake = FakeModel()
    golden = load_golden()
    cache = EmbeddingCache(tmp_path / "emb.json", "v", fake_embed)
    async with LLMClient(settings(), transport=httpx.MockTransport(fake.handle)) as client:
        res = await Pipeline(client, cache, CFG, EXAMPLES).run(golden)
    m = layer1(res.outcomes, golden.refs(), res.calls, res.wall_s, CFG["test_method"])
    assert m["calls"]["errors"] == 0 and m["calls"]["schema_valid_rate"] == 1.0
    assert m["all"]["coverage_rate"] == 1.0
    assert m["all"]["coverage_rate_before_repair"] < 1.0  # KK skipped one, repaired
    assert m["all"]["method_exact_match"] == 0.8  # 32 of 40 are Test only
    assert m["all"]["no_test_violations"] == 0  # generation uses reference methods
    assert m["all"]["step_structure_rate"] == 1.0
    assert any(c.kind == "repair" for c in res.calls)
    assert m["calls"]["prefix_cache_hit_rate"] == 0.5
    assert set(m["by_language"]) == {"en", "tr"}
    # All requests carry the schema and the thinking switch; all share the system prompt.
    assert all(b["response_format"]["type"] == "json_schema" for b in fake.bodies)
    assert len({b["messages"][0]["content"] for b in fake.bodies}) == 1
    assert (tmp_path / "emb.json").exists()


async def test_embedding_cache_without_service(tmp_path):
    cache = EmbeddingCache(tmp_path / "e.json", "v", fake_embed)
    first = await cache.get(["ab", "c"])
    offline = EmbeddingCache(tmp_path / "e.json", "v", None)
    assert await offline.get(["ab", "c"]) == first


async def test_predicted_inputs_mode(tmp_path):
    """End to end: classification errors (all Test) flow into generation."""
    fake = FakeModel()
    golden = load_golden()
    cache = EmbeddingCache(tmp_path / "e.json", "v", fake_embed)
    cfg = deep_merge(CFG, {"generation_inputs": "predicted"})
    async with LLMClient(settings(), transport=httpx.MockTransport(fake.handle)) as client:
        res = await Pipeline(client, cache, cfg, EXAMPLES).run(golden)
    m = layer1(res.outcomes, golden.refs(), res.calls, res.wall_s, CFG["test_method"])
    assert m["all"]["no_test_violations"] == 3  # 3 refs have no Test method
    assert m["all"]["coverage_rate"] == 1.0


def test_deep_merge_and_diff():
    merged = deep_merge(CFG, {"generation": {"thinking": True}})
    assert merged["generation"]["thinking"] is True
    assert merged["generation"]["temperature"] == CFG["generation"]["temperature"]
    assert CFG["generation"]["thinking"] is False
    assert layer1_diff(
        {"all": {"a": 1}, "calls": {"x": 1}}, {"all": {"a": 2}, "calls": {"x": 2}}
    ) == ["all.a: 1 → 2"]


def test_experiment_files_are_valid():
    from eval.run import load_experiment
    from services.settings import load_engines, load_models

    files = sorted((ROOT / "config" / "experiments").glob("*.yaml"))
    assert files
    for f in files:
        exp, cfg = load_experiment(f)
        assert exp["name"] == f.stem and exp.get("question") and exp.get("variable")
        assert exp["server"]["engine"] in load_engines()
        assert exp["server"]["model"] in load_models()
        assert set(cfg) == set(CFG)  # no misspelled top-level pipeline keys
        for stage in ("generation", "classification"):
            assert set(cfg[stage]) == set(CFG[stage])
        assert exp.get("quality", True) or exp.get("throughput")
