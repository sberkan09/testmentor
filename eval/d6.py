"""D6: embedding model and clustering method (paket 3; no pod, no model call).

    uv run --group d6 python -m eval.d6 [--embed]

`--embed` computes the vectors of the alternative models on CPU (sentence-transformers, weights
from the models' official organisations) into eval/cache/d6/; without it the cached vectors are
used. BGE-M3 also has the GPU vectors of paket 1 (eval/cache/embeddings.json); the CPU vectors
are checked to give the same clusters.

Reference: the golden set's reference clusters (source document sections; for v1 the ETC SRS
sections and KDH standard fields), a proxy for an expert's grouping. Per project and setting:
- ARI against the reference;
- moves: requirements minus the members shared under the best one-to-one matching of predicted
  and reference clusters (the fewest requirements a user must move to reach the reference),
  reported also as a rate of the project's requirements;
- the number of clusters (reference in brackets).
The setting is chosen on v1 (mean move rate, then ARI); leave-one-out over the two v1 projects
shows how well the choice carries over; v0 (8 requirements per project) is shown separately.
Clustering goes through `core.stages.clustering.cut`, the production code.

Writes results/d6/metrics.json and docs/deneyler/D6.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import adjusted_rand_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.settings import ClusteringSettings  # noqa: E402
from core.stages.clustering import cut  # noqa: E402
from eval.golden import GoldenProject, load_golden  # noqa: E402
from eval.golden_v1 import load_golden_v1  # noqa: E402

CACHE = ROOT / "eval" / "cache" / "d6"
GPU_CACHE = ROOT / "eval" / "cache" / "embeddings.json"
OUT = ROOT / "results" / "d6"
REPORT = ROOT / "docs" / "deneyler" / "D6.md"

MODELS: dict[str, dict[str, Any]] = {
    # name → repo id (official organisation) and the text prefix its model card asks for
    "bge-m3": {"repo": "BAAI/bge-m3", "prefix": ""},
    "e5-large": {"repo": "intfloat/multilingual-e5-large", "prefix": "query: "},
    "qwen3-emb-0.6b": {"repo": "Qwen/Qwen3-Embedding-0.6B", "prefix": ""},
}
WORKING = ("bge-m3", "agglomerative", "average", 0.35)
# 0.05 … 0.60; the plan's grid started at 0.20, but e5's cosine distances are compressed (one
# cluster everywhere above 0.20), so the lower end is added for every model.
THRESHOLDS = [round(0.05 + 0.05 * i, 2) for i in range(12)]
HDBSCAN_SIZES = [2, 3, 5]


def _key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


def embed_cpu(model: str, texts: Sequence[str]) -> dict[str, list[float]]:
    from sentence_transformers import SentenceTransformer

    spec = MODELS[model]
    st = SentenceTransformer(spec["repo"], device="cpu")
    vecs = st.encode(
        [spec["prefix"] + t for t in texts],
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return {
        _key(model, t): [round(float(x), 6) for x in v] for t, v in zip(texts, vecs, strict=True)
    }


def load_vectors(model: str) -> dict[str, list[float]]:
    path = CACHE / f"{model}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def gpu_vectors(texts: Sequence[str]) -> dict[str, list[float]]:
    """Paket 1 GPU vectors of BGE-M3 (eval.pipeline.EmbeddingCache keys) that exist."""
    data = json.loads(GPU_CACHE.read_text(encoding="utf-8"))
    out = {}
    for t in texts:
        k = hashlib.sha256(f"BAAI/bge-m3\n{t}".encode()).hexdigest()
        if k in data:
            out[_key("bge-m3-gpu", t)] = data[k]
    return out


def moves(pred: Sequence[Sequence[str]], ref: Sequence[Sequence[str]]) -> int:
    """Requirements outside the best one-to-one matching of predicted and reference clusters."""
    n = sum(len(c) for c in ref)
    overlap = np.array([[len(set(p) & set(r)) for r in ref] for p in pred], dtype=float)
    rows, cols = linear_sum_assignment(-overlap)
    return int(n - overlap[rows, cols].sum())


def ari(pred: Sequence[Sequence[str]], ref: Sequence[Sequence[str]]) -> float:
    ids = sorted(i for c in ref for i in c)
    p = {i: k for k, c in enumerate(pred) for i in c}
    r = {i: k for k, c in enumerate(ref) for i in c}
    return float(adjusted_rand_score([r[i] for i in ids], [p[i] for i in ids]))


def settings_grid() -> list[tuple[str, str, float | int, ClusteringSettings]]:
    grid = []
    for linkage in ("average", "complete"):
        for t in THRESHOLDS:
            s = ClusteringSettings(method="agglomerative", linkage=linkage, distance_threshold=t)
            grid.append(("agglomerative", linkage, t, s))
    for size in HDBSCAN_SIZES:
        grid.append(
            ("hdbscan", "-", size, ClusteringSettings(method="hdbscan", min_cluster_size=size))
        )
    return grid


def evaluate(
    projects: Sequence[GoldenProject], vectors: dict[str, list[float]], model_key: str
) -> list[dict[str, Any]]:
    rows = []
    for method, linkage, param, s in settings_grid():
        for p in projects:
            ids = [r.id for r in p.requirements]
            vecs = [vectors[_key(model_key, r.text)] for r in p.requirements]
            pred = cut(ids, vecs, s)
            ref = p.reference_clusters()
            m = moves(pred, ref)
            rows.append(
                {
                    "method": method,
                    "linkage": linkage,
                    "param": param,
                    "project": p.key,
                    "requirements": len(ids),
                    "clusters": len(pred),
                    "reference_clusters": len(ref),
                    "ari": round(ari(pred, ref), 4),
                    "moves": m,
                    "move_rate": round(m / len(ids), 4),
                }
            )
    return rows


def best(rows: Sequence[dict[str, Any]], projects: Sequence[str]) -> tuple[Any, ...]:
    """Setting with the lowest mean move rate over `projects`, then the highest mean ARI."""
    by: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for r in rows:
        if r["project"] in projects:
            by.setdefault((r["model"], r["method"], r["linkage"], r["param"]), []).append(r)
    return min(
        by, key=lambda k: (mean(r["move_rate"] for r in by[k]), -mean(r["ari"] for r in by[k]))
    )


def pick(rows, setting, project):
    model, method, linkage, param = setting
    return next(
        r
        for r in rows
        if (r["model"], r["method"], r["linkage"], r["param"], r["project"])
        == (model, method, linkage, param, project)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--embed", action="store_true", help="compute missing CPU vectors")
    args = ap.parse_args()

    v0, v1 = load_golden(), load_golden_v1()
    projects = [*v1.projects, *v0.projects]
    texts = sorted({r.text for p in projects for r in p.requirements})
    CACHE.mkdir(parents=True, exist_ok=True)
    vectors: dict[str, dict[str, list[float]]] = {}
    for model in MODELS:
        have = load_vectors(model)
        missing = [t for t in texts if _key(model, t) not in have]
        if missing and args.embed:
            print(f"{model}: {len(missing)} metin CPU'da", flush=True)
            have |= embed_cpu(model, missing)
            (CACHE / f"{model}.json").write_text(json.dumps(have, sort_keys=True), encoding="utf-8")
        if all(_key(model, t) in have for t in texts):
            vectors[model] = have
        else:
            print(f"{model}: vektör eksik, atlandı (--embed)", flush=True)
    gpu = gpu_vectors(texts)

    rows: list[dict[str, Any]] = []
    for model, vecs in vectors.items():
        rows += [r | {"model": model} for r in evaluate(projects, vecs, model)]
    covered = [
        p for p in projects if all(_key("bge-m3-gpu", r.text) in gpu for r in p.requirements)
    ]
    gpu_check = None
    if covered:
        keys = {p.key for p in covered}
        gpu_rows = evaluate(covered, gpu, "bge-m3-gpu")
        cpu_rows = [r for r in evaluate(covered, vectors["bge-m3"], "bge-m3")]
        same = sum(
            a["ari"] == b["ari"] and a["clusters"] == b["clusters"]
            for a, b in zip(gpu_rows, cpu_rows, strict=True)
        )
        gpu_check = {
            "projects": sorted(keys),
            "missing_projects": sorted(p.key for p in projects if p.key not in keys),
            "settings_x_projects": len(gpu_rows),
            "identical": same,
        }

    v1_keys = [p.key for p in v1.projects]
    v0_keys = [p.key for p in v0.projects]
    chosen = best(rows, v1_keys)
    # Decision space: BGE-M3 (the production embedding service; another model needs its own
    # serving check, outside paket 3) and agglomerative (the design keeps the tree so the cut
    # level changes without recomputation; HDBSCAN has no such tree).
    feasible = [r for r in rows if r["model"] == "bge-m3" and r["method"] == "agglomerative"]
    decision = best(feasible, v1_keys)
    loo = []
    for held in v1_keys:
        train = [k for k in v1_keys if k != held]
        s = best(feasible, train)
        loo.append(
            {
                "held_out": held,
                "chosen_on": train,
                "setting": s,
                "move_rate": pick(rows, s, held)["move_rate"],
                "working_move_rate": pick(rows, WORKING, held)["move_rate"],
                "best_possible_move_rate": pick(rows, best(rows, [held]), held)["move_rate"],
            }
        )
    best_per_model = {m: best([r for r in rows if r["model"] == m], v1_keys) for m in vectors}
    metrics = {
        "working_assumption": WORKING,
        "chosen_on_v1": chosen,
        "decision_space_best": decision,
        "best_per_model": best_per_model,
        "leave_one_out": loo,
        "gpu_cpu_check": gpu_check,
        "rows": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    REPORT.write_text(render(metrics, v1_keys, v0_keys), encoding="utf-8")
    print(f"genel en iyi (v1): {chosen}; karar uzayında: {decision}; varsayım: {WORKING}")
    return 0


def _row_line(rows, setting, keys) -> str:
    cells = []
    for k in keys:
        r = pick(rows, setting, k)
        cells.append(
            f"{r['ari']:.3f} / {r['moves']} ({r['move_rate']:.0%}) / {r['clusters']} [{r['reference_clusters']}]"
        )
    model, method, linkage, param = setting
    name = f"{model}, {method}" + (
        f" {linkage} {param}" if method == "agglomerative" else f" min {param}"
    )
    return f"| {name} | " + " | ".join(cells) + " |"


DECISION = """## Karar (20 Kasım 2026)

