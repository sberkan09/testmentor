# ruff: noqa: E501
"""Assemble eval/golden/v1/etc.json from the worded requirements and the candidate pool.

    python eval/golden/v1/tools/build_etc.py eval/golden/v1/tools/etc_worded.json

The wording agent saw only the SRS text; test case ids, methods and splits are added here.
- reference_origin: official_tagged when the clause has official test cases (steps are tagged to
  clauses in stage 5), claude otherwise.
- verification_methods: Test, except SUBSET-076-7 Table 3 rows: partially testable → Test + Analiz,
  not testable → Analiz.
- split: holdout is chosen in tools/splits.py over both projects.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CANDIDATES = ROOT / "eval/golden/v1/tools/etc_candidates.json"
TABLE3 = ROOT / "eval/corpus/etc/probe/table3.txt"
OUT = ROOT / "eval/golden/v1/etc.json"


def table3_partial() -> dict[str, bool]:
    """Clause → partially testable (Yes/No) for Table 3 rows without a sub-item suffix."""
    out = {}
    for line in TABLE3.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s{4,14}(3\.\d+(?:\.\d+)+)(?!\s+\S{1,3}\))\s.*?\b(Yes|No)\s*$", line)
        if m:
            out.setdefault(m.group(1), m.group(2) == "Yes")
    return out


def main(worded_path: str) -> None:
    pool = {c["clause"]: c for c in json.loads(CANDIDATES.read_text(encoding="utf-8"))}
    worded = json.loads(Path(worded_path).read_text(encoding="utf-8"))
    partial = table3_partial()
    worded.sort(key=lambda w: [int(x) for x in w["clause"].split(".")])
    reqs = []
    for n, w in enumerate(worded, start=1):
        c = pool[w["clause"]]
        tcs = [t["id"] for t in c["test_cases"]]
        if w["stratum"] == "non_testable":
            p = partial.get(w["clause"], True)
            methods = ["Test", "Analiz"] if p else ["Analiz"]
            rationale = (
                f"SUBSET-076-7 Tablo 3'te {'kısmen test edilebilir' if p else 'test edilemez'} olarak listeli; "
                + (
                    "test edilebilen kısım Test, kalanı Analiz."
                    if p
                    else "doğrulama analizle yapılır."
                )
            )
        else:
            methods = ["Test"]
            rationale = (
                "SUBSET-076-7 Tablo 3'te yok ve SUBSET-076-5-2'de resmî test vakası var: Test."
            )
        reqs.append(
            {
                "id": f"ETC-{n:03d}",
                "language": "en",
                "text": w["text"],
                "source": {"doc": "SUBSET-026-3", "section": w["clause"], "clauses": w["clauses"]},
                "stratum": w["stratum"],
                "split": "dev",
                "reference_origin": "official_tagged" if tcs else "claude",
                "reference_candidates": tcs or [f"SUBSET-076-7 Table 3 {w['clause']}"],
                "reference_cluster": "Kontrol katmanı"
                if w["stratum"] == "control"
                else c["heading"],
                "verification_methods": methods,
                "method_rationale": rationale,
                "difficulty": w["difficulty"],
                "note": w.get("note", "") + (" Deneme 2 maddesi: hep dev." if c["spike"] else ""),
            }
        )
    project = {
        "key": "ETC",
        "name": "ERTMS/ETCS araç üstü birimi",
        "domain": "Demiryolu sinyalizasyonu",
        "version": "v1",
        "requirements": reqs,
    }
    OUT.write_text(json.dumps(project, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(reqs)} requirements → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1])
