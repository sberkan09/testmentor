"""Layer 2: judge model. `python -m eval.judge results/<run id> [results/<run id> ...]`

Unit is the requirement. The judge gets the requirement text, the numbered reference checks
(step action and expected result pairs of the reference tests covering it) and the generated
tests covering it, and returns per-check matches, invented content, boundary and ambiguity flags.
Main metric: check_recall = matched checks / all checks. Style is not scored.

Verdicts are cached by input hash under eval/cache/judge/, so the same output is never scored
twice and no GPU is needed: the judge reads results/<run>/outputs.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.hashing import canonical, input_hash  # noqa: E402
from eval.golden import Golden, load_golden  # noqa: E402
from eval.report import write_report  # noqa: E402
from services.judge_client import JudgeClient, JudgeSettings, JudgeUnavailable  # noqa: E402

RUBRIC = """You grade generated test cases against reference checks for one requirement.
A reference check is an action and its expected result taken from a reference test.
For each numbered check decide whether the generated tests contain a step (or a precondition
plus step) that verifies the same behaviour with an equivalent expected result. Wording,
language, order and test boundaries do not matter; the verified behaviour does. Give as evidence
the generated test title and step number, or an empty string when unmatched.
Also list content in the generated tests that the requirement does not state and that is not
written as an assumption (invented), say whether boundary and error cases implied by the
requirement are covered (boundary_ok), and whether ambiguity in the requirement is written down
as an assumption where a value had to be chosen (ambiguity_flagged).
Do not grade style."""


RUBRIC_R2_ADDENDUM = """
Reference checks may come from official test procedures. Such a check can name one concrete
scenario (a specific message, packet, field value or display symbol) and one observation channel
(for example recorder entries, display symbols or interface messages). Count it as matched when a
generated step tests the same behaviour under the same distinguishing condition (for example:
information whose validity direction is opposite to the train orientation is ignored) and states
an equivalent observable outcome, even if it uses another equivalent message or observes the
outcome through another channel. Do not count it when the generated tests miss the distinguishing
condition or the outcome."""

RUBRICS = {"r1": RUBRIC, "r2": RUBRIC + RUBRIC_R2_ADDENDUM}


class CheckVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    no: int
    matched: bool
    evidence: str


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checks: list[CheckVerdict]
    invented: list[str] = Field(default_factory=list)
    boundary_ok: bool
    ambiguity_flagged: bool


def reference_checks(golden: Golden) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for rid, tests in golden.reference_tests().items():
        checks = []
        for tc in sorted(tests, key=lambda t: t["id"]):
            for s in tc["steps"]:
                checks.append({"test": tc["id"], "action": s["action"], "expected": s["expected"]})
        out[rid] = checks
    return out


def judge_prompt(
    req: dict[str, Any], checks: list[dict[str, str]], tests: list[dict[str, Any]]
) -> str:
    lines = [
        f"# Requirement {req['id']} ({req['language']})",
        req["text"],
        "",
        "# Reference checks",
    ]
    lines += [f"[{i}] {c['action']} → {c['expected']}" for i, c in enumerate(checks, start=1)]
    lines += ["", "# Generated tests"]
    shown = [
        {
            k: t.get(k)
            for k in ("title", "type", "preconditions", "test_inputs", "assumptions", "steps")
        }
        for t in tests
    ]
    lines.append(canonical(shown) if shown else "(none)")
    return "\n".join(lines)


def load_projects(run_dir: Path) -> dict[int, dict[str, dict[str, Any]]]:
    """repeat → project → project record."""
    out: dict[int, dict[str, dict[str, Any]]] = {}
    for line in (run_dir / "outputs.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("type") == "project":
            out.setdefault(rec["repeat"], {})[rec["project"]] = rec
    return out


async def judge_run(run_dir: Path, client: JudgeClient, golden: Golden) -> dict[str, Any]:
    s = client.settings
    cache_dir = ROOT / s.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    checks_by_req = reference_checks(golden)
    raw_reqs = {r["id"]: r for p in golden.projects for r in p.raw["requirements"]}
    sem = asyncio.Semaphore(s.concurrency)
    results: list[dict[str, Any]] = []
    stats = {"cached": 0, "called": 0, "refused": 0}

    async def one(rep: int, rid: str, tests: list[dict[str, Any]]) -> None:
        checks = checks_by_req[rid]
        user = judge_prompt(raw_reqs[rid], checks, tests)
        h = input_hash(
            inputs=[RUBRIC, user],
            prompt_version=s.rubric_version,
            model=s.model,
            params={"effort": s.effort},
        )
        path = cache_dir / f"{h}.json"
        if path.exists():
            verdict = json.loads(path.read_text(encoding="utf-8"))
            stats["cached"] += 1
        else:
            async with sem:
                reply = await client.judge(RUBRIC, user, Verdict)
            stats["called"] += 1
            if reply.parsed is None:
                stats["refused"] += 1
                verdict = {"unscored": reply.stop_reason}
            else:
                verdict = reply.parsed.model_dump() | {"usage": reply.usage}
                path.write_text(json.dumps(verdict, ensure_ascii=False), encoding="utf-8")
        matched = {c["no"] for c in verdict.get("checks", []) if c["matched"]}
        results.append(
            {
                "repeat": rep,
                "requirement": rid,
                "language": raw_reqs[rid]["language"],
                "trap": str(raw_reqs[rid].get("note", "")).startswith("Tuzak"),
                "checks": len(checks),
                "matched": len(matched & set(range(1, len(checks) + 1))),
                "invented": len(verdict.get("invented", [])),
                "boundary_ok": verdict.get("boundary_ok"),
                "ambiguity_flagged": verdict.get("ambiguity_flagged"),
                "unscored": verdict.get("unscored"),
                "input_hash": h,
            }
        )

    jobs = []
    for rep, projects in load_projects(run_dir).items():
        for proj in projects.values():
            for rid in sorted(
                r for r in checks_by_req if raw_reqs[r]["id"].startswith(proj["project"] + "-")
            ):
                tests = [t for t in proj["test_cases"] if rid in t["covers"]]
                jobs.append(one(rep, rid, tests))
    await asyncio.gather(*jobs)
    results.sort(key=lambda r: (r["repeat"], r["requirement"]))
    with (run_dir / "judge.jsonl").open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return summarize(results) | {
        "rubric_version": s.rubric_version,
        "model": s.model,
        "stats": stats,
    }


def _recall(rows: list[dict[str, Any]]) -> float | None:
    rows = [r for r in rows if not r["unscored"]]
    total = sum(r["checks"] for r in rows)
    return round(sum(r["matched"] for r in rows) / total, 4) if total else None


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    first = [r for r in results if r["repeat"] == 0] or results
    langs = sorted({r["language"] for r in first})
    scored = [r for r in first if not r["unscored"]]
    return {
        "check_recall": _recall(first),
        "by_language": {
            lang: _recall([r for r in first if r["language"] == lang]) for lang in langs
        },
        "traps": _recall([r for r in first if r["trap"]]),
        "invented_per_requirement": round(mean(r["invented"] for r in scored), 3)
        if scored
        else None,
        "boundary_ok_rate": round(mean(bool(r["boundary_ok"]) for r in scored), 4)
        if scored
        else None,
        "ambiguity_flagged_rate": round(mean(bool(r["ambiguity_flagged"]) for r in scored), 4)
        if scored
        else None,
        "unscored": sum(bool(r["unscored"]) for r in first),
        "by_repeat": {
            rep: _recall([r for r in results if r["repeat"] == rep])
            for rep in sorted({r["repeat"] for r in results})
        },
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", nargs="+")
    args = ap.parse_args()
    try:
        client = JudgeClient(JudgeSettings.load(ROOT / "config"))
    except JudgeUnavailable as exc:
        print(f"hakem koşamadı: {exc}")
        return 2
    golden = load_golden()
    try:
        for run in args.runs:
            run_dir = Path(run)
            summary = await judge_run(run_dir, client, golden)
            metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
            metrics["judge"] = summary
            (run_dir / "metrics.json").write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            write_report(run_dir, metrics)
            print(
                f"{run_dir.name}: check_recall {summary['check_recall']} {summary['by_language']} "
                f"({summary['stats']})"
            )
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
