import json
import re

import httpx
import yaml

from core.metrics import layer1
from eval.golden import load_golden
from eval.pipeline import EmbeddingCache, Pipeline
from eval.run import deep_merge, layer1_diff
from services.llm_client import LLMClient, LLMError
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


def test_synthetic_passages_differ_per_cluster_and_hit_size():
    from eval.run import synthetic_passages

    golden = load_golden()
    a = synthetic_passages(golden, "P/c1", 2000)
    b = synthetic_passages(golden, "P/c2", 2000)
    assert a != b and a == synthetic_passages(golden, "P/c1", 2000)
    assert sum(map(len, a)) >= 8000
    assert synthetic_passages(golden, "x", 0) == []


# Paket 3: stage pipeline ------------------------------------------------------------------------


async def test_reference_prompt_is_the_paket1_prompt(tmp_path):
    """The stage pipeline sends what paket 1's bare pipeline sent (baseline comparability)."""
    from core.prompts import Method, ProjectCard, generation_messages
    from core.schemas import case_set_model

    fake = FakeModel()
    golden = load_golden(projects=["KK"])
    p = golden.projects[0]
    cache = EmbeddingCache(tmp_path / "e.json", "v", fake_embed)
    async with LLMClient(settings(), transport=httpx.MockTransport(fake.handle)) as client:
        await Pipeline(client, cache, CFG, EXAMPLES).run(golden)
    cluster = p.reference_clusters()[0]
    by_id = {r.id: r for r in p.requirements}
    refs = {r["id"]: sorted(r["verification_methods"]) for r in p.raw["requirements"]}
    card = ProjectCard(
        p.key, p.name, p.domain, tuple(Method(m["name"], m["criterion"]) for m in CFG["methods"])
    )
    expected = generation_messages(
        card,
        [by_id[i] for i in cluster],
        {i: refs[i] for i in cluster},
        schema=case_set_model(
            tuple(CFG["test_types"]), tuple(CFG["priorities"])
        ).model_json_schema(),
        examples=EXAMPLES,
        test_method=CFG["test_method"],
        types=CFG["test_types"],
        priorities=CFG["priorities"],
    )
    assert expected in [b["messages"] for b in fake.bodies]


async def test_raw_violations_count_model_output_before_the_filter(tmp_path):
    """Reference mode: the producer drops covers of non-Test requirements, so the final sets
    show no violation; the raw count still sees the model writing them (threshold uses it)."""
    from core.metrics import passes_thresholds

    golden = load_golden(projects=["KMU"])  # KMU-008 has no Test method
    no_test = [
        r["id"]
        for r in golden.projects[0].raw["requirements"]
        if "Test" not in r["verification_methods"]
    ]
    assert no_test

    class Violating(FakeModel):
        def handle(self, request):
            body = json.loads(request.content)
            user = body["messages"][-1]["content"]
            if "# Task: verification method" in user:
                return super().handle(request)
            rows = re.findall(r"^(\w+-\d+) \(", user[user.rindex("# Requirements") :], re.M)
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
                    for i, rid in enumerate(rows)  # every member, Test or not
                ]
            }
            chunks = [
                {"choices": [{"index": 0, "delta": {"content": json.dumps(out)}}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]
            sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=sse.encode()
            )

    fake = Violating()
    cache = EmbeddingCache(tmp_path / "e.json", "v", fake_embed)
    async with LLMClient(settings(), transport=httpx.MockTransport(fake.handle)) as client:
        res = await Pipeline(client, cache, CFG, EXAMPLES).run(golden)
    m = layer1(
        res.outcomes,
        golden.refs(),
        res.calls,
        res.wall_s,
        CFG["test_method"],
        raw_outputs=res.raw_outputs,
    )
    assert m["all"]["no_test_violations"] == 0
    assert m["all"]["no_test_violations_raw"] >= len(no_test)
    assert passes_thresholds(m, CFG["thresholds"])["no_test_violations"] is False


async def test_driver_isolates_a_failing_job():
    """One job raising (an HTTP 400, say) fails only its own nodes; the others are produced."""
    from core.llm import LLMReply
    from core.nodes import NodeKind, ref
    from eval.stage_driver import drive
    from tests.stages.helpers import SETTINGS, project, smart_reply

    async def complete(request):
        rows = request.messages[-1]["content"]
        if request.stage == NodeKind.TEST_SET and "R1 (tr)" in rows:
            raise LLMError("HTTP 400: bad request")
        out = smart_reply(request)
        content = json.dumps(out, ensure_ascii=False)
        return LLMReply(content=content, parsed=request.schema.model_validate_json(content))

    async def embed(texts):
        return [[float(len(t)), 1.0] for t in texts]

    out = await drive(
        project(), complete, settings=SETTINGS, skip={NodeKind.CLUSTER_LABEL}, embed=embed
    )
    assert set(out.errors) == {ref(NodeKind.TEST_SET, "A")}
    assert out.errors[ref(NodeKind.TEST_SET, "A")].startswith("LLMError: HTTP 400")
    assert out.state.node(ref(NodeKind.TEST_SET, "A")).status.value == "failed"
    assert out.state.node(ref(NodeKind.TEST_SET, "B")).status.value == "fresh"
