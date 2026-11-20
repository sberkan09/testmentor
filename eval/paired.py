"""Paired requirement bootstrap of the check_recall difference between two judged runs.

    uv run python -m eval.paired results/<new> results/<baseline> [--arm A] [--base-arm B]

Reads `judge.jsonl` (or `judge-<arm>.jsonl` for a D8 arm) of both runs, keeps the requirements
scored in both, pools repeats per requirement (mean matched and checks), and resamples the
requirements with replacement (4.000 samples, seed 0). Prints new, baseline, difference and the
95% interval. Used for the paket 3 bitti criterion (regression) and the D7 / D8 comparisons.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def load(run: Path, arm: str | None = None) -> dict[str, tuple[float, float]]:
    name = "judge.jsonl" if arm is None else f"judge-{arm}.jsonl"
    by: dict[str, list[float]] = {}
    for line in (run / name).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["unscored"]:
            continue
        m, c, n = by.get(r["requirement"], [0.0, 0.0, 0])
        by[r["requirement"]] = [m + r["matched"], c + r["checks"], n + 1]
    return {k: (m / n, c / n) for k, (m, c, n) in by.items()}


def paired(
    new: dict[str, tuple[float, float]],
    base: dict[str, tuple[float, float]],
    samples: int = 4000,
    seed: int = 0,
) -> dict[str, float]:
    ids = sorted(set(new) & set(base))
    nm, nc = (np.array([new[i][k] for i in ids]) for k in (0, 1))
    bm, bc = (np.array([base[i][k] for i in ids]) for k in (0, 1))
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(samples):
        k = rng.integers(0, len(ids), len(ids))
        diffs.append(nm[k].sum() / nc[k].sum() - bm[k].sum() / bc[k].sum())
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {
        "requirements": len(ids),
        "new": round(float(nm.sum() / nc.sum()), 4),
        "baseline": round(float(bm.sum() / bc.sum()), 4),
        "difference": round(float(nm.sum() / nc.sum() - bm.sum() / bc.sum()), 4),
        "low": round(float(lo), 4),
        "high": round(float(hi), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("new")
    ap.add_argument("baseline")
    ap.add_argument("--arm", help="D8 arm of the new run (judge-<arm>.jsonl)")
    ap.add_argument("--base-arm", help="D8 arm of the baseline run")
    args = ap.parse_args()
    out = paired(load(Path(args.new), args.arm), load(Path(args.baseline), args.base_arm))
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
