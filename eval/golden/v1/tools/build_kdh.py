# ruff: noqa: E501
"""Assemble eval/golden/v1/kdh.json from the worded requirements and the candidate pools.

    python eval/golden/v1/tools/build_kdh.py eval/golden/v1/tools/kdh_worded.json

The wording agents saw only standard texts and the system documents; reference ids, methods and
splits are added here from the reference side.
- reference_origin: official for 800-63-4 criteria, WCAG (ACT rules), Rehber (audit tables) and
  800-53 (800-53A); claude for ASVS and system-specific requirements.
- verification_methods: from the official method labels. 800-63-4 and 800-53A: TEST → Test,
  EXAMINE and INTERVIEW → İnceleme. Rehber: Sızma Testi and Güvenlik Denetimi → Test, Mülakat,
  Gözden Geçirme and Kaynak Kod Analizi → İnceleme. WCAG with ACT rules: Test. ASVS: İnceleme when
  the statement is about documentation, otherwise Test. System-specific: Test.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TOOLS = ROOT / "eval/golden/v1/tools"
TEXT = ROOT / "eval/corpus/cache/kdh/text"
OUT = ROOT / "eval/golden/v1/kdh.json"
POOL_ORDER = ["nist63", "asvs", "wcag", "rehber", "nist53", "system"]
REHBER_MAP = {
    "Sızma Testi": "Test",
    "Güvenlik Denetimi": "Test",
    "Mülakat": "İnceleme",
    "Gözden Geçirme": "İnceleme",
    "Kaynak Kod Analizi": "İnceleme",
}
NIST_MAP = {"TEST": "Test", "EXAMINE": "İnceleme", "INTERVIEW": "İnceleme"}


def sort_key(ref: str) -> list:
    return [int(x) if x.isdigit() else x for x in re.split(r"[.\-# ]+", ref) if x]


def methods_53a() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for row in (TEXT / "NIST-SP-800-53Ar5.txt").read_text(encoding="utf-8").splitlines():
        c = row.split("\t")
        m = re.match(r"([A-Z]{2})-0*(\d+)$", c[1]) if len(c) > 7 else None
        if m:  # base control rows only (enhancements are AC-02(01) etc.)
            key = f"{m.group(1)}-{m.group(2)}"
            for col, name in ((5, "EXAMINE"), (6, "INTERVIEW"), (7, "TEST")):
                if c[col].strip():
                    out.setdefault(key, set()).add(name)
    return out


def main(worded_path: str) -> None:
    sys.path.insert(0, str(TOOLS))
    import select_kdh  # noqa: PLC0415  (full pools including method labels)

    nist63 = {x["ref"]: x for x in select_kdh.nist63()}
    rehber = {x["ref"]: x for x in select_kdh.rehber()}
    wcag = {x["sc"]: x for x in select_kdh.wcag()}
    asvs = {x["ref"]: x for x in select_kdh.asvs()}
    m53 = methods_53a()
    worded = json.loads(Path(worded_path).read_text(encoding="utf-8"))
    worded.sort(key=lambda w: (POOL_ORDER.index(w["pool"]), sort_key(w["ref"])))
    reqs = []
    for n, w in enumerate(worded, start=1):
        pool, ref = w["pool"], w["ref"]
        if pool == "nist63":
            c = nist63[ref]
            methods = sorted({NIST_MAP[m] for m in c["methods"]}, key=["Test", "İnceleme"].index)
            origin, cands = "official", [ref]
            cluster = f"{c['volume']} {c['section'].split()[0].rsplit('.', 1)[0]} {c['title'].split(' - ')[0]}"[
                :80
            ]
            rationale = f"800-63-4 uygunluk kriteri {ref} yöntemleri: {', '.join(c['methods'])}."
        elif pool == "wcag":
            c = wcag[ref]
            methods, origin = ["Test"], "official"
            cands = [f"ACT {r['id']}" for r in c["act_rules"]]
            cluster = "Erişilebilirlik (WCAG 2.2)"
            rationale = "Başarı ölçütü onaylı ACT kurallarıyla test edilir: Test."
        elif pool == "rehber":
            c = rehber[ref]
            methods = sorted({REHBER_MAP[m] for m in c["methods"]}, key=["Test", "İnceleme"].index)
            origin, cands = "official", [f"Rehber Denetim Maddeleri {ref}"]
            cluster = f"Rehber {'.'.join(ref.split('.')[:3])}"
            rationale = f"Rehber denetim yöntem önerileri: {', '.join(c['methods'])}."
        elif pool == "nist53":
            key = ref.upper()
            ms = m53.get(key, {"TEST"})
            methods = sorted({NIST_MAP[m] for m in ms}, key=["Test", "İnceleme"].index)
            origin, cands = "official", [f"800-53A {key}"]
            cluster = f"NIST 800-53 {key.split('-')[0]}"
            rationale = f"800-53A değerlendirme yöntemleri: {', '.join(sorted(ms))}."
        elif pool == "asvs":
            stmt = asvs[ref]["statement"]
            doc_only = bool(re.search(r"\bdocument", stmt, re.I))
            methods = ["İnceleme"] if doc_only else ["Test"]
            origin, cands = "claude", [ref]
            cluster = f"ASVS {asvs[ref]['chapter']}"
            rationale = "ASVS'de test prosedürü yok; " + (
                "belge gerekliliği: İnceleme."
                if doc_only
                else "davranış çalıştırılarak doğrulanır: Test."
            )
        else:  # system
            methods, origin, cands = ["Test"], "claude", [ref]
            cluster = "VBP tasarım kararları"
            rationale = (
                "Tasarım belgesindeki karara özgü; davranış çalıştırılarak doğrulanır: Test."
            )
        reqs.append(
            {
                "id": f"KDH-{n:03d}",
                "language": w["language"],
                "text": w["text"],
                "source": {
                    "doc": w["source"]["doc"],
                    "section": w["source"]["section"],
                    "clauses": w.get("clauses", []),
                },
                "stratum": w["stratum"],
                "split": "dev",
                "reference_origin": origin,
                "reference_candidates": cands,
                "reference_cluster": cluster,
                "verification_methods": methods,
                "method_rationale": rationale,
                "difficulty": w["difficulty"],
                "note": w.get("note", ""),
            }
        )
    project = {
        "key": "KDH",
        "name": "Vatandaş Başvuru Portalı",
        "domain": "Kamu dijital hizmeti",
        "version": "v1",
        "requirements": reqs,
    }
    OUT.write_text(json.dumps(project, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(reqs)} requirements → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1])
