"""D8 scenarios: how a set is produced again after a change (paket 3).

Experiment key `scenario: {kind: add | remove | merge, min_test_members: 3, arms: {...}}`. The
baseline is produced once per project; every arm applies the same change to a copy of it, so the
arms are compared on the same sets (paired). An arm is one config line, as the result will be
applied:
- add: `generation.regeneration: incremental` (working assumption) or `full`;
- remove: `generation.prune_removals: false` (incremental call) or `true` (no call);
- merge: `merge_sources: true` (merge prompt, drops duplicates) or `false` (regenerate).
Production mode settings are not part of `input_hash`, so the baseline stays fresh under every
arm's settings.

Golden set reference clusters and methods; clusters with at least `min_test_members` Test
members take part. Per project two phases, recorded as `phase` on every call:
1. baseline: the sets without the held-out requirement (add: it waits in a `park` cluster with a
   non-Test method, which needs no call), then one test per selected set is pinned as a "user
   correction" (title and first step edited);
2. change, once per arm: the event (add: the held-out requirement goes back with its methods; remove: the
   largest-id Test member leaves to `park`; merge: neighbouring clusters merge), then the stale
   sets are produced again.

Metrics (`PipelineResult.extra`): preservation of the earlier unpinned cases (a later case with
text similarity >= 0.9 on title and steps; identical cases count too; on removal the cases that
covered only the removed requirement are left out), identical cases, pinned cases kept and
repeated (a generated case >= 0.8 similar to a pinned one), the new requirement's coverage
before repair (add), duplicates and coverage of merged sets, calls, output tokens and call time
of the change phase. Recall of the changed requirements comes from the judge (step 8): the rows
list their ids.
"""

from __future__ import annotations

import difflib
import time
from collections.abc import Mapping, Sequence
from typing import Any

from core.events import (
    ClusterCreated,
    ClustersMerged,
    MethodEdited,
    RequirementMoved,
    TestCaseEdited,
)
from core.graph import ProjectState
from core.invalidation import Hint, apply
from core.metrics import ProjectOutcome, duplicate_tests
from core.nodes import NodeKind, NodeRef, TestCaseContent, TestSetContent, ref
from eval.golden import Golden, GoldenProject
from eval.pipeline import Pipeline, PipelineResult, case_dicts
from eval.stage_driver import drive

PARK = "park"
PRESERVED = 0.9
REPEATED = 0.8


def case_text(c: Mapping[str, Any]) -> str:
    steps = " ".join(f"{s['action']} {s['expected']}" for s in c["steps"])
    return " ".join(f"{c['title']} {steps}".lower().split())