- **Embedding: BGE-M3 kalır.** Alternatiflerin (multilingual-e5-large, Qwen3-Embedding-0.6B) hiçbiri
  v1'de BGE-M3'ün en iyi ayarını geçmiyor; model değişikliği üretim embedding servisinde ayrı
  doğrulama da isterdi.
- **Yöntem: agglomerative kalır.** HDBSCAN (min 2) v1'de en düşük taşımayı veriyor (%45), ama
  tasarımın öbek ağacını (kesim seviyesi yeniden hesaplanmadan değişir, kullanıcı kaydırıcısı)
  sağlamıyor ve v0'da öbeklerin çoğunu tek üyeli bırakıyor (5 projeden 4'ünde 8 öbek).
- **Eşik: 0,35 → 0,30** (`config/pipeline.yaml` `clustering.distance_threshold`, tek satır). v1'in
  iki projesinde hem taşıma (ETC 54 → 45, KDH 70 → 66) hem ARI (0,321 → 0,375; 0,336 → 0,457)
  iyileşiyor. İki eşik eşit derecede basit; ana ölçüt gerçekçi boyuttaki v1'dir.
- Sınırlar: (1) referans uzman öbeklemesi değil belge bölümleri; (2) yalnızca iki v1 projesi:
  birini dışarıda bırakmada ETC'de seçilen eşik KDH'ye taşınıyor (%55, varsayım %58), KDH'de
  seçilen ise 0,05 (KDH referansı 120 gereksinimde 66 öbek, çok parçalı) ve ETC'de kötü (%71);
  (3) v0'da (8'er gereksinim) 0,30 biraz kötü (toplam taşıma 22 → 24). Eşik kullanıcı kaydırıcısıyla
  zaten değişir; bu yalnızca başlangıç kesimidir. Uzman öbeklemesi gelince yeniden ölçülmeli.
