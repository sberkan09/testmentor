# ruff: noqa: ASYNC240  (CLI script: blocking file reads are fine here)
"""Stage 2 probe of paket 1b: can rubric r1 match generated tests against official reference
checks, and do the documents make a measurable difference?

    python -m eval.spike2 [--dir eval/golden/spike2]

Inputs in the directory: items.json (requirements, reference checks, support passages) and
generated tests per variant: generated_<variant>.json = {item id: [test cases]}.
Writes results.json and prints recall per variant, project and needs_documents.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.hashing import input_hash  # noqa: E402
from eval.judge import RUBRIC, Verdict, judge_prompt  # noqa: E402
from services.judge_client import JudgeClient, JudgeSettings  # noqa: E402


async def score(client: JudgeClient, item: dict[str, Any], tests: list[dict[str, Any]]) -> dict:
    s = client.settings
    checks = item["reference_checks"]
    user = judge_prompt(item, checks, tests)
    h = input_hash(
        inputs=[RUBRIC, user],
        prompt_version=s.rubric_version,
        model=s.model,
        params={"effort": s.effort},
    )
    path = ROOT / s.cache_dir / f"{h}.json"
    if path.exists():
        verdict = json.loads(path.read_text(encoding="utf-8"))
    else:
        reply = await client.judge(RUBRIC, user, Verdict)
        if reply.parsed is None:
            return {"unscored": reply.stop_reason}
        verdict = reply.parsed.model_dump()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(verdict, ensure_ascii=False), encoding="utf-8")
    matched = {c["no"] for c in verdict["checks"] if c["matched"]} & set(range(1, len(checks) + 1))
    return {
        "checks": len(checks),
        "matched": len(matched),
        "invented": len(verdict["invented"]),
        "evidence": [c for c in verdict["checks"] if c["matched"]],
    }


def recall(rows: list[dict]) -> float | None:
    rows = [r for r in rows if "checks" in r]
    total = sum(r["checks"] for r in rows)
    return round(sum(r["matched"] for r in rows) / total, 3) if total else None


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=str(ROOT / "eval" / "golden" / "spike2"))
    args = ap.parse_args()
    d = Path(args.dir)
    items = json.loads((d / "items.json").read_text(encoding="utf-8"))
    variants = {
        p.stem.removeprefix("generated_"): json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(d.glob("generated_*.json"))
    }
    client = JudgeClient(JudgeSettings.load(ROOT / "config"))
    results: dict[str, dict[str, Any]] = {}
    try:
        for name, generated in variants.items():
            scored = await asyncio.gather(
                *(score(client, it, generated.get(it["id"], [])) for it in items)
            )
            results[name] = {it["id"]: r for it, r in zip(items, scored, strict=True)}
    finally:
        await client.aclose()
    (d / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    by = {it["id"]: it for it in items}
    for name, res in results.items():
        rows = list(res.values())
        print(f"{name}: recall {recall(rows)}")
        for key in ("project", "needs_documents"):
            groups: dict[Any, list] = {}
            for iid, r in res.items():
                groups.setdefault(by[iid][key], []).append(r)
            print("   ", key, {k: recall(v) for k, v in sorted(groups.items(), key=str)})
        print(
            "    madde:", {iid: f"{r.get('matched')}/{r.get('checks')}" for iid, r in res.items()}
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
