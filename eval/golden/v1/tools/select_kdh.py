# ruff: noqa: E501
"""Stage 4 candidate pools for KDH (paket 1b). Deterministic; rerun reproduces the pools.

    python eval/golden/v1/tools/select_kdh.py > eval/golden/v1/tools/kdh_candidates.json

Reads the cached corpus (python -m eval.corpus fetch --project kdh --all). Selection may use the
reference documents (which items have a TEST procedure); the pools written here contain only the
standard's own text plus reference ids for stage 5, so the wording agent sees no procedure text.

- nist63: 800-63-4 conformance criteria with a TEST method (statement = the SHALL text of the
  guideline; objective and methods are not copied).
- wcag: WCAG 2.2 success criteria tested by at least one approved ACT rule.
- rehber: Rehber measures whose audit method suggestions include Sızma Testi or Güvenlik Denetimi;
  the measure definition comes from the writer view (audit tables stripped).
- nist53: 800-53 controls in application-relevant families with a TEST row in 800-53A; control
  statement from the writer view of the OSCAL catalog.
- asvs: ASVS 5.0.0 requirements (no official procedure; Claude writes references).
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TEXT = ROOT / "eval/corpus/cache/kdh/text"
ACT = ROOT / "eval/corpus/kdh/snapshots/act-rules"
FAMILIES_53 = ("AC", "IA", "AU", "SC", "SI", "CM")
TEST_METHODS = ("Sızma Testi", "Güvenlik Denetimi")


def nist63() -> list[dict]:
    cat = json.loads((TEXT / "NIST-800-63-4-CC.txt").read_text(encoding="utf-8"))["catalog"]
    out = []

    def walk(group, volume):
        for c in group.get("controls", []):
            props = {(p["name"], p.get("class")): p["value"] for p in c.get("props", [])}
            methods = sorted(
                {
                    q["value"]
                    for p in c.get("parts", [])
                    if p["name"] == "assessment-method"
                    for q in p.get("props", [])
                    if q["name"] == "method"
                }
            )
            stmt = " ".join(
                p.get("prose", "") for p in c.get("parts", []) if p["name"] == "statement"
            )
            if "TEST" in methods:
                out.append(
                    {
                        "ref": c["id"],
                        "volume": volume,
                        "section": props.get(("label", "index"), ""),
                        "title": c.get("title", ""),
                        "target": props.get(("marking", "target"), ""),
                        "level": props.get(("marking", "xal-level"), ""),
                        "statement": re.sub(r"\s+", " ", stmt).strip(),
                        "methods": methods,
                    }
                )
            walk(c, volume)
        for g in group.get("groups", []):
            walk(g, g.get("title", volume))

    walk(cat, "")
    return out


def wcag() -> list[dict]:
    scs: dict[str, dict] = {}
    for f in sorted(ACT.glob("*.md")):
        meta = f.read_text(encoding="utf-8").split("\n---", 1)[0]
        name = re.search(r'^\s*name:\s*"?(.*?)"?\s*$', meta, re.M).group(1)
        for handle, num, level in re.findall(
            r"- handle: (.*?)\s*\n\s+num: ([\d.]+)\s*\n\s+level: (\w+)", meta
        ):
            s = scs.setdefault(num, {"sc": num, "handle": handle, "level": level, "act_rules": []})
            s["act_rules"].append({"id": f.stem, "name": name})
    return sorted(scs.values(), key=lambda s: [int(x) for x in s["sc"].split(".")])


def rehber() -> list[dict]:
    full = (TEXT / "SGB-REHBER-1.1.txt").read_text(encoding="utf-8")
    view = (TEXT / "SGB-REHBER-1.1.writer.txt").read_text(encoding="utf-8")
    methods: dict[str, set[str]] = {}
    for block in full.split("\nDenetim Maddeleri\n")[1:]:
        block = re.split(r"\n(?:\d+\.){2,3}\s+\S", block, maxsplit=1)[0]
        parts = re.split(r"\n(\d+\.\d+\.\d+\.\d+)\n", "\n" + block)
        for i in range(1, len(parts), 2):
            chunk = re.sub(r"\s+", " ", parts[i + 1])
            methods[parts[i]] = {
                m
                for m in (*TEST_METHODS, "Mülakat", "Gözden Geçirme", "Kaynak Kod Analizi")
                if m in chunk
            }
    out = []
    for no, ms in sorted(methods.items(), key=lambda kv: [int(x) for x in kv[0].split(".")]):
        if not ms & set(TEST_METHODS):
            continue
        # measure definition in the writer view: the tedbir number line, then name and definition
        m = re.search(
            rf"\n{re.escape(no)}\n(.*?)(?=\n\d+\.\d+\.\d+\.\d+\n|\n(?:\d+\.){{2,3}}\s+\S)",
            view,
            re.S,
        )
        definition = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        out.append({"ref": no, "methods": sorted(ms), "definition": definition[:1500]})
    return out


def nist53() -> list[dict]:
    rows = (TEXT / "NIST-SP-800-53Ar5.txt").read_text(encoding="utf-8").splitlines()
    tested = set()
    for r in rows:
        cells = r.split("\t")
        if len(cells) >= 8 and cells[7].strip() and re.match(r"[A-Z]{2}-\d", cells[1]):
            tested.add(re.match(r"([A-Z]{2})-0*(\d+)", cells[1]).groups())
    cat = json.loads((TEXT / "NIST-SP-800-53r5.writer.txt").read_text(encoding="utf-8"))["catalog"]
    out = []

    def prose(parts):
        return " ".join(
            filter(None, (p.get("prose", "") + " " + prose(p.get("parts", [])) for p in parts))
        )

    for g in cat["groups"]:
        for c in g.get("controls", []):
            fam, num = c["id"].split("-")[0].upper(), c["id"].split("-")[1]
            if fam in FAMILIES_53 and (fam, num) in tested:
                stmt = prose([p for p in c.get("parts", []) if p["name"] == "statement"])
                out.append(
                    {
                        "ref": c["id"].upper(),
                        "title": c["title"],
                        "statement": re.sub(r"\s+", " ", stmt).strip()[:1500],
                    }
                )
    return out


def asvs() -> list[dict]:
    rows = csv.DictReader(io.StringIO((TEXT / "OWASP-ASVS-5.0.0.txt").read_text(encoding="utf-8")))
    return [
        {
            "ref": r["req_id"],
            "chapter": r["chapter_name"],
            "section": r["section_name"],
            "level": r["L"],
            "statement": r["req_description"],
        }
        for r in rows
    ]


def main() -> None:
    pools = {
        "nist63": nist63(),
        "wcag": wcag(),
        "rehber": rehber(),
        "nist53": nist53(),
        "asvs": asvs(),
    }
    print(json.dumps(pools, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