"""


def render(m: dict[str, Any], v1_keys: list[str], v0_keys: list[str]) -> str:
    rows = m["rows"]
    W, C = tuple(m["working_assumption"]), tuple(m["chosen_on_v1"])
    D = tuple(m["decision_space_best"])
    head = "| ayar | " + " | ".join(v1_keys) + " |"
    sep = "|" + " --- |" * (len(v1_keys) + 1)
    lines = [
        "# D6: Embedding ve kümeleme",
        "",
        "Koşucu: `uv run --group d6 python -m eval.d6 --embed` (pod yok, 0 USD). Hücre biçimi: "
        "ARI / taşıma (gereksinim payı) / öbek sayısı [referans öbek sayısı].",
        "",
        "Referans uzman öbeklemesi değil, kaynak belge bölümleridir (ETC SRS bölümü, KDH standart "
        "alanı); sonuç bu vekile göre okunmalıdır. Taşıma: kullanıcının referansa ulaşmak için "
        "taşıması gereken en az gereksinim (öbekler arası en iyi birebir eşleşme dışında kalanlar).",
        "",
        DECISION,
        "## Çalışma varsayımı, karar uzayının en iyisi, genel en iyi (v1)",
        "",
        "Karar uzayı: BGE-M3 (üretimdeki embedding servisi) ve agglomerative (tasarım ağacı "
        "tutar, kesim seviyesi yeniden hesaplanmadan değişir; HDBSCAN'de ağaç yok).",
        "",
        head,
        sep,
        _row_line(rows, W, v1_keys),
        _row_line(rows, D, v1_keys),
        _row_line(rows, C, v1_keys),
        "",
        "## Model başına en iyi ayar (v1)",
        "",
        head,
        sep,
        *[_row_line(rows, tuple(s), v1_keys) for s in m["best_per_model"].values()],
        "",
        "## Birini dışarıda bırakma (v1, karar uzayında)",
        "",
        "| dışarıdaki | seçilen ayar (diğerinde) | taşıma payı | çalışma varsayımı | o projede en iyi |",
        "| --- | --- | --- | --- | --- |",
        *[
            f"| {x['held_out']} | {', '.join(map(str, x['setting']))} | {x['move_rate']:.0%} | "
            f"{x['working_move_rate']:.0%} | {x['best_possible_move_rate']:.0%} |"
            for x in m["leave_one_out"]
        ],
        "",
        "## v0 (proje başına 8 gereksinim)",
        "",
        "| ayar | " + " | ".join(v0_keys) + " |",
        "|" + " --- |" * (len(v0_keys) + 1),
        _row_line(rows, W, v0_keys),
        _row_line(rows, D, v0_keys),
        _row_line(rows, C, v0_keys),
        "",
    ]
    if m["gpu_cpu_check"]:
        g = m["gpu_cpu_check"]
        lines += [
            f"BGE-M3 CPU vektörleri, paket 1'in GPU vektörleriyle {g['settings_x_projects']} ayar × "
            f"proje bileşiminin {g['identical']}'inde aynı öbeklemeyi verdi (projeler: "
            f"{', '.join(g['projects'])}; GPU önbelleğinde metni eksik olan: "
            f"{', '.join(g['missing_projects']) or 'yok'}).",
            "",
        ]
    lines += [
        "## Eşik taraması (v1, ortalama taşıma payı)",
        "",
        "| model | yöntem | " + " | ".join(str(t) for t in THRESHOLDS) + " |",
        "|" + " --- |" * (len(THRESHOLDS) + 2),
    ]
    for model in m["best_per_model"]:
        for linkage in ("average", "complete"):
            cells = []
            for t in THRESHOLDS:
                rs = [pick(rows, (model, "agglomerative", linkage, t), k) for k in v1_keys]
                cells.append(f"{mean(r['move_rate'] for r in rs):.0%}")
            lines.append(f"| {model} | {linkage} | " + " | ".join(cells) + " |")
        cells = []
        for size in HDBSCAN_SIZES:
            rs = [pick(rows, (model, "hdbscan", "-", size), k) for k in v1_keys]
            cells.append(f"min {size}: {mean(r['move_rate'] for r in rs):.0%}")
        lines.append(
            f"| {model} | hdbscan | "
            + " | ".join(cells)
            + " |"
            + " |" * (len(THRESHOLDS) - len(cells))
        )
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
