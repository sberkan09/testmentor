"""Layer 1 metrics: rule checks without any model call (docs/paketler/paket-1-olcum.md)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from sklearn.metrics import adjusted_rand_score


@dataclass(frozen=True)
class RefRequirement:
    id: str
    project: str
    language: str
    methods: frozenset[str]
    cluster: str
    trap: bool = False


@dataclass
class ProjectOutcome:
    project: str
    clusters: list[list[str]]
    methods: dict[str, list[str]]
    test_cases: list[dict[str, Any]]
    covered_before_repair: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class CallStat:
    kind: str  # "classification" | "label" | "generation" | "repair" | "incremental" | "merge"
    schema_valid: bool
    error: bool
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int | None
    ttft_s: float | None
    total_s: float


def step_structure_ok(tc: Mapping[str, Any]) -> bool:
    steps = tc.get("steps") or []
    if not steps:
        return False
    nos = [s.get("no") for s in steps]
    return nos == list(range(1, len(steps) + 1)) and all(
        str(s.get("action", "")).strip() and str(s.get("expected", "")).strip() for s in steps
    )


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    a, b = set(a), set(b)
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def requirement_metrics(
    outcomes: Sequence[ProjectOutcome],
    refs: Mapping[str, RefRequirement],
    test_method: str,
    keep: Callable[[RefRequirement], bool] = lambda r: True,
) -> dict[str, Any]:
    """Metrics over the requirements selected by `keep` (e.g. one language)."""
    selected = {rid: r for rid, r in refs.items() if keep(r)}
    covered: set[str] = set()
    tests_on_selected: list[dict[str, Any]] = []
    violations = 0
    covered_before: set[str] = set()
    for o in outcomes:
        covered_before |= o.covered_before_repair
        for tc in o.test_cases:
            ids = [i for i in tc.get("covers", []) if i in selected]
            if not ids:
                continue
            tests_on_selected.append(tc)
            covered.update(ids)
            if any(test_method not in selected[i].methods for i in ids):
                violations += 1
    needs_test = [rid for rid, r in selected.items() if test_method in r.methods]
    predicted = {rid: m for o in outcomes for rid, m in o.methods.items()}
    method_rows = [(set(predicted.get(rid, [])), r.methods) for rid, r in selected.items()]
    return {
        "requirements": len(selected),
        "coverage_rate": _rate(sum(r in covered for r in needs_test), len(needs_test)),
        "coverage_rate_before_repair": _rate(
            sum(r in covered_before for r in needs_test), len(needs_test)
        ),
        "no_test_violations": violations,
        "step_structure_rate": _rate(
            sum(step_structure_ok(tc) for tc in tests_on_selected), len(tests_on_selected)
        ),
        "test_cases": len(tests_on_selected),
        "method_exact_match": _rate(sum(p == r for p, r in method_rows), len(method_rows)),
        "method_jaccard": round(mean(_jaccard(p, r) for p, r in method_rows), 4)
        if method_rows
        else None,
    }


def raw_violations(
    outputs: Iterable[str], refs: Mapping[str, RefRequirement], test_method: str
) -> int:
    """Test cases in the model's own outputs (before the covers filter) that cover a requirement
    whose reference methods lack `test_method` (paket 3). The producer drops such ids, so the
    final set cannot show them in reference mode; this keeps the paket 1 threshold meaningful.
    Lists read: `test_cases` (full, repair), `add` and `update` (incremental)."""
    count = 0
    for text in outputs:
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            continue
        for key in ("test_cases", "add", "update"):
            for tc in data.get(key) or []:
                ids = [i for i in tc.get("covers", []) if i in refs]
                if any(test_method not in refs[i].methods for i in ids):
                    count += 1
    return count


_WORD = re.compile(r"\w+")


def _step_words(tc: Mapping[str, Any]) -> set[str]:
    text = " ".join(f"{s.get('action', '')} {s.get('expected', '')}" for s in tc.get("steps") or [])
    return set(_WORD.findall(text.lower()))


def duplicate_tests(outcomes: Sequence[ProjectOutcome], threshold: float = 0.8) -> dict[str, Any]:
    """D7: pairs of test cases in the same project with the same `covers` set whose normalised
    step words have Jaccard >= `threshold`. `duplicate_test_rate`: share of test cases that are
    in at least one such pair."""
    pairs = 0
    involved = 0
    total = 0
    for o in outcomes:
        groups: dict[frozenset[str], list[set[str]]] = {}
        for tc in o.test_cases:
            groups.setdefault(frozenset(tc.get("covers", [])), []).append(_step_words(tc))
            total += 1
        for words in groups.values():
            dup = [False] * len(words)
            for i in range(len(words)):
                for j in range(i + 1, len(words)):
                    if _jaccard(words[i], words[j]) >= threshold:
                        pairs += 1
                        dup[i] = dup[j] = True
            involved += sum(dup)
    return {"duplicate_pairs": pairs, "duplicate_test_rate": _rate(involved, total)}


def cluster_ari(outcome: ProjectOutcome, refs: Mapping[str, RefRequirement]) -> float | None:
    ids = sorted(rid for rid, r in refs.items() if r.project == outcome.project)
    predicted = {rid: i for i, c in enumerate(outcome.clusters) for rid in c}
    if len(ids) < 2 or any(rid not in predicted for rid in ids):
        return None
    return round(
        float(adjusted_rand_score([refs[r].cluster for r in ids], [predicted[r] for r in ids])), 4
    )


def call_metrics(calls: Sequence[CallStat], wall_s: float, clusters: int) -> dict[str, Any]:
    gen = [c for c in calls if c.kind in ("generation", "repair")]
    out_tokens = sum(c.completion_tokens for c in calls)
    in_tokens = sum(c.prompt_tokens for c in calls)
    cached = [c.cached_tokens for c in calls if c.cached_tokens is not None]
    return {
        "calls": len(calls),
        "errors": sum(c.error for c in calls),
        "schema_valid_rate": _rate(sum(c.schema_valid for c in calls), len(calls)),
        "schema_valid_rate_generation": _rate(sum(c.schema_valid for c in gen), len(gen)),
        "tokens_total": in_tokens + out_tokens,
        "prompt_tokens": in_tokens,
        "completion_tokens": out_tokens,
        "cached_tokens": sum(cached) if cached else None,
        "prefix_cache_hit_rate": _rate(sum(cached), in_tokens) if cached else None,
        "wall_s": round(wall_s, 2),
        "seconds_per_cluster": round(wall_s / clusters, 2) if clusters else None,
        "tokens_per_second": round(out_tokens / wall_s, 1) if wall_s else None,
    }


def layer1(
    outcomes: Sequence[ProjectOutcome],
    refs: Mapping[str, RefRequirement],
    calls: Sequence[CallStat],
    wall_s: float,
    test_method: str,
    raw_outputs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """`raw_outputs` given (paket 3 pipeline): `all.no_test_violations_raw` is counted on them and
    the threshold uses it; `all.no_test_violations` stays the count on the final sets."""
    langs = sorted({r.language for r in refs.values()})
    aris = [a for o in outcomes if (a := cluster_ari(o, refs)) is not None]
    overall = requirement_metrics(outcomes, refs, test_method)
    overall |= duplicate_tests(outcomes)
    if raw_outputs is not None:
        overall["no_test_violations_raw"] = raw_violations(raw_outputs, refs, test_method)
    return {
        "all": overall,
        "by_language": {
            lang: requirement_metrics(
                outcomes, refs, test_method, lambda r, lang=lang: r.language == lang
            )
            for lang in langs
        },
        "traps": requirement_metrics(outcomes, refs, test_method, lambda r: r.trap),
        "cluster_ari": round(mean(aris), 4) if aris else None,
        "cluster_ari_by_project": {o.project: cluster_ari(o, refs) for o in outcomes},
        "calls": call_metrics(calls, wall_s, sum(len(o.clusters) for o in outcomes)),
    }


def passes_thresholds(m: Mapping[str, Any], thresholds: Mapping[str, float]) -> dict[str, bool]:
    """Decision rule step 1 (paket-1-olcum.md, Karar kuralı)."""
    a, c = m["all"], m["calls"]
    return {
        "schema_valid_rate": (c["schema_valid_rate"] or 0) >= thresholds["schema_valid_rate"],
        "coverage_rate": (a["coverage_rate"] or 0) >= thresholds["coverage_rate"],
        "step_structure_rate": (a["step_structure_rate"] or 0) >= thresholds["step_structure_rate"],
        "no_test_violations": a.get("no_test_violations_raw", a["no_test_violations"])
        <= thresholds["no_test_violations"],
    }
