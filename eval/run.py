"""Measurement runner: `python -m eval.run --config config/experiments/<deney>.yaml`.

Writes results/<run id>/outputs.jsonl, metrics.json and report.md. An experiment file changes
one value; everything else comes from config/pipeline.yaml (working assumptions).

Experiment file keys:
    name, question, variable           report metadata
    server: {engine, model}            what the running pod must serve (checked)
    pipeline: {...}                    deep-merged over config/pipeline.yaml
    golden: v0|v1, projects: [...]     golden set and project subset
    scenario: {kind: add|remove|merge} D8 scenario run (eval/scenarios.py) instead of the pipeline
    quality: true|false                run the golden-set pipeline
    repeat: N                          quality runs; layer 1 differences are reported
    throughput: {concurrency: [1, 8, 16, 32], requests_per_level: 32}
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.metrics import layer1, passes_thresholds  # noqa: E402
from core.prompts import Method, ProjectCard, generation_messages  # noqa: E402
from core.schemas import case_set_model  # noqa: E402
from eval.golden import load_golden  # noqa: E402
from eval.golden_v1 import load_golden_v1  # noqa: E402
from eval.pipeline import EmbeddingCache, Pipeline  # noqa: E402
from eval.report import write_report  # noqa: E402
from eval.scenarios import ScenarioPipeline  # noqa: E402
from scripts.runpod_state import base_urls_from_state, read_state  # noqa: E402
from services.embedder import Embedder  # noqa: E402
from services.llm_client import LLMClient, LLMError  # noqa: E402
from services.settings import load_embedding_settings, load_models  # noqa: E402

EMBED_CACHE = ROOT / "eval" / "cache" / "embeddings.json"


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = (
            deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
        )
    return out


def load_experiment(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    exp = yaml.safe_load(path.read_text(encoding="utf-8"))
    base = yaml.safe_load((ROOT / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
    return exp, deep_merge(base, exp.get("pipeline") or {})


def point_at_pod(exp: dict[str, Any]) -> dict[str, Any]:
    """Use the recorded pod unless LLM_BASE_URL is set; check it serves the expected model."""
    server = exp.get("server") or {}
    pod = read_state().get("pod") or {}
    if "LLM_BASE_URL" not in os.environ and (urls := base_urls_from_state()):
        os.environ["LLM_BASE_URL"] = urls["llm"]
        os.environ.setdefault("EMBEDDING_BASE_URL", urls["embedding"])
    if server.get("engine"):
        os.environ["LLM_ENGINE"] = server["engine"]
    if server.get("model"):
        os.environ["LLM_MODEL"] = server["model"]
    for key in ("engine", "model"):
        if server.get(key) and pod and pod.get(key) != server[key]:
            raise SystemExit(f"pod serves {key}={pod.get(key)!r}, experiment needs {server[key]!r}")
    if (
        pod
        and "overrides" in server
        and (pod.get("overrides") or {}) != (server["overrides"] or {})
    ):
        raise SystemExit(
            f"pod overrides {pod.get('overrides')!r}, experiment needs {server['overrides']!r}"
        )
    return {
        "pod": pod.get("id"),
        "engine": pod.get("engine"),
        "model": pod.get("model"),
        "overrides": pod.get("overrides", {}),
    }


async def check_served(client: LLMClient) -> str:
    key = os.environ.get(client.settings.api_key_env or "", "")
    async with httpx.AsyncClient(timeout=20, headers={"Authorization": f"Bearer {key}"}) as http:
        r = await http.get(client.settings.base_url.rstrip("/") + "/models")
        r.raise_for_status()
        served = r.json()["data"][0]["id"]
    if served != client.settings.served_model_name:
        raise SystemExit(
            f"endpoint serves {served!r}, settings expect {client.settings.served_model_name!r}"
        )
    return served


def synthetic_passages(golden, seed: str, tokens: int) -> list[str]:
    """Stand-in for retrieved knowledge-base passages, for load tests only (D9 measures real
    retrieval). Text differs per cluster so the engine's prefix cache cannot reuse it across
    clusters, as with real retrieval; ~4 characters per token."""
    if tokens <= 0:
        return []
    import random

    rng = random.Random(seed)
    sentences = [r.text for p in golden.projects for r in p.requirements]
    passages, size, k = [], 0, 0
    while size < tokens * 4:
        body = " ".join(rng.choice(sentences) for _ in range(12))
        passages.append(f"[Doc {k + 1}, section {rng.randint(1, 40)}] {body}")
        size += len(passages[-1])
        k += 1
    return passages


async def throughput(client: LLMClient, cfg: dict[str, Any], spec: dict[str, Any], golden) -> list:
    """Load at fixed concurrency levels with generation requests over the reference clusters."""
    model = case_set_model(tuple(cfg["test_types"]), tuple(cfg["priorities"]))
    schema = model.model_json_schema()
    examples = yaml.safe_load((ROOT / cfg["examples_file"]).read_text(encoding="utf-8"))
    stage = cfg["generation"]
    prompts = []
    for p in golden.projects:
        card = ProjectCard(
            p.key,
            p.name,
            p.domain,
            tuple(Method(m["name"], m["criterion"]) for m in cfg["methods"]),
        )
        by_id = {r.id: r for r in p.requirements}
        refs = {r["id"]: r["verification_methods"] for r in p.raw["requirements"]}
        for cluster in p.reference_clusters():
            prompts.append(
                generation_messages(
                    card,
                    [by_id[i] for i in cluster],
                    {i: refs[i] for i in cluster},
                    schema=schema,
                    examples=examples,
                    test_method=cfg["test_method"],
                    types=cfg["test_types"],
                    priorities=cfg["priorities"],
                    passages=synthetic_passages(
                        golden, f"{p.key}/{cluster[0]}", int(spec.get("passage_tokens", 0))
                    ),
                )
            )
    # Warm-up, not counted: the first load level after an engine restart measured about half
    # the throughput of later levels (CUDA graphs and autotune caches still cold).
    warm = int(spec.get("warmup_requests", 8))
    if warm:
        await asyncio.gather(
            *(
                client.chat(
                    prompts[i % len(prompts)],
                    schema=model,
                    max_tokens=256,
                    temperature=stage["temperature"],
                    thinking=stage["thinking"],
                )
                for i in range(warm)
            ),
            return_exceptions=True,
        )
    levels = []
    for c in spec["concurrency"]:
        n = max(int(spec.get("min_requests", 4)), int(spec.get("requests_per_level", 2 * c)), c)
        sem = asyncio.Semaphore(c)

        async def one(i: int, sem: asyncio.Semaphore = sem):
            async with sem:
                try:
                    return await client.chat(
                        prompts[i % len(prompts)],
                        schema=model,
                        max_tokens=stage["max_tokens"],
                        temperature=stage["temperature"],
                        thinking=stage["thinking"],
                    )
                except LLMError as exc:
                    return exc

        started = time.perf_counter()
        results = await asyncio.gather(*(one(i) for i in range(n)))
        wall = time.perf_counter() - started
        ok = [r for r in results if not isinstance(r, Exception)]
        ttfts = sorted(r.metrics.ttft_s for r in ok if r.metrics.ttft_s is not None)
        out_tok = sum(r.metrics.completion_tokens or 0 for r in ok)
        level = {
            "concurrency": c,
            "requests": n,
            "errors": n - len(ok),
            "error_samples": [str(r)[:300] for r in results if isinstance(r, Exception)][:2],
            "schema_valid_rate": round(sum(r.schema_error is None for r in ok) / n, 4),
            "wall_s": round(wall, 2),
            "output_tokens_per_s": round(out_tok / wall, 1),
            "ttft_p50_s": round(statistics.median(ttfts), 3) if ttfts else None,
            "ttft_p95_s": round(ttfts[min(len(ttfts) - 1, int(0.95 * len(ttfts)))], 3)
            if ttfts
            else None,
            "finish_length": sum(r.finish_reason == "length" for r in ok),
        }
        print(f"  eşzamanlılık {c}: {json.dumps(level, ensure_ascii=False)}", flush=True)
        levels.append(level)
    return levels


def layer1_diff(a: dict[str, Any], b: dict[str, Any], prefix: str = "") -> list[str]:
    diffs = []
    skip = {"calls"}
    for k in sorted(set(a) | set(b)):
        if k in skip:
            continue
        va, vb = a.get(k), b.get(k)
        if isinstance(va, dict) and isinstance(vb, dict):
            diffs += layer1_diff(va, vb, f"{prefix}{k}.")
        elif va != vb:
            diffs.append(f"{prefix}{k}: {va} → {vb}")
    return diffs


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("--repeat", type=int)
    ap.add_argument("--out", default=str(ROOT / "results"))
    args = ap.parse_args()

    exp_path = Path(args.config)
    exp, cfg = load_experiment(exp_path)
    server_info = point_at_pod(exp)
    # golden: v0 (default, eval/golden/altin-set-v0.json) or v1 (eval/golden/v1/, paket 1b)
    loader = load_golden_v1 if exp.get("golden", "v0") == "v1" else load_golden
    golden = loader(projects=exp.get("projects"))
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{exp['name']}"
    out_dir = Path(args.out) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {
        "run_id": run_id,
        "experiment": exp,
        "config_file": str(exp_path),
        "pipeline_config": cfg,
        "golden_version": golden.version,
        "server": server_info,
        "model_spec": load_models()[os.environ.get("LLM_MODEL", "")].model_dump()
        if os.environ.get("LLM_MODEL") in load_models()
        else None,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    print(f"koşu {run_id}: {exp.get('question', '')}", flush=True)

    emb_settings = load_embedding_settings()
    embedder = Embedder.from_config() if os.environ.get("EMBEDDING_BASE_URL") else None
    cache = EmbeddingCache(
        EMBED_CACHE,
        emb_settings.model_version,
        (lambda t: _embed(embedder, t)) if embedder else None,
    )
    examples = yaml.safe_load((ROOT / cfg["examples_file"]).read_text(encoding="utf-8"))
    runs: list[dict[str, Any]] = []
    tp_levels = None
    with (out_dir / "outputs.jsonl").open("w", encoding="utf-8") as fh:
        async with LLMClient.from_config() as client:
            meta["served_model"] = await check_served(client)
            meta["engine_settings"] = client.settings.model_dump()
            if exp.get("throughput"):
                print("yük ölçümü", flush=True)
                tp_levels = await throughput(client, cfg, exp["throughput"], golden)
            if exp.get("quality", True):
                repeats = args.repeat or int(exp.get("repeat", 1))
                for rep in range(repeats):
                    if exp.get("scenario"):  # D8 (eval/scenarios.py)
                        pipe = ScenarioPipeline(
                            client, cache, cfg, examples, scenario=exp["scenario"]
                        )
                    else:
                        pipe = Pipeline(client, cache, cfg, examples)
                    meta["prompt_versions"] = pipe.prompt_versions()
                    res = await pipe.run(golden)
                    m = layer1(
                        res.outcomes,
                        golden.refs(),
                        res.calls,
                        res.wall_s,
                        cfg["test_method"],
                        raw_outputs=res.raw_outputs,
                    )
                    m["thresholds"] = passes_thresholds(m, cfg["thresholds"])
                    if res.extra:
                        m["scenario"] = res.extra
                    runs.append(m)
                    for rec in res.records:
                        fh.write(json.dumps({"repeat": rep} | rec, ensure_ascii=False) + "\n")
                    c, a = m["calls"], m["all"]
                    print(
                        f"  tekrar {rep + 1}/{repeats}: kapsama {a['coverage_rate']}, şema "
                        f"{c['schema_valid_rate']}, yöntem {a['method_exact_match']}, ihlal "
                        f"{a.get('no_test_violations_raw', a['no_test_violations'])}, {c['wall_s']} sn, {c['tokens_per_second']} tok/sn, "
                        f"hata {c['errors']}",
                        flush=True,
                    )
    if embedder:
        await embedder.aclose()

    metrics: dict[str, Any] = {"meta": meta, "runs": runs, "throughput": tp_levels}
    if len(runs) > 1:
        metrics["repeat_differences"] = layer1_diff(runs[0], runs[1])
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(out_dir, metrics)
    print(f"sonuç: {out_dir}", flush=True)
    return 0


async def _embed(embedder: Embedder, texts):
    return (await embedder.embed(texts)).vectors


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
