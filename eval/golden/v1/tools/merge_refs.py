"""Merge reference-agent outputs (<ID>.refs.json) into eval/golden/v1/<project>.json and validate.

    python eval/golden/v1/tools/merge_refs.py DIR [DIR ...]

Only stage 5 fields are taken (preconditions, checks, passages, needs_documents, reference_note);
requirement text and stage 4 fields are never changed by a reference agent. Problems from the
validator are printed per requirement; files are written only when there are none, unless
--force.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.golden_v1 import V1_DIR, ProjectV1, validate_project

FIELDS = (
    "reference_preconditions",
    "reference_checks",
    "support_passages",
    "needs_documents",
    "reference_note",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    outputs = {}
    for d in args.dirs:
        for f in sorted(Path(d).glob("*.refs.json")):
            rec = json.loads(f.read_text(encoding="utf-8"))
            outputs[rec["id"]] = rec
    failed = False
    for path in sorted(V1_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        hits = 0
        for r in data["requirements"]:
            if r["id"] in outputs:
                hits += 1
                r.update({k: outputs[r["id"]][k] for k in FIELDS if k in outputs[r["id"]]})
        if not hits:
            continue
        problems = validate_project(ProjectV1.model_validate(data))
        for p in problems:
            print(f"  {path.stem}: {p}")
        failed |= bool(problems)
        if not problems or args.force:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{path.name}: merged {hits}, problems {len(problems)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
