"""The matrix as clients see it (paket 4): one row per requirement, read from the project state
the way the matrix stage reads it, so the view is right even while a row node is stale."""

from __future__ import annotations

from core.graph import ProjectState
from core.nodes import ClusterLabelContent, MethodContent, NodeKind, NodeRef
from worker.contracts import MatrixRowView


def cluster_name(state: ProjectState, cluster: str) -> str:
    """The produced cluster name, the cluster key while there is none."""
    node = state.get(NodeRef(kind=NodeKind.CLUSTER_LABEL, key=cluster))
    if node is not None and isinstance(node.content, ClusterLabelContent):
        return node.content.name
    return cluster


def matrix_rows(state: ProjectState, test_method: str) -> list[MatrixRowView]:
    """Rows in requirement id order. Warnings (docs/tasarim.md, Matris): the methods include
    `test_method` but no test case covers the requirement (`test_without_case`), or they do not
    include it but a case covers it (`case_without_test_method`). A requirement whose method
    node has no content has no methods and no warning."""
    rows: list[MatrixRowView] = []
    for rid in state.keys_of(NodeKind.REQUIREMENT):
        req = state.requirement(rid)
        method = state.get(NodeRef(kind=NodeKind.METHOD, key=rid))
        methods = (
            method.content.methods if method and isinstance(method.content, MethodContent) else ()
        )
        keys = tuple(c.key for c in state.cases_covering(rid))
        covered = bool(keys)
        warning = ""
        if methods and test_method in methods and not covered:
            warning = "test_without_case"
        elif methods and test_method not in methods and covered:
            warning = "case_without_test_method"
        cluster = state.cluster_of(rid) or ""
        rows.append(
            MatrixRowView(
                requirement_id=rid,
                text=req.text,
                language=req.language,
                cluster=cluster,
                cluster_name=cluster_name(state, cluster) if cluster else "",
                methods=tuple(methods),
                test_case_keys=keys,
                covered=covered,
                warning=warning,  # type: ignore[arg-type]
            )
        )
    return rows
