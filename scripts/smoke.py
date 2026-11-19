"""Smoke test for the serving stack.

1. Waits until the engine answers.
2. Prefix cache probe: two sequential requests sharing the same prefix (system, project card,
   schema and example) with a different tail. The prefix carries a per-run marker so that the
   first request is always cold. Reports cached tokens and time to first token for both.
3. Sends N (default 16) concurrent schema-bound requests built from one reference cluster of
   the golden set and checks that every answer is error-free and conforms to the schema.

Writes `results/smoke/<timestamp>.json` and exits non-zero when any check fails.
Only the synthetic golden set is used.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.runpod_state import base_urls_from_state  # noqa: E402
from services.llm_client import ChatResult, LLMClient, LLMError  # noqa: E402

GOLDEN = ROOT / "eval" / "golden" / "altin-set-v0.json"


# Output schema used only by the smoke test; the real stage schemas live in core/ (paket 3).
class SmokeStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    no: int
    action: str = Field(min_length=1)
    expected: str = Field(min_length=1)


class SmokeTestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1)
    covers: list[str] = Field(min_length=1)
    type: str
    priority: str
    preconditions: str
    test_inputs: str
    assumptions: str
    steps: list[SmokeStep] = Field(min_length=1)


class SmokeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_cases: list[SmokeTestCase] = Field(min_length=1)


SYSTEM = (
    "You are a senior test engineer. Write test cases for the given requirements. "
    "Every step has its own expected result. Leave preconditions, test inputs and assumptions "
    "empty when they are not needed. Answer only with JSON that matches the schema. "
    "Write in the language of each requirement."
)


def pick_cluster(golden: dict) -> tuple[dict, list[dict], dict]:
    """The largest reference cluster (deterministic: ties broken by project key, name)."""
    best = None
    for project in sorted(golden["projects"], key=lambda p: p["key"]):
        clusters: dict[str, list[dict]] = {}
        for req in project["requirements"]:
            clusters.setdefault(req["reference_cluster"], []).append(req)
        for name in sorted(clusters):
            reqs = sorted(clusters[name], key=lambda r: r["id"])
            if best is None or len(reqs) > len(best[1]):
                best = (project, reqs, name)
    assert best is not None
    project, reqs, _ = best
    ids = {r["id"] for r in reqs}
    example = next(tc for tc in project["test_cases"] if set(tc["covers"]) & ids)
    return project, reqs, example


def build_messages(project: dict, reqs: list[dict], example: dict, marker: str = "") -> list:
    """Prompt order from CLAUDE.md: system, project card, schema and example, (retrieved
    passages: none in smoke), requirements. `marker` is only used by the cache probe."""
    card = f"Project: {project['name']} ({project['key']}). Domain: {project['domain']}."
    schema = json.dumps(SmokeOutput.model_json_schema(), ensure_ascii=False, sort_keys=True)
    ex = json.dumps({"test_cases": [example]}, ensure_ascii=False, sort_keys=True)
    prefix = f"{marker}{SYSTEM}" if marker else SYSTEM
    user = "\n".join(
        f"{r['id']} [{r['language']}]: {r['text']}" for r in sorted(reqs, key=lambda r: r["id"])
    )
    return [
        {"role": "system", "content": prefix},
        {"role": "user", "content": f"{card}\n\nSchema:\n{schema}\n\nExample:\n{ex}"},
        {"role": "user", "content": f"Requirements:\n{user}"},
    ]


async def wait_ready(base_url: str, api_key: str | None, timeout_s: float) -> float:
    started = time.perf_counter()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=10, headers=headers) as http:
        while True:
            try:
                r = await http.get(base_url.rstrip("/") + "/models")
                if r.status_code == 200:
                    return time.perf_counter() - started
            except httpx.HTTPError:
                pass
            if time.perf_counter() - started > timeout_s:
                raise TimeoutError(f"engine not ready after {timeout_s:.0f}s at {base_url}")
            await asyncio.sleep(5)


def summarize(m) -> dict:
    return {
        "prompt_tokens": m.prompt_tokens,
        "completion_tokens": m.completion_tokens,
        "cached_tokens": m.cached_tokens,
        "ttft_s": round(m.ttft_s, 3) if m.ttft_s is not None else None,
        "total_s": round(m.total_s, 3),
    }


async def cache_probe(client: LLMClient, project, reqs, example, args) -> dict:
    marker = f"[run {uuid.uuid4().hex[:12]}] "
    first = await client.chat(
        build_messages(project, reqs[:1], example, marker),
        schema=SmokeOutput,
        max_tokens=args.probe_max_tokens,
        temperature=0.0,
        thinking=False,
    )
    second = await client.chat(
        build_messages(project, reqs[1:2] or reqs[:1], example, marker),
        schema=SmokeOutput,
        max_tokens=args.probe_max_tokens,
        temperature=0.0,
        thinking=False,
    )
    out = {"first": summarize(first.metrics), "second": summarize(second.metrics)}
    t1, t2 = first.metrics.ttft_s, second.metrics.ttft_s
    if t1 and t2:
        out["ttft_drop_pct"] = round(100 * (t1 - t2) / t1, 1)
    return out


async def concurrent_run(client: LLMClient, project, reqs, example, args) -> dict:
    messages = build_messages(project, reqs, example)
    started = time.perf_counter()
    results = await asyncio.gather(
        *(
            client.chat(
                messages,
                schema=SmokeOutput,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                thinking=args.thinking,
            )
            for _ in range(args.concurrency)
        ),
        return_exceptions=True,
    )
    wall = time.perf_counter() - started
    errors = [repr(r) for r in results if isinstance(r, BaseException)]
    ok = [r for r in results if isinstance(r, ChatResult)]
    schema_ok = [r for r in ok if r.schema_error is None]
    covered_ok = [
        r
        for r in schema_ok
        if {rid for tc in r.parsed.test_cases for rid in tc.covers} >= {q["id"] for q in reqs}
    ]
    ttfts = sorted(r.metrics.ttft_s for r in ok if r.metrics.ttft_s is not None)
    out_tokens = sum(r.metrics.completion_tokens or 0 for r in ok)
    in_tokens = sum(r.metrics.prompt_tokens or 0 for r in ok)
    cached = [r.metrics.cached_tokens for r in ok if r.metrics.cached_tokens is not None]
    return {
        "requests": args.concurrency,
        "errors": len(errors),
        "error_samples": errors[:3],
        "schema_valid": len(schema_ok),
        "schema_errors": [r.schema_error[:300] for r in ok if r.schema_error][:3],
        "finish_reasons": sorted({str(r.finish_reason) for r in ok}),
        "all_requirements_covered": len(covered_ok),
        "wall_s": round(wall, 2),
        "output_tokens": out_tokens,
        "prompt_tokens": in_tokens,
        "cached_tokens_total": sum(cached) if cached else None,
        "output_tokens_per_s": round(out_tokens / wall, 1) if wall else None,
        "ttft_p50_s": round(statistics.median(ttfts), 3) if ttfts else None,
        "ttft_max_s": round(ttfts[-1], 3) if ttfts else None,
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(ROOT / "config"))
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--max-tokens", type=int, default=3072)
    ap.add_argument("--probe-max-tokens", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--ready-timeout", type=float, default=900)
    args = ap.parse_args()

    if "LLM_BASE_URL" not in os.environ:
        urls = base_urls_from_state()
        if urls:
            os.environ["LLM_BASE_URL"] = urls["llm"]
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    project, reqs, example = pick_cluster(golden)

    report: dict = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    async with LLMClient.from_config(args.config) as client:
        s = client.settings
        api_key = os.environ.get(s.api_key_env) if s.api_key_env else None
        report |= {
            "engine": s.engine,
            "model": s.model,
            "base_url": s.base_url,
            "cluster": [r["id"] for r in reqs],
            "thinking": args.thinking,
        }
        print(f"engine={s.engine} model={s.model} url={s.base_url} cluster={report['cluster']}")
        report["ready_wait_s"] = round(await wait_ready(s.base_url, api_key, args.ready_timeout), 1)
        try:
            report["cache_probe"] = await cache_probe(client, project, reqs, example, args)
            report["concurrent"] = await concurrent_run(client, project, reqs, example, args)
        except LLMError as exc:
            report["fatal"] = str(exc)

    out_dir = ROOT / "results" / "smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{report['engine']}-{report['model']}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"rapor: {path}")

    c = report.get("concurrent") or {}
    passed = (
        "fatal" not in report
        and c.get("errors") == 0
        and c.get("schema_valid") == c.get("requests")
    )
    print("SMOKE GEÇTİ" if passed else "SMOKE KALDI")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
