"""D10 (paket 11): the project example pool built from the golden reference checks, without
leaking the answer key.

Each requirement with reference checks becomes one pooled test case (`REF-<id>`: its reference
preconditions, one step per check). A cluster must not see the reference of its own members, nor of
a requirement that shares a reference source (`reference_candidates`) with a member: that test
would be the same procedure. The rule is carried by `ExampleEntry.excluded_with` (the product's
own selection rule, `services.kb_examples`), and `leak_check` verifies the outcome independently
from the golden data after the run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.nodes import Step, TestCaseContent
from core.stages.base import Embed
from services.kb_examples import ExampleEntry, build_entry

REF_PREFIX = "REF-"
TITLE_CHARS = 90


def _title(action: str) -> str:
    text = " ".join(action.split())
    return text if len(text) <= TITLE_CHARS else text[: TITLE_CHARS - 1].rstrip() + "…"


def _sources(r: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(str(c) for c in r.get("reference_candidates") or () if str(c).strip())


def reference_case(r: Mapping[str, Any], test_type: str, priority: str) -> TestCaseContent | None:
    checks = r.get("reference_checks") or []
    if not checks:
        return None
    return TestCaseContent(
        id=f"{REF_PREFIX}{r['id']}",
        title=_title(checks[0]["action"]),
        covers=(r["id"],),
        type=test_type,
        priority=priority,
        preconditions=r.get("reference_preconditions") or "",
        steps=tuple(
            Step(no=i, action=c["action"], expected=c["expected"])
            for i, c in enumerate(checks, start=1)
        ),
    )


def related(requirements: Sequence[Mapping[str, Any]]) -> dict[str, frozenset[str]]:
    """Requirement id → the other requirements sharing a reference source with it."""
    by_id = {r["id"]: _sources(r) for r in requirements}
    return {
        rid: frozenset(o for o, s in by_id.items() if o != rid and s & mine)
        for rid, mine in by_id.items()
    }


async def build_reference_pool(
    project: Mapping[str, Any], embed: Embed, *, test_type: str, priority: str
) -> list[ExampleEntry]:
    reqs = sorted(project["requirements"], key=lambda r: r["id"])
    rel = related(reqs)
    entries = []
    for r in reqs:
        case = reference_case(r, test_type, priority)
        if case is None:
            continue
        entries.append(
            await build_entry(case.id, case, [r["text"]], embed, excluded_with=rel[r["id"]])
        )
    return entries


class ExampleLeak(AssertionError):
    pass


def leak_check(
    project: Mapping[str, Any],
    clusters: Mapping[str, Sequence[str]],
    example_keys: Mapping[str, Sequence[str]],
) -> dict[str, list[str]]:
    """Cluster → the requirement ids of its selected examples. Raises `ExampleLeak` when an
    example covers a member or shares a reference source with one (checked from the golden data,
    not from `excluded_with`)."""
    sources = {r["id"]: _sources(r) for r in project["requirements"]}
    out: dict[str, list[str]] = {}
    for cid, members in clusters.items():
        member_sources = frozenset().union(*(sources.get(m, frozenset()) for m in members))
        picked = []
        for key in example_keys.get(cid, ()):
            rid = key.split("@", 1)[0].removeprefix(REF_PREFIX)
            if rid in members:
                raise ExampleLeak(f"{cid}: example {key} covers member {rid}")
            shared = sources.get(rid, frozenset()) & member_sources
            if shared:
                raise ExampleLeak(f"{cid}: example {key} shares reference source {sorted(shared)}")
            picked.append(rid)
        out[cid] = picked
    return out
