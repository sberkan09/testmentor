"""Test set producer (docs/tasarim.md, Test durumu üretimi): modes, tails, repair, retry, split."""

from __future__ import annotations

import pytest

from core.events import (
    ClustersMerged,
    MethodEdited,
    NodePinned,
    ProjectCardChanged,
    RequirementMoved,
    RequirementTextChanged,
    TestCaseEdited,
)
from core.invalidation import analyze, apply
from core.nodes import NodeKind, ProjectCardContent, ref
from core.prompts import (
    INCREMENTAL_INSTRUCTION,
    MERGE_INSTRUCTION,
    PINNED_HEADER,
    SCHEMA_RETRY_INSTRUCTION,
    ContentCard,
    generation_messages,
    repair_section,
)
from core.schemas import Requirement, case_set_model
from core.stages.test_generation import basis_of, read_basis
from tests.stages.helpers import (
    EXAMPLES,
    SETTINGS,
    ScriptedComplete,
    case_json,
    cases_of,
    covered,
    drive,
    many_reqs,
    project,
    requirement_rows,
    smart_reply,
)

pytestmark = pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="paket 3 adım 4")

SCHEMA = case_set_model(SETTINGS.test_types, SETTINGS.priorities)


def SET(k: str):
    return ref(NodeKind.TEST_SET, k)


def MX(k: str):
    return ref(NodeKind.MATRIX_ROW, k)


def expected_full(state, cluster: str) -> list[dict[str, str]]:
    """Layers 1–5 of full generation for the cluster as it is in `state` (paket 1 prompt)."""
    card = state.node(ref(NodeKind.PROJECT_CARD, "card")).content
    assert isinstance(card, ProjectCardContent)
    members = state.members(cluster)
    reqs = [
        Requirement(id=m, text=state.requirement(m).text, language=state.requirement(m).language)
        for m in members
    ]
    methods = {m: list(state.node(ref(NodeKind.METHOD, m)).content.methods) for m in members}
    return generation_messages(
        ContentCard(card),
        reqs,
        methods,
        schema=SCHEMA.model_json_schema(),
        examples=EXAMPLES,
        test_method=SETTINGS.test_method,
        types=SETTINGS.test_types,
        priorities=SETTINGS.priorities,
    )


def request_for(complete: ScriptedComplete, cluster_members: set[str], nth: int = 0):
    reqs = [
        r
        for r in complete.of(NodeKind.TEST_SET)
        if {rid for rid, _ in requirement_rows(r)} == cluster_members
    ]
    return reqs[nth]


async def base():
    complete = ScriptedComplete()
    out = await drive(project(), complete)
    assert not analyze(out.state).stale
    return out.state


# Full -----------------------------------------------------------------------------------------


async def test_full_prompt_is_the_paket1_prompt():
    complete = ScriptedComplete()
    out = await drive(project(), complete)
    first = request_for(complete, {"R1", "R2"})
    assert list(first.messages) == expected_full(out.state, "A")
    assert first.schema is SCHEMA
    assert first.params == SETTINGS.llm[NodeKind.TEST_SET]
    assert len(complete.of(NodeKind.TEST_SET)) == 3  # one call per cluster


async def test_full_result_records_basis_and_settles():
    state = await base()
    node = state.node(SET("A"))
    assert node.produced_by.mode == "full"
    assert read_basis(node) == basis_of(state, "A")
    assert covered(state, "A") == {"R1", "R2"}
    assert [c.id for c in cases_of(state, "A")] == ["TC-1", "TC-2"]  # renumbered


async def test_covers_filtered_to_test_members():
    state = project()
    state, _ = apply(state, MethodEdited(requirement="R2", methods=("İnceleme",)))
    reply = {
        "test_cases": [
            case_json("R1", covers=["R1", "R9"]),
            case_json("R3", covers=["R3"]),
            case_json("R2", covers=["R2"]),
        ]
    }
    complete = ScriptedComplete(
        lambda r: reply if {i for i, _ in requirement_rows(r)} == {"R1", "R2"} else smart_reply(r)
    )
    out = await drive(state, complete)
    assert [c.covers for c in cases_of(out.state, "A")] == [("R1",)]
    s = out.stats(SET("A"))
    assert (s["dropped_ids"], s["dropped_cases"]) == (3, 2)


async def test_cluster_without_test_requirements_needs_no_call():
    state = project()
    for rid in ("R1", "R2"):
        state, _ = apply(state, MethodEdited(requirement=rid, methods=("İnceleme",)))
    complete = ScriptedComplete()
    out = await drive(state, complete)
    assert not [r for r in complete.of(NodeKind.TEST_SET) if "R1" in str(r.messages)]
    assert out.state.node(SET("A")).status.value == "fresh"
    assert cases_of(out.state, "A") == []


