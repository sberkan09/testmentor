"""Corpus of golden set v1.

    python -m eval.corpus list   [--project etc]
    python -m eval.corpus fetch  [--project etc] [--doc ID ...] [--all] [--allow-unpinned]
    python -m eval.corpus verify [--project etc]

`fetch` skips optional downloads unless `--all` or `--doc` names them.
"""

from __future__ import annotations

import argparse
import sys

from eval.corpus.fetch import CorpusError, fetch_manifest, make_client, verify_manifest
from eval.corpus.manifest import load_manifest, manifest_paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.corpus", description=__doc__)
    ap.add_argument("command", choices=["list", "fetch", "verify"])
    ap.add_argument("--project", action="append", help="project key, e.g. etc (repeatable)")
    ap.add_argument("--doc", action="append", help="document id (repeatable)")
    ap.add_argument("--all", action="store_true", help="include optional downloads")
    ap.add_argument("--allow-unpinned", action="store_true")
    args = ap.parse_args(argv)
    wanted = {p.lower() for p in args.project or []}
    manifests = [load_manifest(p) for p in manifest_paths()]
    manifests = [m for m in manifests if not wanted or m.project.lower() in wanted]
    if not manifests:
        print("no matching manifest", file=sys.stderr)
        return 2
    failed = False
    for m in manifests:
        print(f"== {m.project}")
        if args.command == "list":
            for d in m.documents:
                dl = m.downloads.get(d.download or "")
                flag = " (optional)" if dl and dl.optional else ""
                print(
                    f"  {d.id:24} {d.role.value:9} {d.language} {d.repo_text.value:12} {d.title}{flag}"
                )
            for k, why in m.excluded.items():
                print(f"  - excluded {k}: {why}")
        elif args.command == "verify":
            for key, status in verify_manifest(m).items():
                failed |= status in ("mismatch", "unpinned")
                print(f"  {key:20} {status}")
        else:
            docs = [d for d in args.doc or [] if any(x.id == d for x in m.documents)]
            if args.doc and not docs:
                continue
            try:
                with make_client() as client:
                    results, index, notes = fetch_manifest(
                        m,
                        client,
                        docs=docs or None,
                        include_optional=args.all,
                        allow_unpinned=args.allow_unpinned,
                    )
            except CorpusError as exc:
                print(f"  ERROR {exc}", file=sys.stderr)
                failed = True
                continue
            for r in results:
                print(f"  {r.key:20} {r.status:10} {r.bytes:>11} {r.sha256[:12]}")
            for n in notes:
                print(f"  ! {n}")
            print(
                f"  {len(index)} documents in index, {sum(len(v['texts']) for v in index.values())} text files"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