def similarity(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    return difflib.SequenceMatcher(None, case_text(a), case_text(b), autojunk=False).ratio()


def _content(c: Mapping[str, Any]) -> dict[str, Any]:
    """A case without its ids: full regeneration renumbers, so identity is by content."""
    return {k: v for k, v in c.items() if k not in ("id", "case_id", "cluster", "pinned")}


def correction(case: TestCaseContent) -> TestCaseContent:
    """The user's correction of a generated case: title and first step changed."""
    steps = list(case.steps)
    steps[0] = steps[0].model_copy(update={"action": f"{steps[0].action} (düzeltildi)"})
    return case.model_copy(update={"title": f"[Düzeltildi] {case.title}", "steps": tuple(steps)})


class ScenarioPipeline(Pipeline):
    def __init__(self, *args: Any, scenario: Mapping[str, Any], **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.scenario = dict(scenario)
        self.kind = self.scenario["kind"]
        if self.kind not in ("add", "remove", "merge"):
            raise ValueError(f"unknown scenario {self.kind!r}")
        self.min_test = int(self.scenario.get("min_test_members", 3))
        self.arms: dict[str, dict[str, Any]] = dict(self.scenario.get("arms") or {"default": {}})
        allowed = {"regeneration", "prune_removals", "merge_sources"}
        for name, arm in self.arms.items():
            if set(arm) - allowed:
                raise ValueError(f"arm {name}: unknown keys {sorted(set(arm) - allowed)}")
        self.rows: list[dict[str, Any]] = []
        self.phases: list[dict[str, Any]] = []

    # Setup ----------------------------------------------------------------------------------

    def _ref_methods(self, p: GoldenProject) -> dict[str, tuple[str, ...]]:
        return {r["id"]: tuple(sorted(r["verification_methods"])) for r in p.raw["requirements"]}

    def _other_method(self) -> str:
        test = self.settings.test_method
        return next(m.name for m in self.card_methods if m.name != test)

    async def run_project(self, p: GoldenProject) -> ProjectOutcome:
        test = self.settings.test_method
        methods = self._ref_methods(p)
        clusters = {f"c{i:03d}": tuple(c) for i, c in enumerate(p.reference_clusters())}
        tests_of = {k: [m for m in ms if test in methods[m]] for k, ms in clusters.items()}
        selected = [k for k, t in tests_of.items() if len(t) >= self.min_test]
        changed = {k: max(tests_of[k]) for k in selected}  # held out (add) or removed (remove)
        other = self._other_method()

        base = dict(clusters)
        if self.kind == "add" and changed:
            base = {
                k: tuple(m for m in ms if m not in changed.values()) for k, ms in clusters.items()
            }
            base[PARK] = tuple(sorted(changed.values()))
        state = self.project_state(p, base)
        state, _, _ = await self._reference_methods(
            p, state, self._complete(p, "setup"), predict=False
        )
        if self.kind == "add":
            for rid in changed.values():
                state, _ = apply(state, MethodEdited(requirement=rid, methods=(other,)))

        # Phase 1: baseline -------------------------------------------------------------------
        state, _ = await self._phase(p, "baseline", state)
        pinned: dict[str, dict[str, Any]] = {}
        if self.kind in ("add", "remove"):
            for k in selected:
                for c in case_dicts(state, k):
                    if self.kind == "remove" and changed[k] in c["covers"]:
                        continue
                    node = state.node(ref(NodeKind.TEST_CASE, c["id"]))
                    assert isinstance(node.content, TestCaseContent)
                    state, _ = apply(
                        state, TestCaseEdited(case=c["id"], content=correction(node.content))
                    )
                    pinned[k] = next(x for x in case_dicts(state, k) if x["id"] == c["id"])
                    break
        before = {k: [c for c in case_dicts(state, k) if not c["pinned"]] for k in clusters}

        # Phase 2: change, once per arm on the same baseline ----------------------------------
        baseline = state
        finals: dict[str, ProjectState] = {}
        for arm_name, arm in self.arms.items():
            finals[arm_name] = await self._change(
                p,
                baseline,
                arm_name,
                arm,
                clusters,
                tests_of,
                selected,
                changed,
                methods,
                other,
                before,
                pinned,
            )
        for arm_name, final in finals.items():
            self.records.append(
                {
                    "type": "scenario_project",
                    "project": p.key,
                    "arm": arm_name,
                    "test_cases": [
                        t for c in final.keys_of(NodeKind.CLUSTER) for t in case_dicts(final, c)
                    ],
                }
            )
        # Layer 1 and the plain project record use the first arm (the working assumption).
        return self._outcome(p, finals[next(iter(self.arms))])

    async def _change(
        self,
        p: GoldenProject,
        state: ProjectState,
        arm_name: str,
        arm: Mapping[str, Any],
        clusters: Mapping[str, tuple[str, ...]],
        tests_of: Mapping[str, list[str]],
        selected: Sequence[str],
        changed: Mapping[str, str],
        methods: Mapping[str, tuple[str, ...]],
        other: str,
        before: Mapping[str, list[dict[str, Any]]],
        pinned: Mapping[str, dict[str, Any]],
    ) -> ProjectState:
        test = self.settings.test_method
        hints: dict[NodeRef, Hint] = {}
        sources: dict[NodeRef, Sequence[TestCaseContent]] = {}
        merged: dict[str, tuple[str, str]] = {}
        if self.kind == "add":
            for k, rid in changed.items():
                state, inv = apply(state, RequirementMoved(requirement=rid, to_cluster=k))
                hints |= inv.hints
                state, inv = apply(state, MethodEdited(requirement=rid, methods=methods[rid]))
                hints |= inv.hints
        elif self.kind == "remove":
            for rid in changed.values():
                state, inv = apply(state, MethodEdited(requirement=rid, methods=(other,)))
                hints |= inv.hints
            if changed:
                state, inv = apply(
                    state, ClusterCreated(cluster=PARK, members=tuple(sorted(changed.values())))
                )
                hints |= inv.hints
        else:
            with_tests = [k for k in clusters if tests_of[k]]
            for i in range(0, len(with_tests) - 1, 2):
                a, b = with_tests[i], with_tests[i + 1]
                new = f"m{i // 2:03d}"
                for k in (a, b):
                    sources[ref(NodeKind.TEST_SET, k)] = self._unpinned(state, k)
                state, inv = apply(state, ClustersMerged(sources=(a, b), new_cluster=new))
                hints |= inv.hints
                merged[new] = (a, b)
            if not arm.get("merge_sources", True):
                sources = {}
        settings = self.settings.model_copy(
            update={k: v for k, v in arm.items() if k in ("regeneration", "prune_removals")}
        )
        state, stats = await self._phase(
            p, f"change:{arm_name}", state, hints=hints, sources=sources, settings=settings
        )

        # Metrics -----------------------------------------------------------------------------
        if self.kind in ("add", "remove"):
            for k in selected:
                row = self._row(p, state, k, changed[k], before[k], pinned.get(k), stats)
                self.rows.append({"arm": arm_name, **row})
        else:
            for new, (a, b) in merged.items():
                after = case_dicts(state, new)
                dup = duplicate_tests([ProjectOutcome(p.key, [], {}, after)])
                need = [m for m in state.members(new) if test in methods[m]]
                covered = {i for c in after for i in c["covers"]}
                self.rows.append(
                    {
                        "arm": arm_name,
                        "project": p.key,
                        "cluster": new,
                        "sources": [a, b],
                        "requirements": list(state.members(new)),
                        "cases_before": len(before[a]) + len(before[b]),
                        "cases_after": len(after),
                        "duplicate_pairs": dup["duplicate_pairs"],
                        "duplicate_test_rate": dup["duplicate_test_rate"],
                        "coverage": sum(m in covered for m in need) / len(need) if need else None,
                        "mode": state.node(ref(NodeKind.TEST_SET, new)).produced_by.mode,  # type: ignore[union-attr]
                    }
                )
        return state

    # Helpers --------------------------------------------------------------------------------

    def _complete(self, p: GoldenProject, phase: str):
        return self.recorder.for_project(p.key, phase)

    async def _phase(
        self,
        p: GoldenProject,
        phase: str,
        state: ProjectState,
        *,
        hints: Mapping[NodeRef, Hint] | None = None,
        sources: Mapping[NodeRef, Sequence[TestCaseContent]] | None = None,
        settings: Any = None,
    ) -> tuple[ProjectState, dict[NodeRef, Mapping[str, Any]]]:
        started = time.perf_counter()

        async def embed(texts: Sequence[str]) -> list[list[float]]:
            return await self.embeddings.get(texts)

        driven = await drive(
            state,
            self._complete(p, phase),
            settings=settings or self.settings,
            skip={NodeKind.CLUSTER_LABEL},
            hints=hints,
            sources=sources,
            embed=embed,
        )
        self.phases.append(
            {
                "project": p.key,
                "phase": phase,
                "wall_s": round(time.perf_counter() - started, 2),
                "errors": {str(r): why for r, why in driven.errors.items()},
            }
        )
        return driven.state, driven.stats()

    @staticmethod
    def _unpinned(state: ProjectState, cluster: str) -> list[TestCaseContent]:
        content = state.node(ref(NodeKind.TEST_SET, cluster)).content
        keys = content.case_keys if isinstance(content, TestSetContent) else ()
        out = []
        for k in keys:
            node = state.node(ref(NodeKind.TEST_CASE, k))
            if not node.pinned and isinstance(node.content, TestCaseContent):
                out.append(node.content)
        return out

    def _row(
        self,
        p: GoldenProject,
        state: ProjectState,
        cluster: str,
        changed: str,
        before: list[dict[str, Any]],
        pinned: dict[str, Any] | None,
        stats: Mapping[NodeRef, Mapping[str, Any]],
    ) -> dict[str, Any]:
        if self.kind == "remove":
            # Cases covering only the removed requirement are meant to go; not counted.
            before = [b for b in before if set(b["covers"]) != {changed}]
        after_all = case_dicts(state, cluster)
        after = [c for c in after_all if not c["pinned"]]
        contents = [_content(c) for c in after]
        preserved = sum(1 for b in before if any(similarity(b, a) >= PRESERVED for a in after))
        identical = sum(1 for b in before if _content(b) in contents)
        st = dict(stats.get(ref(NodeKind.TEST_SET, cluster), {}))
        row: dict[str, Any] = {
            "project": p.key,
            "cluster": cluster,
            "changed_requirement": changed,
            "mode": st.get("mode"),
            "calls": st.get("calls", 0),
            "completion_tokens": st.get("completion_tokens"),
            "cases_before": len(before),
            "cases_after": len(after),
            "preserved": preserved,
            "identical": identical,
        }
        if pinned is not None:
            kept = [c for c in after_all if c["pinned"] and _content(c) == _content(pinned)]
            row["pinned_kept"] = bool(kept)
            # Only cases the change wrote (new or updated): siblings already in the baseline that
            # resemble the pinned case are not a repeat caused by regeneration.
            # (By title and steps, so a case whose covers were only trimmed is not "written".)
            before_texts = {case_text(b) for b in before}
            written = [a for a in after if case_text(a) not in before_texts]
            row["pinned_repeats"] = sum(1 for a in written if similarity(a, pinned) >= REPEATED)
        if self.kind == "add":
            row["new_covered_before_repair"] = changed in st.get("covered_before_repair", [])
            row["new_covered"] = any(changed in c["covers"] for c in after_all)
        return row

    def _outcome(self, p: GoldenProject, state: ProjectState) -> ProjectOutcome:
        tests = [t for c in state.keys_of(NodeKind.CLUSTER) for t in case_dicts(state, c)]
        self.records.append(
            {
                "type": "project",
                "project": p.key,
                "clusters": [list(state.members(c)) for c in state.keys_of(NodeKind.CLUSTER)],
                "methods": {},
                "generation_inputs": "reference",
                "test_cases": tests,
                "covered_before_repair": [],
                "scenario": [r for r in self.rows if r["project"] == p.key],
            }
        )
        return ProjectOutcome(p.key, [], {}, tests, set())

    async def run(self, golden: Golden) -> PipelineResult:
        """Projects one after another (not concurrently as in `Pipeline.run`), so a phase's wall
        time is not mixed with another project's phase. Arms run in a fixed order; output tokens
        and call counts are the primary cost measure, wall time secondary."""
        started = time.perf_counter()
        outcomes = [await self.run_project(p) for p in golden.projects]
        res = PipelineResult(
            outcomes,
            self.records,
            self.calls,
            time.perf_counter() - started,
            raw_outputs=self.recorder.raw_outputs,
        )
        res.extra = summarize(self.kind, self.rows, self.phases, self.records)
        return res


def _rate(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def summarize(
    kind: str,
    rows: Sequence[Mapping[str, Any]],
    phases: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    arms = list(dict.fromkeys(r["arm"] for r in rows))
    return {
        "kind": kind,
        "baseline_calls": sum(
            1 for r in records if r.get("type") == "call" and r.get("phase") == "baseline"
        ),
        "arms": {a: summarize_arm(kind, a, rows, phases, records) for a in arms},
    }


def summarize_arm(
    kind: str,
    arm: str,
    rows: Sequence[Mapping[str, Any]],
    phases: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    phase = f"change:{arm}"
    rows = [r for r in rows if r["arm"] == arm]
    phases = [ph for ph in phases if ph["phase"] == phase]
    calls = [r for r in records if r.get("type") == "call" and r.get("phase") == phase]
    out: dict[str, Any] = {
        "units": len(rows),
        "change_calls": len(calls),
        "change_completion_tokens": sum(
            (r["metrics"] or {}).get("completion_tokens") or 0 for r in calls
        ),
        "change_call_s": round(sum((r["metrics"] or {}).get("total_s") or 0 for r in calls), 2),
        "change_wall_s": max((ph["wall_s"] for ph in phases), default=None),
        "errors": {ph["project"]: ph["errors"] for ph in phases if ph["errors"]},
        "rows": list(rows),
    }
    if kind in ("add", "remove"):
        before = sum(r["cases_before"] for r in rows)
        pinned = [r for r in rows if "pinned_kept" in r]
        out |= {
            "preservation_rate": _rate(sum(r["preserved"] for r in rows), before),
            "identical_rate": _rate(sum(r["identical"] for r in rows), before),
            "pinned_kept_rate": _rate(sum(r["pinned_kept"] for r in pinned), len(pinned)),
            "pinned_repeats": sum(r["pinned_repeats"] for r in pinned),
            "changed_requirements": [r["changed_requirement"] for r in rows],
        }
    if kind == "add":
        out["new_coverage_before_repair"] = _rate(
            sum(r["new_covered_before_repair"] for r in rows), len(rows)
        )
        out["new_coverage"] = _rate(sum(r["new_covered"] for r in rows), len(rows))
    if kind == "merge":
        cases = sum(r["cases_after"] for r in rows)
        out |= {
            "duplicate_pairs": sum(r["duplicate_pairs"] for r in rows),
            "duplicate_test_rate": _rate(
                sum((r["duplicate_test_rate"] or 0) * r["cases_after"] for r in rows), cases
            ),
            "coverage": _rate(
                sum(r["coverage"] for r in rows if r["coverage"] is not None),
                sum(1 for r in rows if r["coverage"] is not None),
            ),
        }
    return out