# Repair and retry -----------------------------------------------------------------------------


def only_r1(r):
    if {i for i, _ in requirement_rows(r)} == {"R1", "R2"}:
        return {"test_cases": [case_json("R1")]}
    return smart_reply(r)


def miss_r2_once():
    done: list[int] = []

    def handle(r):
        if not done and {i for i, _ in requirement_rows(r)} == {"R1", "R2"}:
            done.append(1)
            return {"test_cases": [case_json("R1")]}
        return smart_reply(r)

    return handle


async def test_repair_asks_only_for_missing_requirements():
    complete = ScriptedComplete(miss_r2_once())
    out = await drive(project(), complete)
    full, repair = request_for(complete, {"R1", "R2"}), request_for(complete, {"R1", "R2"}, 1)
    assert repair.messages[1]["content"] == full.messages[1]["content"] + "\n\n" + repair_section(
        ["R2"]
    )
    assert repair.schema is SCHEMA
    assert covered(out.state, "A") == {"R1", "R2"}
    s = out.stats(SET("A"))
    assert s["calls"] == 2 and s["covered_before_repair"] == ["R1"] and s["uncovered"] == []


async def test_still_uncovered_after_repair_is_written_not_failed():
    complete = ScriptedComplete(only_r1)  # repair also answers R1 only
    out = await drive(project(), complete)
    assert SET("A") not in out.failed()
    assert out.state.node(SET("A")).status.value == "fresh"
    assert out.stats(SET("A"))["uncovered"] == ["R2"]
    assert out.state.node(MX("R2")).content.covered is False


def bad_once_for_a():
    done: list[int] = []

    def handle(r):
        if not done and {i for i, _ in requirement_rows(r)} == {"R1", "R2"}:
            done.append(1)
            return '{"test_cases": []}'  # min_length=1 violated
        return smart_reply(r)

    return handle


async def test_schema_error_is_retried_once():
    complete = ScriptedComplete(bad_once_for_a())
    out = await drive(project(), complete)
    first, retry = request_for(complete, {"R1", "R2"}), request_for(complete, {"R1", "R2"}, 1)
    assert SCHEMA_RETRY_INSTRUCTION in retry.messages[1]["content"]
    assert retry.messages[1]["content"].startswith(first.messages[1]["content"] + "\n\n")
    assert not out.failed()
    assert out.stats(SET("A"))["calls"] == 2


async def test_second_schema_error_fails_the_node():
    bad = lambda r: '{"test_cases": []}'  # noqa: E731
    complete = ScriptedComplete(
        lambda r: bad(r) if {i for i, _ in requirement_rows(r)} == {"R1", "R2"} else smart_reply(r)
    )
    out = await drive(project(), complete)
    assert out.failed() == {SET("A")}
    assert out.state.node(SET("A")).status.value == "failed"
    assert cases_of(out.state, "A") == []


# Incremental ----------------------------------------------------------------------------------


async def test_move_produces_incremental_sets_and_keeps_unchanged_cases():
    state = await base()
    before_b = cases_of(state, "B")
    state, inv = apply(state, RequirementMoved(requirement="R2", to_cluster="B"))
    complete = ScriptedComplete()
    out = await drive(state, complete, hints=inv.hints)

    req_b = request_for(complete, {"R2", "R3", "R4"})
    assert req_b.schema.__name__ == "TestCaseDelta"
    content = req_b.messages[1]["content"]
    assert content.startswith(expected_full(state, "B")[1]["content"] + "\n\n")
    assert INCREMENTAL_INSTRUCTION in content and "Added: R2" in content

    after_b = cases_of(out.state, "B")
    assert after_b[: len(before_b)] == before_b  # same ids, same content
    assert covered(out.state, "B") == {"R2", "R3", "R4"}
    assert out.state.node(SET("B")).produced_by.mode == "incremental"
    assert not analyze(out.state).stale

    req_a = request_for(complete, {"R1"})  # removal still calls (design count; D8 measures pruning)
    assert "Removed: R2" in req_a.messages[1]["content"]
    assert covered(out.state, "A") == {"R1"}


async def test_unchanged_cases_keep_matrix_rows_fresh():
    state = await base()
    state, inv = apply(
        state, RequirementTextChanged(requirement="R3", text="The system shall log changes.")
    )
    complete = ScriptedComplete()
    out = await drive(state, complete, hints=inv.hints)
    versions = {k: out.state.node(MX(k)).version for k in ("R4",)}
    assert versions == {"R4": state.node(MX("R4")).version}  # R4's cases untouched


