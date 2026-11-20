# ruff: noqa: E501
"""Reference material per requirement for stage 5 (paket 1b). Deterministic.

    python eval/golden/v1/tools/ref_blocks.py OUT_DIR [--ids ETC-001,KDH-004] [--spike]

Writes OUT_DIR/<id>.json: the requirement (as worded) plus the official reference blocks the
reference agent turns into checks. Blocks are verbatim reference text (the answer key), so the
output directory must never be shown to a requirement-wording or test-writing agent.
- ETC: the official test cases (SUBSET-076-5-2 SV30), at most MAX_TC per requirement, fewest
  cited clauses first.
- KDH 800-63-4: the criterion (statement, objective, assessment methods).
- KDH WCAG: the approved ACT rules of the success criterion (Applicability, Expectation, ...).
- KDH Rehber: the audit-table window between the previous and the next measure number; the first
  question of a row can sit before its number in the extracted text, so the window is wider than
  the row and the agent decides which questions belong to the measure.
- KDH 800-53: assessment objectives and methods from the 5.2.0 OSCAL catalog.
- ASVS and system-specific: no official block (Claude writes the checks).
--spike writes the five stage 2 ETC items with the test cases named in their reference_basis.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
V1 = ROOT / "eval/golden/v1"
CACHE = ROOT / "eval/corpus/cache"
ACT = ROOT / "eval/corpus/kdh/snapshots/act-rules"
MAX_TC = 3


def etc_tc(tc_id: str) -> str:
    feat, no = tc_id.split("/TC")
    f = next((CACHE / "etc/text/SUBSET-076-5-2").glob(f"*-{feat}_v400_SV30.txt"))
    text = f.read_text(encoding="utf-8")
    # a test case starts at a line "Test case N"; page headers may sit between it and IDENTIFICATION
    parts = re.split(r"\n(?=Test case \d+\s*\n)", text)
    for p in parts:
        if re.match(rf"Test case {no}\s*\n", p) and "IDENTIFICATION" in p[:2000]:
            return p.strip()
    raise KeyError(tc_id)


def _walk(node, fn):
    if isinstance(node, dict):
        fn(node)
        for v in node.values():
            _walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            _walk(v, fn)


def _prose(parts: list[dict], depth: int = 0) -> list[str]:
    out = []
    for p in parts:
        label = p.get("name", "")
        methods = [q["value"] for q in p.get("props", []) if q.get("name") == "method"]
        head = f"{'  ' * depth}[{label}{' ' + '/'.join(methods) if methods else ''}] "
        if p.get("prose"):
            out.append(head + p["prose"])
        elif methods:
            out.append(head)
        out += _prose(p.get("parts", []), depth + 1)
    return out


def nist63_block(ref: str) -> str:
    cat = json.loads((CACHE / "kdh/text/NIST-800-63-4-CC.txt").read_text(encoding="utf-8"))
    found = []
    _walk(cat, lambda n: found.append(n) if n.get("id") == ref and "parts" in n else None)
    c = found[0]
    return f"{ref}: {c.get('title', '')}\n" + "\n".join(_prose(c["parts"]))


def nist53_block(control: str) -> str:
    cat = json.loads((CACHE / "kdh/text/NIST-SP-800-53r5.txt").read_text(encoding="utf-8"))
    found = []
    _walk(
        cat, lambda n: found.append(n) if n.get("id") == control.lower() and "parts" in n else None
    )
    c = found[0]
    keep = [
        p
        for p in c["parts"]
        if p["name"] in ("statement", "assessment-objective", "assessment-method")
    ]
    params = {
        p["id"]: p.get("label") or p.get("guidelines", [{}])[0].get("prose", "")
        for p in c.get("params", [])
    }
    text = "\n".join(_prose(keep))
    text = re.sub(
        r"\{\{ insert: param, ([\w.-]+) \}\}",
        lambda m: f"[{params.get(m.group(1), m.group(1))}]",
        text,
    )
    return f"{control.upper()}: {c.get('title', '')}\n" + text


def act_block(rule: str) -> str:
    text = (ACT / f"{rule}.md").read_text(encoding="utf-8")
    body = text.split("\n---", 1)[1] if "\n---" in text else text
    return body.split("## Implementations")[0].strip()


def rehber_block(no: str) -> str:
    lines = (CACHE / "kdh/text/SGB-REHBER-1.1.txt").read_text(encoding="utf-8").splitlines()
    nums = [i for i, line in enumerate(lines) if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", line.strip())]
    # the audit-table occurrence is the last one (the measure table comes first)
    hits = [i for i in nums if lines[i].strip() == no]
    i = hits[-1]
    prev = max([j for j in nums if j < i] or [i - 40])
    after = [j for j in nums if j > i] or [i + 60]
    # where row numbers are stacked (3.2.10.1-3.2.10.4), the questions of a row sit several
    # numbers further down: widen the window until it holds questions, at most 6 numbers ahead
    nxt = after[0]
    for j in after[:6]:
        nxt = j
        if any(line.rstrip().endswith("?") for line in lines[i:j]):
            break
    return "\n".join(line for line in lines[prev : nxt + 1] if line.strip())


def blocks_for(r: dict) -> list[dict]:
    doc, cands = r["source"]["doc"], r["reference_candidates"]
    if r["id"].startswith("ETC"):
        tcs = [c for c in cands if "/TC" in c][:MAX_TC]
        return [{"doc": "SUBSET-076-5-2", "ref": t, "text": etc_tc(t)} for t in tcs]
    if doc.startswith("NIST-SP-800-63"):
        return [{"doc": "NIST-800-63-4-CC", "ref": c, "text": nist63_block(c)} for c in cands]
    if doc == "W3C-WCAG-2.2":
        return [
            {"doc": "W3C-ACT-RULES", "ref": c, "text": act_block(c.removeprefix("ACT "))}
            for c in cands
        ]
    if doc == "SGB-REHBER-1.1":
        no = cands[0].removeprefix("Rehber Denetim Maddeleri ")
        return [{"doc": "SGB-REHBER-1.1", "ref": no, "text": rehber_block(no)}]
    if doc == "NIST-SP-800-53r5":
        ctrl = cands[0].removeprefix("800-53A ")
        return [{"doc": "NIST-SP-800-53r5", "ref": ctrl, "text": nist53_block(ctrl)}]
    return []


def spike_items() -> list[dict]:
    items = json.loads((V1.parent / "spike2/items.json").read_text(encoding="utf-8"))
    out = []
    for it in items:
        if it["project"] != "ETC":
            continue
        tcs = [f"{f}/TC{n}" for f, n in re.findall(r"Feature (\d+) TC(\d+)", it["reference_basis"])]
        clauses = sorted(set(re.findall(r"\b3\.\d+(?:\.\d+)+\b", it["source"]["section"])))
        out.append(
            {
                "id": it["id"],
                "language": it["language"],
                "text": it["text"],
                "source": {
                    "doc": "SUBSET-026-3",
                    "section": it["source"]["section"],
                    "clauses": clauses,
                },
                "stratum": "core",
                "reference_origin": "official_tagged",
                "reference_candidates": tcs,
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--ids", default="")
    ap.add_argument("--spike", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.spike:
        reqs = spike_items()
    else:
        reqs = [
            r
            for f in sorted(V1.glob("*.json"))
            for r in json.loads(f.read_text(encoding="utf-8"))["requirements"]
        ]
        if args.ids:
            wanted = set(args.ids.split(","))
            reqs = [r for r in reqs if r["id"] in wanted]
    keys = (
        "id",
        "language",
        "text",
        "source",
        "stratum",
        "reference_origin",
        "reference_candidates",
        "verification_methods",
        "note",
    )
    for r in reqs:
        rec = {k: r[k] for k in keys if k in r} | {"reference_blocks": blocks_for(r)}
        (out / f"{r['id']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    print(f"{len(reqs)} files → {out}")


if __name__ == "__main__":
    main()
