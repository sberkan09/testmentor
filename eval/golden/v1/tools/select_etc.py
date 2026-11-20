# ruff: noqa: E501
"""Stage 4 candidate selection for ETC (paket 1b). Deterministic; rerun reproduces the list.

    python eval/golden/v1/tools/select_etc.py > eval/golden/v1/tools/etc_candidates.json

Reads the cached SUBSET-026-3 text (python -m eval.corpus fetch --project etc) and the stage 1
traceability probe (eval/corpus/etc/probe/refs2.json, SUBSET-076-5-2 SV30 "Based on" references).

Candidate (core): a §3.5–3.12 clause with at least one official test case that cites at most 3
base clauses, has an input row and no Use_FT. Candidate (non_testable): a SUBSET-076-7 Table 3 row
in §3.5–3.12. The full clause text (with sub-items and notes) is cut from the SRS text up to the
next clause number. The test case ids are kept for stage 5 and must not be shown to the agent that
words the requirements.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRS = ROOT / "eval/corpus/cache/etc/text/SUBSET-026-3.txt"
REFS = ROOT / "eval/corpus/etc/probe/refs2.json"
TABLE3 = ROOT / "eval/corpus/etc/probe/table3.txt"
SECTIONS = tuple(f"3.{i}" for i in range(5, 13))
MAX_CLAUSES = 3
# clauses of the stage 2 spike items (eval/golden/spike2/items.json): always dev, never holdout
SPIKE = {"3.6.2.2.2", "3.6.3.1.3", "3.6.4.2.2.2", "3.7.3.1", "3.8.2.1.7", "3.8.2.2.2"}

# clause start: number at the left margin, then text starting with a capital (wrapped cross
# references such as "3.8.2.1.1 b) & c) ..." continue in lower case and are not clause starts)
CLAUSE = re.compile(r"^\s{0,6}(3\.(?:[5-9]|1[0-2])(?:\.\d+){1,6})\s+([A-Z•(\"].*)$")
TOC = re.compile(r"^\s*(3\.\d+(?:\.\d+)*)\s+(\S.*?)\s*\.{5,}\s*\d+\s*$")
NOISE = re.compile(
    r"(SUBSET-026-3|System Requirements Specification|Chapter 3|Principles|Page \d+/\d+|^\s*\d+/\d+\s*$|ERA \* UNISIG)",
    re.I,
)


def in_scope(c: str) -> bool:
    return any(c == s or c.startswith(s + ".") for s in SECTIONS)


def base(ref: str) -> str:
    return re.match(r"\d+(?:\.\d+)+", ref).group(0)


def parse_srs() -> tuple[dict[str, str], dict[str, str]]:
    clauses: dict[str, list[str]] = {}
    headings: dict[str, str] = {}
    current = None
    for line in SRS.read_text(encoding="utf-8").splitlines():
        if t := TOC.match(line):  # table of contents gives the section headings
            headings.setdefault(t.group(1), t.group(2))
            continue
        if m := CLAUSE.match(line):
            current = m.group(1)
            if current in clauses:  # repeated number (cross reference in a table): keep first
                current = None
                continue
            clauses[current] = [m.group(2).strip()]
        elif current and line.strip() and not NOISE.search(line):
            clauses[current].append(line.strip())
    return {k: re.sub(r"\s+", " ", " ".join(v)) for k, v in clauses.items()}, headings


def heading_for(c: str, headings: dict[str, str]) -> str:
    parts = c.split(".")
    for n in (4, 3, 2):
        key = ".".join(parts[:n])
        if key in headings:
            return f"{key} {headings[key]}"
    return ".".join(parts[:3])


def main() -> None:
    texts, headings = parse_srs()
    refs = json.loads(REFS.read_text(encoding="utf-8"))
    tcs: dict[str, list[dict]] = {}
    for feat, cases in refs.items():
        for tc in cases:
            if tc["deleted"] or tc["useft"] or not tc["nI"]:
                continue
            bases = sorted({base(r) for r in tc["refs"]})
            if not bases or len(bases) > MAX_CLAUSES:
                continue
            for b in bases:
                if in_scope(b):
                    tcs.setdefault(b, []).append(
                        {"id": f"{feat}/TC{tc['no']}", "clauses": bases, "steps": tc["nsteps"]}
                    )
    t3 = TABLE3.read_text(encoding="utf-8")
    nontest = sorted(
        {m for m in re.findall(r"^\s{4,14}(3\.\d+(?:\.\d+)+)", t3, re.M) if in_scope(m)}
    )
    out = []
    for c in sorted(set(tcs) | set(nontest), key=lambda c: [int(x) for x in c.split(".")]):
        text = texts.get(c, "")
        out.append(
            {
                "clause": c,
                "kind": "non_testable" if c in nontest else "core",
                "heading": heading_for(c, headings),
                "text": text,
                "has_shall": "shall" in text,
                "spike": c in SPIKE,
                # stage 5 only; never shown to the wording agent
                "test_cases": sorted(tcs.get(c, []), key=lambda t: (len(t["clauses"]), t["id"])),
            }
        )
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