async def test_pinned_cases_go_to_the_tail_and_cannot_be_updated():
    state = await base()
    pinned = cases_of(state, "A")[0]
    key = f"A:{pinned.id}"
    state, _ = apply(
        state, TestCaseEdited(case=key, content=pinned.model_copy(update={"title": "Düzeltilmiş"}))
    )
    state, inv = apply(
        state, RequirementTextChanged(requirement="R2", text="Bağlantı 10 dakika geçerlidir.")
    )

    def update_pinned(r):
        if r.schema.__name__ == "TestCaseDelta":
            return {"add": [], "update": [case_json("R1", cid=pinned.id)]}
        return smart_reply(r)

    complete = ScriptedComplete(update_pinned)
    out = await drive(state, complete, hints=inv.hints)
    content = request_for(complete, {"R1", "R2"}).messages[1]["content"]
    assert content.index(PINNED_HEADER) < content.index(INCREMENTAL_INSTRUCTION)
    assert "Düzeltilmiş" in content
    assert out.stats(SET("A"))["pinned_update_attempts"] == 1
    assert out.stats(SET("A"))["calls"] == 1  # the pinned case covers R1: no repair
    assert out.state.node(ref(NodeKind.TEST_CASE, key)).content.title == "Düzeltilmiş"


async def test_card_change_regenerates_from_scratch():
    state = await base()
    state, inv = apply(state, ProjectCardChanged(text="Başka kart."))
    complete = ScriptedComplete()
    out = await drive(state, complete, hints=inv.hints)
    assert {r.schema.__name__ for r in complete.of(NodeKind.TEST_SET)} == {"TestCaseSet"}
    assert out.state.node(SET("A")).produced_by.mode == "full"


# Merge ----------------------------------------------------------------------------------------


async def test_merge_uses_source_sets_and_drops_duplicates():
    state = await base()
    sources = {SET("A"): cases_of(state, "A"), SET("B"): cases_of(state, "B")}
    state, inv = apply(state, ClustersMerged(sources=("A", "B"), new_cluster="D"))
    assert inv.hints[SET("D")].mode == "merge"

    complete = ScriptedComplete(
        lambda r: {"drop": ["B.TC-1"]} if r.schema.__name__ == "MergeDecision" else smart_reply(r)
    )
    out = await drive(state, complete, hints=inv.hints, sources=sources)
    req = complete.of(NodeKind.TEST_SET)[0]
    assert MERGE_INSTRUCTION in req.messages[1]["content"]
    ids = [c.id for c in cases_of(out.state, "D")]
    assert ids == ["TC-1", "TC-2", "B.TC-2", "TC-3"]  # dropping B.TC-1 uncovered R3: repaired
    assert cases_of(out.state, "D")[-1].covers == ("R3",)
    assert out.state.node(SET("D")).produced_by.mode == "merge"


async def test_merge_without_sources_regenerates():
    state = await base()
    state, inv = apply(state, ClustersMerged(sources=("A", "B"), new_cluster="D"))
    complete = ScriptedComplete()
    out = await drive(state, complete, hints=inv.hints)
    assert out.state.node(SET("D")).produced_by.mode == "full"


# Split ----------------------------------------------------------------------------------------


async def test_cluster_larger_than_unit_is_split_into_balanced_parts():
    reqs = many_reqs(60)
    state = project(reqs, {"BIG": tuple(reqs)})
    complete = ScriptedComplete()
    out = await drive(state, complete)
    calls = complete.of(NodeKind.TEST_SET)
    assert [len(requirement_rows(r)) for r in calls] == [20, 20, 20]
    assert covered(out.state, "BIG") == set(reqs)
    ids = [c.id for c in cases_of(out.state, "BIG")]
    assert ids == [f"TC-{i}" for i in range(1, 61)]
    assert out.stats(SET("BIG"))["units"] == 3


async def test_unit_limit_comes_from_settings():
    reqs = many_reqs(12)
    state = project(reqs, {"M": tuple(reqs)})
    complete = ScriptedComplete()
    await drive(state, complete, settings=SETTINGS.model_copy(update={"max_unit_size": 5}))
    assert [len(requirement_rows(r)) for r in complete.of(NodeKind.TEST_SET)] == [4, 4, 4]


async def test_pinning_a_case_does_not_call_the_model():
    state = await base()
    state, inv = apply(state, NodePinned(node=ref(NodeKind.TEST_CASE, "A:TC-1")))
    assert inv.llm_calls == 0
    complete = ScriptedComplete()
    await drive(state, complete, hints=inv.hints)
    assert complete.requests == []
