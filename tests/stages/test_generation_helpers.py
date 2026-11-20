"""Pure helpers of the test set producer (`core.stages.test_generation`)."""

from __future__ import annotations

import pytest

from core.events import MethodEdited, ProjectCardChanged, RequirementMoved, RequirementTextChanged
from core.invalidation import Hint, apply
from core.nodes import NodeKind, ProducedBy, TestCaseContent, ref
from core.schemas import Step
from core.stages.test_generation import (
    BASIS_PARAM,
    Basis,
    MemberBasis,
    apply_incremental,
    apply_merge,
    basis_of,
    choose_mode,
    delta,
    filter_covers,
    merge_sources,
    need,
    next_ids,
    prune_removed,
    read_basis,
    renumber,
    split_units,
    uncovered,
)
from tests.core.helpers import produce_all
from tests.stages.helpers import case_json, project

pytestmark = pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="paket 3 adım 4")


def tc(cid: str, *covers: str, title: str = "") -> TestCaseContent:
    return TestCaseContent(
        id=cid,
        title=title or f"{cid} başlık",
        covers=covers,
        type="Normal",
        priority="Orta",
        steps=(Step(no=1, action="yap", expected="olur"),),
    )


def SET(k: str):
    return ref(NodeKind.TEST_SET, k)


def with_basis(state, cluster: str):
    """State whose set `cluster` records the basis of the current state (as if produced now)."""
    r = SET(cluster)
    node = state.node(r)
    produced = ProducedBy(
        mode="full", params={BASIS_PARAM: basis_of(state, cluster).model_dump(mode="json")}
    )
    return state.model_copy(
        update={"nodes": state.nodes | {r: node.model_copy(update={"produced_by": produced})}}
    )


# Basis and mode -------------------------------------------------------------------------------


def test_basis_and_delta():
    state = produce_all(project())
    b0 = basis_of(state, "A")
    assert set(b0.members) == {"R1", "R2"}
    assert b0.members["R1"].methods == ("Test",)
    state = with_basis(state, "A")
    assert read_basis(state.node(SET("A"))) == b0

    state, _ = apply(state, RequirementTextChanged(requirement="R1", text="Yeni metin."))
    state, _ = apply(state, RequirementMoved(requirement="R3", to_cluster="A"))
    state, _ = apply(state, MethodEdited(requirement="R2", methods=("İnceleme",)))
    d = delta(b0, basis_of(state, "A"))
    assert d.added == ("R3",)
    assert d.changed == ("R1", "R2")
    assert d.removed == ()
    assert not d.only_removed


def test_delta_only_removed():
    old = Basis(
        config="c",
        card="k",
        passages=(),
        members={
            "R1": MemberBasis(text_hash="a", methods=("Test",)),
            "R2": MemberBasis(text_hash="b", methods=("Test",)),
        },
    )
    new = old.model_copy(update={"members": {"R1": old.members["R1"]}})
    d = delta(old, new)
    assert d.removed == ("R2",) and d.only_removed and not d.empty


def test_choose_mode():
    state = project()
    assert choose_mode(state, "A", None, {}) == "full"  # never produced
    state = with_basis(produce_all(state), "A")
    state, _ = apply(state, RequirementTextChanged(requirement="R1", text="Değişti."))
    assert choose_mode(state, "A", Hint(mode="incremental"), {}) == "incremental"
    assert choose_mode(state, "A", None, {}) == "incremental"  # the basis decides, not the hint


def test_card_change_forces_full_even_with_incremental_hint():
    state = with_basis(produce_all(project()), "A")
    state, inv = apply(state, ProjectCardChanged(text="Başka kart."))
    assert inv.hints[SET("A")].mode == "incremental"  # paket 2 hint ignores the cause
    assert choose_mode(state, "A", inv.hints[SET("A")], {}) == "full"


def test_merge_needs_sources():
    state = with_basis(produce_all(project()), "A")
    hint = Hint(mode="merge", sources=(SET("X"), SET("Y")))
    assert choose_mode(state, "A", hint, {SET("X"): [tc("TC-1", "R1")], SET("Y"): []}) == "merge"
    assert choose_mode(state, "A", hint, {SET("X"): [tc("TC-1", "R1")]}) == "incremental"


