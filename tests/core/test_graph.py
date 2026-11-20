"""Graph construction, declared dependencies and hash inputs."""

import pytest

from core.graph import cache_key, dependents, expected_hash, new_project, upstream
from core.invalidation import analyze
from core.nodes import (
    PROJECT_CARD_KEY,
    ClusterContent,
    NodeKind,
    RequirementContent,
    Status,
    ref,
)
from core.stages import all_specs
from tests.core.helpers import (
    CLUSTERS,
    CONFIGS,
    EMB,
    LABEL,
    METHOD,
    MX,
    PID,
    REQ,
    REQ_TEXTS,
    RET,
    SET,
    TC,
    TREE,
)

CARD = ref(NodeKind.PROJECT_CARD, PROJECT_CARD_KEY)
INDEX = ref(NodeKind.KB_INDEX, "index")


def _new(**overrides):
    args = dict(
        requirements=[RequirementContent(id=k, text=v) for k, v in REQ_TEXTS.items()],
        clusters=CLUSTERS,
        card="Kart",
        index_version="v1",
        stage_configs=CONFIGS,
    )
    return new_project(PID, **(args | overrides))


def test_stages_registered_in_topological_order():
    kinds = [s.kind for s in all_specs()]
    assert kinds == [
        NodeKind.EMBEDDING,
        NodeKind.CLUSTERING,
        NodeKind.METHOD,
        NodeKind.CLUSTER_LABEL,
        NodeKind.RETRIEVAL,
        NodeKind.TEST_SET,
        NodeKind.MATRIX_ROW,
    ]
    assert {s.kind for s in all_specs() if s.uses_llm} == {
        NodeKind.METHOD,
        NodeKind.CLUSTER_LABEL,
        NodeKind.TEST_SET,
    }


def test_new_project_creates_stale_placeholders():
    state = _new()
    a = analyze(state)
    assert a.llm_calls == 6 + 3 + 3  # methods, labels, sets
    assert state.node(SET("A")).content is None
    assert state.node(SET("A")).status == Status.STALE
    assert state.node(REQ("R1")).status == Status.FRESH
    assert set(a.ready) == {EMB(f"R{i}") for i in range(1, 7)} | {
        METHOD(f"R{i}") for i in range(1, 7)
    } | {LABEL(k) for k in CLUSTERS} | {RET(k) for k in CLUSTERS}


@pytest.mark.parametrize(
    "overrides",
    [
        {"clusters": {"A": ("R1", "R2"), "B": ("R2", "R3", "R4"), "C": ("R5", "R6")}},
        {"clusters": {"A": ("R1",), "B": ("R3", "R4"), "C": ("R5", "R6")}},
        {"stage_configs": {k: v for k, v in CONFIGS.items() if k != NodeKind.TEST_SET}},
    ],
    ids=["requirement-in-two-clusters", "requirement-in-no-cluster", "missing-stage-config"],
)
def test_new_project_rejects_inconsistent_input(overrides):
    with pytest.raises(ValueError):
        _new(**overrides)


def test_declared_dependencies(project):
    state, _ = project
    assert upstream(state, SET("A")) == (
        REQ("R1"), REQ("R2"), METHOD("R1"), METHOD("R2"), RET("A"), CARD,
    )  # fmt: skip
    assert upstream(state, LABEL("A")) == (REQ("R1"), REQ("R2"), CARD)
    assert upstream(state, RET("A")) == (REQ("R1"), REQ("R2"), INDEX)
    assert upstream(state, METHOD("R1")) == (REQ("R1"), CARD)
    assert upstream(state, EMB("R1")) == (REQ("R1"),)
    assert upstream(state, TREE) == tuple(EMB(f"R{i}") for i in range(1, 7))
    assert upstream(state, MX("R1")) == (REQ("R1"), METHOD("R1"), TC("A", "R1"))
    assert upstream(state, TC("A", "R1")) == (SET("A"),)
    assert upstream(state, REQ("R1")) == ()


def test_dependents_reverse_upstream(project):
    state, _ = project
    assert dependents(state, SET("A")) == {TC("A", "R1"), TC("A", "R2")}
    assert dependents(state, REQ("R1")) == {
        EMB("R1"), METHOD("R1"), LABEL("A"), RET("A"), SET("A"), MX("R1"),
    }  # fmt: skip
    assert dependents(state, LABEL("A")) == frozenset()  # the name feeds nothing


def test_hash_ignores_member_order_and_cluster_name(project):
    state, _ = project
    h = expected_hash(state, SET("A"))
    swapped = state.model_copy(
        update={
            "nodes": state.nodes
            | {
                ref(NodeKind.CLUSTER, "A"): state.node(ref(NodeKind.CLUSTER, "A")).model_copy(
                    update={"content": ClusterContent(members=("R2", "R1"))}
                )
            }
        }
    )
    assert expected_hash(swapped, SET("A")) == h
    assert state.node(SET("A")).input_hash == h


@pytest.mark.parametrize("field", ["prompt_version", "model", "params"])
def test_hash_includes_stage_config(project, field):
    state, _ = project
    cfg = CONFIGS[NodeKind.TEST_SET]
    value = {"prompt_version": "t9", "model": "other", "params": {"temperature": 0.7}}[field]
    changed = state.model_copy(
        update={
            "stage_configs": state.stage_configs
            | {NodeKind.TEST_SET: cfg.model_copy(update={field: value})}
        }
    )
    assert expected_hash(changed, SET("A")) != expected_hash(state, SET("A"))
    assert expected_hash(changed, LABEL("A")) == expected_hash(state, LABEL("A"))


def test_nodes_record_their_cache_key(project):
    state, _ = project
    assert cache_key(state, SET("A")) == state.node(SET("A")).cache_key
    assert cache_key(state, LABEL("A")) == state.node(LABEL("A")).cache_key
