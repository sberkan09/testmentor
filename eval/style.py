"""Style agreement with the reference tests (D10, paket 11): an approximation, no expert.

Per run, the generated test cases and the golden v1 reference checks (one reference case per
requirement: its preconditions, one step per check) are reduced to four means: steps per case,
characters per action, characters per expected result, characters of preconditions. The distance
is the mean relative difference |generated - reference| / reference over the four (0 = same shape).

    python -m eval.style results/<run> [results/<run> ...]
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from statistics import mean
from typing import Any

FEATURES = ("steps", "action_chars", "expected_chars", "precondition_chars")


def shape(cases: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    cases = list(cases)
    steps = [s for c in cases for s in c["steps"]]
    if not cases or not steps:
        return dict.fromkeys(FEATURES, 0.0)
    return {
        "steps": mean(len(c["steps"]) for c in cases),
        "action_chars": mean(len(s["action"]) for s in steps),
        "expected_chars": mean(len(s["expected"]) for s in steps),
        "precondition_chars": mean(len(c.get("preconditions") or "") for c in cases),
    }


def reference_cases(project: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"steps": r["reference_checks"], "preconditions": r.get("reference_preconditions") or ""}
        for r in project["requirements"]
        if r.get("reference_checks")
    ]


def distance(gen: Mapping[str, float], ref: Mapping[str, float]) -> float:
    return mean(abs(gen[f] - ref[f]) / ref[f] for f in FEATURES if ref[f])


def run_style(run: Path, golden: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for line in (run / "outputs.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec.get("type") != "project" or rec["project"] not in golden:
            continue
        gen = shape(rec["test_cases"])
        ref = shape(reference_cases(golden[rec["project"]]))
        out[rec["project"]] = {"generated": gen, "reference": ref, "distance": distance(gen, ref)}
    return out


def table(runs: Sequence[Path]) -> str:
    from eval.golden_v1 import load_golden_v1

    golden = {p.key: p.raw for p in load_golden_v1().projects}
    lines = [
        "| koşu | proje | adım/test | eylem karakteri | beklenen karakteri | ön koşul karakteri"
        " | uzaklık |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    refs_done: set[str] = set()
    for run in runs:
        for project, s in sorted(run_style(run, golden).items()):
            if project not in refs_done:
                r = s["reference"]
                lines.append(
                    f"| referans | {project} | {r['steps']:.2f} | {r['action_chars']:.0f}"
                    f" | {r['expected_chars']:.0f} | {r['precondition_chars']:.0f} | 0 |"
                )
                refs_done.add(project)
            g = s["generated"]
            lines.append(
                f"| {run.name} | {project} | {g['steps']:.2f} | {g['action_chars']:.0f}"
                f" | {g['expected_chars']:.0f} | {g['precondition_chars']:.0f}"
                f" | {s['distance']:.3f} |"
            )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", nargs="+", type=Path)
    args = ap.parse_args()
    print(table(args.runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
