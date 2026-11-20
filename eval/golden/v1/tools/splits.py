"""Fix the rubric hold-out split of golden set v1 (paket 1b, stage 4). Deterministic.

    python eval/golden/v1/tools/splits.py

About 20 requirements over both projects are `holdout`: unseen when rubric r1/r2 is confirmed in
stage 5. Per project 10, stratified by stratum and reference origin, ordered by SHA-256 of a fixed
seed and the id. Requirements that carry the stage 2 spike clauses ("Deneme 2 maddesi") are never
holdout. Rerunning gives the same split.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

V1 = Path(__file__).resolve().parents[1]
SEED = "paket-1b-holdout-2026-11-20"
PER_PROJECT = 10


def rank(rid: str) -> str:
    return hashlib.sha256(f"{SEED}:{rid}".encode()).hexdigest()


def choose(reqs: list[dict], n: int) -> set[str]:
    eligible = [r for r in reqs if "Deneme 2 maddesi" not in r.get("note", "")]
    strata: dict[tuple, list[dict]] = {}
    for r in eligible:
        strata.setdefault((r["stratum"], r["reference_origin"]), []).append(r)
    for group in strata.values():
        group.sort(key=lambda r: rank(r["id"]))
    total = len(eligible)
    # proportional allocation, at least one per stratum while seats remain
    quota = {k: max(1, round(n * len(v) / total)) for k, v in strata.items()}
    while sum(quota.values()) > n:
        biggest = max(quota, key=lambda k: (quota[k], k))
        quota[biggest] -= 1
    chosen = set()
    for k, group in sorted(strata.items()):
        chosen |= {r["id"] for r in group[: quota[k]]}
    return chosen


def main() -> None:
    for path in sorted(V1.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        held = choose(data["requirements"], PER_PROJECT)
        for r in data["requirements"]:
            r["split"] = "holdout" if r["id"] in held else "dev"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(path.name, sorted(held))


if __name__ == "__main__":
    main()
