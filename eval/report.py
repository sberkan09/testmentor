"""report.md for one run: metrics in separate columns, no single total score."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _fmt(v: Any) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _req_table(m: dict[str, Any]) -> list[str]:
    cols = [
        "requirements",
        "coverage_rate",
        "coverage_rate_before_repair",
        "no_test_violations",
        "step_structure_rate",
        "test_cases",
        "method_exact_match",
        "method_jaccard",
    ]
    rows = (
        [("tümü", m["all"])]
        + [(k, v) for k, v in m["by_language"].items()]
        + [("tuzak", m["traps"])]
    )
    out = ["| küme | " + " | ".join(cols) + " |", "|" + " --- |" * (len(cols) + 1)]
    out += [f"| {name} | " + " | ".join(_fmt(r.get(c)) for c in cols) + " |" for name, r in rows]
    return out


def render(metrics: dict[str, Any]) -> str:
    meta = metrics["meta"]
    exp = meta["experiment"]
    lines = [
        f"# {exp['name']}",
        "",
        f"- Soru: {exp.get('question', '')}",
        f"- Değişken: {exp.get('variable', '')}",
        f"- Koşu: `{meta['run_id']}`, ayar `{meta['config_file']}`, şablon `{meta['template_version']}`, "
        f"altın set `{meta['golden_version']}`",
        f"- Sunucu: {meta['server'].get('engine')} / {meta['server'].get('model')} "
        f"(sunulan ad `{meta.get('served_model')}`, pod `{meta['server'].get('pod')}`)",
        "- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.",
        "",
    ]
    if metrics.get("throughput"):
        cols = [
            "concurrency",
            "requests",
            "errors",
            "schema_valid_rate",
            "output_tokens_per_s",
            "ttft_p50_s",
            "ttft_p95_s",
            "wall_s",
            "finish_length",
        ]
        lines += ["## Yük ölçümü", "", "| " + " | ".join(cols) + " |", "|" + " --- |" * len(cols)]
        lines += [
            "| " + " | ".join(_fmt(level.get(c)) for c in cols) + " |"
            for level in metrics["throughput"]
        ]
        lines.append("")
    for i, m in enumerate(metrics.get("runs") or [], start=1):
        c = m["calls"]
        lines += [f"## Kalite koşusu {i}", ""]
        lines += _req_table(m)
        lines += [
            "",
            f"- Öbek uyumu (ARI): {_fmt(m['cluster_ari'])}",
            f"- Çağrı: {c['calls']}, hata {c['errors']}, şema geçerliliği {_fmt(c['schema_valid_rate'])} "
            f"(üretim {_fmt(c['schema_valid_rate_generation'])})",
            f"- Süre {c['wall_s']} sn, öbek başına {_fmt(c['seconds_per_cluster'])} sn, "
            f"{_fmt(c['tokens_per_second'])} çıktı token/sn, toplam {c['tokens_total']} token, "
            f"önek cache isabeti {_fmt(c['prefix_cache_hit_rate'])}",
            "- Katman 1 eşikleri: "
            + ", ".join(f"{k} {'✓' if v else '✗'}" for k, v in m["thresholds"].items()),
            "",
        ]
    if "repeat_differences" in metrics:
        diffs = metrics["repeat_differences"]
        lines += ["## Tekrar karşılaştırması (katman 1)", ""]
        lines += [f"- {d}" for d in diffs] if diffs else ["- Fark yok."]
        lines.append("")
    if metrics.get("judge"):
        j = metrics["judge"]
        lines += ["## Hakem (katman 2)", "", f"- check_recall: {_fmt(j.get('check_recall'))}"]
        for k, v in (j.get("by_language") or {}).items():
            lines.append(f"- {k}: {_fmt(v)}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_report(out_dir: Path, metrics: dict[str, Any]) -> None:
    (out_dir / "report.md").write_text(render(metrics), encoding="utf-8")
