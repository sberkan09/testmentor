"""Fix the rubric hold-out split of golden set v1 (paket 1b, stage 4). Deterministic.

    python eval/golden/v1/tools/splits.py

About 20 requirements over both projects are `holdout`: unseen when rubric r1/r2 is confirmed in
stage 5. The rubric is about official procedures, so seats go to official-origin requirements,
stratified by source document (KDH) or stratum (ETC), proportionally with at least one seat per
group while seats remain. Claude-origin requirements get at most one seat, and only core ones;
non_testable at most one. Anything touching the stage 2 spike (same clause, same official test
case, same criterion, ACT rule, Rehber measure or control) is never holdout. Order inside a group
is the SHA-256 of a fixed seed and the id.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

V1 = Path(__file__).resolve().parents[1]
SPIKE = V1.parent / "spike2" / "items.json"
SEED = "paket-1b-holdout-2026-11-20"
PER_PROJECT = 10
PREFIXES = ("ACT ", "Rehber Denetim Maddeleri ", "800-53A ")


def rank(rid: str) -> str:
    return hashlib.sha256(f"{SEED}:{rid}".encode()).hexdigest()


def norm(token: str) -> str:
    for p in PREFIXES:
        token = token.removeprefix(p)
    return re.sub(r"^([A-Z]{2})-0*(\d+)$", r"\1-\2", token.strip())


def spike_tokens() -> set[str]:
    out: set[str] = set()
    for it in json.loads(SPIKE.read_text(encoding="utf-8")):
        basis, section = it["reference_basis"], it["source"]["section"]
        out |= {f"{f}/TC{n}" for f, n in re.findall(r"Feature (\d+) TC(\d+)", basis)}
        out |= set(re.findall(r"\b3\.\d+(?:\.\d+)+\b", section))
        if m := re.search(r"Based on: ([^)]*\)?[^;]*)", basis):
            out |= set(re.findall(r"\b3\.\d+(?:\.\d+)+\b", m.group(1)))
        out |= {norm(t) for t in re.findall(r"\b[A-Z]{2,5}-\d+\b", basis)}
        out |= set(re.findall(r"ACT rule (\w{6})", basis))
        out |= {f"SC {s}" for s in re.findall(r"SC ([\d.]+\d)", section)}
        out |= set(re.findall(r"tedbir (\d+\.\d+\.\d+\.\d+)", basis))
    return out


def tokens(r: dict) -> set[str]:
    out = {norm(c) for c in r["reference_candidates"]} | set(r["source"]["clauses"])
    out.add(r["source"]["section"])
    if r["source"]["doc"] == "W3C-WCAG-2.2":
        out.add(f"SC {r['source']['section'].removeprefix('SC ').strip()}")
    return out


def choose(reqs: list[dict], n: int, spike: set[str]) -> set[str]:
    eligible = [r for r in reqs if not tokens(r) & spike]
    official = [r for r in eligible if r["reference_origin"] != "claude"]
    claude = sorted(
        (r for r in eligible if r["reference_origin"] == "claude" and r["stratum"] == "core"),
        key=lambda r: rank(r["id"]),
    )
    seats = n - (1 if claude else 0)
    groups: dict[str, list[dict]] = {}
    for r in official:
        key = r["stratum"] if r["stratum"] != "core" else r["source"]["doc"]
        groups.setdefault(key, []).append(r)
    for g in groups.values():
        g.sort(key=lambda r: rank(r["id"]))
    quota = {k: max(1, round(seats * len(v) / len(official))) for k, v in groups.items()}
    quota = {
        k: (min(q, 1) if k == "non_testable" else min(q, len(groups[k]))) for k, q in quota.items()
    }
    while sum(quota.values()) > seats:
        quota[max(quota, key=lambda k: (quota[k], k))] -= 1
    while sum(quota.values()) < seats:  # rounding left seats: give them to the largest groups
        k = max(
            (k for k in groups if k != "non_testable" and quota[k] < len(groups[k])),
            key=lambda k: (len(groups[k]) / (quota[k] + 1), k),
        )
        quota[k] += 1
    chosen = {r["id"] for k, g in groups.items() for r in g[: quota[k]]}
    if claude:
        chosen.add(claude[0]["id"])
    return chosen


def main() -> None:
    spike = spike_tokens()
    for path in sorted(V1.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        held = choose(data["requirements"], PER_PROJECT, spike)
        excluded = [r["id"] for r in data["requirements"] if tokens(r) & spike]
        for r in data["requirements"]:
            r["split"] = "holdout" if r["id"] in held else "dev"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(path.name, "holdout", sorted(held), "spike-excluded", excluded)


if __name__ == "__main__":
    main()