def test_need_uses_test_method():
    state = produce_all(project())
    state, _ = apply(state, MethodEdited(requirement="R2", methods=("İnceleme",)))
    assert need(state, "A", "Test") == ("R1",)


# Covers, ids, splitting -----------------------------------------------------------------------


def test_filter_covers_drops_foreign_and_non_test_ids():
    out = filter_covers(
        [
            case_json("R1", covers=["R1", "R9", "R1"]),
            case_json("R3", covers=["R3"]),
            case_json("R2", covers=["R2", "R1"]),
        ],
        allowed={"R1"},
    )
    assert [c.covers for c in out.cases] == [("R1",), ("R1",)]
    assert out.dropped_ids == 3  # R9, R3, R2 (the duplicate R1 is not counted)
    assert out.dropped_cases == 1


@pytest.mark.parametrize(
    ("n", "size", "parts"),
    [
        (10, 25, [10]),
        (25, 25, [25]),
        (26, 25, [13, 13]),
        (60, 25, [20, 20, 20]),
        (51, 25, [17, 17, 17]),
        (11, 5, [4, 4, 3]),
    ],
)
def test_split_units_balanced(n, size, parts):
    members = [f"R{i:03d}" for i in range(n, 0, -1)]  # unsorted input
    units = split_units(members, size)
    assert [len(u) for u in units] == parts
    assert [m for u in units for m in u] == sorted(members)


def test_next_ids_and_renumber():
    assert next_ids({"TC-1", "TC-3"}, 3) == ["TC-2", "TC-4", "TC-5"]
    out = renumber([tc("X-R1", "R1"), tc("X-R2", "R2")], taken={"TC-1"})
    assert [c.id for c in out] == ["TC-2", "TC-3"]
    assert [c.covers for c in out] == [("R1",), ("R2",)]


def test_uncovered():
    assert uncovered([tc("TC-1", "R1"), tc("TC-2", "R1", "R3")], ["R3", "R2", "R1"]) == ["R2"]


# Incremental and merge ------------------------------------------------------------------------


def test_prune_removed():
    kept, trimmed = prune_removed(
        [tc("TC-1", "R1"), tc("TC-2", "R2"), tc("TC-3", "R1", "R2")], removed={"R2"}
    )
    assert [(c.id, c.covers) for c in kept] == [("TC-1", ("R1",)), ("TC-3", ("R1",))]
    assert trimmed == ["TC-3"]


def test_apply_incremental_keeps_identity():
    existing = [tc("TC-1", "R1"), tc("TC-2", "R2")]
    out, ignored = apply_incremental(
        existing,
        add=[tc("TC-1", "R3", title="yeni")],  # model reused an id: an add always gets a new id
        update=[tc("TC-2", "R2", title="güncel"), tc("TC-9", "R4"), tc("TC-5", "R1")],
        pinned_ids={"TC-5"},
    )
    assert out[0] == existing[0]  # unchanged: same object content, same id
    assert out[1].id == "TC-2" and out[1].title == "güncel"
    assert [c.id for c in out[2:]] == ["TC-3", "TC-4"]  # adds after TC-1, TC-2 and pinned TC-5
    assert {c.covers for c in out[2:]} == {("R3",), ("R4",)}  # unknown update id → add
    assert ignored == 1


def test_merge_sources_renames_collisions_and_apply_merge_drops():
    merged = merge_sources(
        {SET("B"): [tc("TC-1", "R3")], SET("A"): [tc("TC-1", "R1"), tc("TC-2", "R2")]},
        pinned_ids={"TC-2"},
    )
    assert list(merged) == ["A", "B"]
    assert [c.id for c in merged["A"]] == ["TC-1", "A.TC-2"]
    assert [c.id for c in merged["B"]] == ["B.TC-1"]
    out = apply_merge(merged, drop=["B.TC-1", "nope"])
    assert [c.id for c in out] == ["TC-1", "A.TC-2"]
