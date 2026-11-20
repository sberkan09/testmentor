# ruff: noqa: E501
"""Confirm or retire rubric r2 on the hold-out requirements of golden set v1 (paket 1b, stage 5).

    PYTHONPATH=. python eval/golden/v1/tools/rubric_holdout.py results/<run> [results/<run> ...]

r2 was written while looking at the stage 2 spike items, so it may only be adopted if it behaves
the same way on requirements nobody looked at. For every run, the hold-out requirements are judged
with r1 and r2 (same model, same cache as eval.judge) and recall is printed for all checks and for
checks that need documents. Writes results/<run>/rubric_holdout.json.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from core.hashing import input_hash
from eval.golden_v1 import load_golden_v1
from eval.judge import RUBRICS, Verdict, judge_prompt, load_projects, reference_checks
from services.judge_client import JudgeClient, JudgeSettings

ROOT = Path(__file__).resolve().parents[4]


async def main(runs: list[str]) -> None:
    golden = load_golden_v1()
    raw = {r["id"]: r for p in golden.projects for r in p.raw["requirements"]}
    checks = reference_checks(golden)
    held = sorted(i for i in checks if raw[i]["split"] == "holdout")
    client = JudgeClient(JudgeSettings.load(ROOT / "config"))
    s = client.settings
    try:
        for run in runs:
            projects = load_projects(Path(run))[0]
            out: dict[str, dict] = {}
            for rubric in ("r1", "r2"):
                text = RUBRICS[rubric]

                async def one(
                    rid: str, text=text, rubric=rubric, projects=projects
                ) -> tuple[str, list[bool]]:
                    proj = projects[rid.split("-")[0]]
                    tests = [t for t in proj["test_cases"] if rid in t["covers"]]
                    user = judge_prompt(raw[rid], checks[rid], tests)
                    h = input_hash(
                        inputs=[text, user],
                        prompt_version=rubric,
                        model=s.model,
                        params={"effort": s.effort},
                    )
                    path = ROOT / s.cache_dir / f"{h}.json"
                    if path.exists():
                        v = json.loads(path.read_text(encoding="utf-8"))
                    else:
                        reply = await client.judge(text, user, Verdict)
                        v = reply.parsed.model_dump() if reply.parsed else {"checks": []}
                        path.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
                    m = {c["no"] for c in v["checks"] if c["matched"]}
                    return rid, [(k in m) for k in range(1, len(checks[rid]) + 1)]

                got = dict(await asyncio.gather(*(one(r) for r in held)))
                allc = [
                    (ok, c["needs_documents"])
                    for r in held
                    for ok, c in zip(got[r], checks[r], strict=True)
                ]
                nd = [ok for ok, need in allc if need]
                out[rubric] = {
                    "recall": round(sum(ok for ok, _ in allc) / len(allc), 3),
                    "recall_needs_documents": round(sum(nd) / len(nd), 3) if nd else None,
                    "checks": len(allc),
                    "checks_needs_documents": len(nd),
                }
            (Path(run) / "rubric_holdout.json").write_text(
                json.dumps(out, indent=2), encoding="utf-8"
            )
            print(Path(run).name, out)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
