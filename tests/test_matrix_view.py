"""core.matrix_view: matrix rows and the two consistency warnings (paket 4)."""

from __future__ import annotations

from typing import Any

from core.graph import ProjectState
from core.matrix_view import matrix_rows
from core.nodes import (
    ClusterLabelContent,
    MethodContent,
    NodeKind,
    NodeRef,
    TestCaseContent,
)
from core.schemas import Step
from tests.stages.helpers import project


def put(state: ProjectState, kind: NodeKind, key: str, content: Any) -> ProjectState:
    ref = NodeRef(kind=kind, key=key)
    node = state.nodes.get(ref)
    if node is None:
        from core.nodes import Node

        node = Node(ref=ref, version=1)
    node = node.model_copy(update={"content": content, "version": 1})
    return state.model_copy(update={"nodes": {**state.nodes, ref: node}})


def case(cid: str, covers: tuple[str, ...]) -> TestCaseContent:
    return TestCaseContent(
        id=cid,
        title=f"Test {cid}",
        covers=covers,
        type="Normal",
        priority="Orta",
        steps=(Step(no=1, action="a", expected="b"),),
    )


def build() -> ProjectState:
    st = project()
    for rid, methods in {
        "R1": ("Test",),
        "R2": ("Test",),
        "R3": ("Analiz",),
        "R4": ("Analiz",),
    }.items():
        st = put(st, NodeKind.METHOD, rid, MethodContent(methods=methods))
    st = put(st, NodeKind.CLUSTER_LABEL, "A", ClusterLabelContent(name="Giriş"))
    st = put(st, NodeKind.TEST_CASE, "A:T0", case("T0", ("R1",)))
    st = put(st, NodeKind.TEST_CASE, "B:T0", case("T0", ("R3",)))
    return st


def test_rows_order_coverage_and_warnings() -> None:
    rows = {r.requirement_id: r for r in matrix_rows(build(), "Test")}
    assert list(rows) == ["R1", "R2", "R3", "R4", "R5", "R6"]
    assert rows["R1"].covered and rows["R1"].warning == ""
    assert rows["R1"].test_case_keys == ("A:T0",)
    assert rows["R2"].warning == "test_without_case" and not rows["R2"].covered
    assert rows["R3"].warning == "case_without_test_method" and rows["R3"].covered
    assert rows["R4"].warning == "" and not rows["R4"].covered


def test_cluster_name_and_fallback() -> None:
    rows = {r.requirement_id: r for r in matrix_rows(build(), "Test")}
    assert (rows["R1"].cluster, rows["R1"].cluster_name) == ("A", "Giriş")
    assert (rows["R3"].cluster, rows["R3"].cluster_name) == ("B", "B")


def test_method_without_content_has_no_methods_and_no_warning() -> None:
    rows = {r.requirement_id: r for r in matrix_rows(build(), "Test")}
    assert rows["R5"].methods == () and rows["R5"].warning == ""
    assert rows["R5"].language == "tr" and rows["R5"].text.startswith("Sistem")
