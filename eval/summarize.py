"""Experiment reports: `python -m eval.summarize` → docs/deneyler/<D>.md

Collects the latest run of every experiment under results/ and writes one comparison table per
experiment group (D1, D2, ...). Metrics stay in separate columns; there is no total score.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GROUPS = {
    "D1": "Sunum motoru",
    "D2": "Model",
    "D3": "Düşünme modu ve örnekleme",
    "D4": "Ağırlık hassasiyeti",
    "D5": "Eşzamanlılık ve bağlam",
    "D12": "Önek ısıtma",
}


def latest_runs(results: Path) -> dict[str, dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for d in sorted(results.glob("*/metrics.json")):
        m = json.loads(d.read_text(encoding="utf-8"))
        if "meta" not in m:  # not an eval.run result (e.g. results/d6, eval/d6.py)
            continue
        name = m["meta"]["experiment"]["name"]
        m["_dir"] = str(d.parent.relative_to(ROOT))
        runs[name] = m  # sorted by run id (timestamp) → last wins
    return runs


def _f(v: Any) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.3g}" if abs(v) < 1000 else f"{v:.0f}"
    return str(v)


def quality_rows(runs: dict[str, dict[str, Any]], names: list[str]) -> list[str]:
    cols = [
        ("kapsama", lambda r, j: r["all"]["coverage_rate"]),
        ("onarım öncesi", lambda r, j: r["all"]["coverage_rate_before_repair"]),
        ("ihlal", lambda r, j: r["all"]["no_test_violations"]),
        ("adım yapısı", lambda r, j: r["all"]["step_structure_rate"]),
        ("test sayısı", lambda r, j: r["all"]["test_cases"]),
        ("yöntem tam", lambda r, j: r["all"]["method_exact_match"]),
        (
            "yöntem tr/en",
            lambda r, j: (
                f"{_f(r['by_language']['tr']['method_exact_match'])} / "
                f"{_f(r['by_language']['en']['method_exact_match'])}"
            ),
        ),
        ("şema", lambda r, j: r["calls"]["schema_valid_rate"]),
        ("hata", lambda r, j: r["calls"]["errors"]),
        ("süre sn", lambda r, j: r["calls"]["wall_s"]),
        ("tok/sn", lambda r, j: r["calls"]["tokens_per_second"]),
        ("önek isabeti", lambda r, j: r["calls"]["prefix_cache_hit_rate"]),
        (
            "eşikler",
            lambda r, j: (
                "✓"
                if all(r["thresholds"].values())
                else "✗ " + ",".join(k for k, v in r["thresholds"].items() if not v)
            ),
        ),
        ("check_recall", lambda r, j: (j or {}).get("check_recall")),
        (
            "recall tr/en",
            lambda r, j: (
                " / ".join(_f(v) for v in ((j or {}).get("by_language") or {}).values())
                if j
                else None
            ),
        ),
    ]
    out = ["| deney | " + " | ".join(c for c, _ in cols) + " |", "|" + " --- |" * (len(cols) + 1)]
    for n in names:
        m = runs.get(n)
        if not m or not m.get("runs"):
            continue
        for i, r in enumerate(m["runs"]):
            label = n if len(m["runs"]) == 1 else f"{n} #{i + 1}"
            judge = m.get("judge") if i == 0 else None
            out.append(f"| {label} | " + " | ".join(_f(fn(r, judge)) for _, fn in cols) + " |")
    return out


def throughput_rows(runs: dict[str, dict[str, Any]], names: list[str]) -> list[str]:
    cols = [
        "concurrency",
        "requests",
        "errors",
        "schema_valid_rate",
        "output_tokens_per_s",
        "ttft_p50_s",
        "ttft_p95_s",
        "finish_length",
    ]
    out = ["| deney | " + " | ".join(cols) + " |", "|" + " --- |" * (len(cols) + 1)]
    for n in names:
        for level in (runs.get(n) or {}).get("throughput") or []:
            out.append(f"| {n} | " + " | ".join(_f(level.get(c)) for c in cols) + " |")
    return out


def write_group(code: str, runs: dict[str, dict[str, Any]], out_dir: Path) -> Path | None:
    prefix = code.lower() + "-"
    names = sorted(n for n in runs if n.startswith(prefix))
    if not names:
        return None
    lines = [
        f"# {code}: {GROUPS[code]}",
        "",
        "Otomatik üretildi: `python -m eval.summarize`. "
        "Altın set sentetiktir (v0.1); sonuçlar gerçek projeler için kesin sayılmaz.",
        "",
    ]
    for n in names:
        m = runs[n]
        e = m["meta"]["experiment"]
        lines.append(
            f"- `{n}`: {e.get('question', '')} Koşu: [`{m['_dir']}`](../../{m['_dir']}/report.md)"
        )
    if any(runs[n].get("throughput") for n in names):
        lines += ["", "## Yük ölçümü", ""] + throughput_rows(runs, names)
    if any(runs[n].get("runs") for n in names):
        lines += ["", "## Kalite (katman 1; katman 2 hakem sütunları hakem koşunca dolar)", ""]
        lines += quality_rows(runs, names)
    diffs = {n: runs[n]["repeat_differences"] for n in names if "repeat_differences" in runs[n]}
    if diffs:
        lines += ["", "## Tekrarlanabilirlik (aynı ayarla iki koşu, katman 1)", ""]
        for n, d in diffs.items():
            lines.append(f"- `{n}`: " + ("fark yok" if not d else "; ".join(d)))
    path = out_dir / f"{code}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    runs = latest_runs(ROOT / "results")
    out_dir = ROOT / "docs" / "deneyler"
    out_dir.mkdir(parents=True, exist_ok=True)
    for code in GROUPS:
        if p := write_group(code, runs, out_dir):
            print(p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
