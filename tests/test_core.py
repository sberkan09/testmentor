import json

import pytest
from pydantic import ValidationError

from core.clustering import build_tree
from core.hashing import input_hash
from core.metrics import CallStat, ProjectOutcome, RefRequirement, layer1, step_structure_ok
from core.prompts import Method, ProjectCard, classification_messages, generation_messages
from core.schemas import Requirement, case_set_model, method_batch_model

TYPES = ("Normal", "Sınır", "Hata")
PRIOS = ("Yüksek", "Orta", "Düşük")
METHODS = ("Test", "Analiz", "İnceleme", "Gösterim")


def tc(covers, steps=None, **kw):
    base = dict(
        id="T",
        title="t",
        covers=covers,
        type="Normal",
        priority="Orta",
        preconditions="",
        test_inputs="",
        assumptions="",
        steps=steps or [{"no": 1, "action": "a", "expected": "e"}],
    )
    return base | kw


def test_test_case_schema_enforces_labels_and_steps():
    model = case_set_model(TYPES, PRIOS)
    ok = model.model_validate({"test_cases": [tc(["R1"])]})
    assert ok.model_dump(mode="json")["test_cases"][0]["type"] == "Normal"
    with pytest.raises(ValidationError):
        model.model_validate({"test_cases": [tc(["R1"], type="Smoke")]})
    with pytest.raises(ValidationError):
        model.model_validate({"test_cases": [tc(["R1"], steps=[{"no": 1, "action": "a"}])]})
    schema = model.model_json_schema()
    assert "Sınır" in json.dumps(schema, ensure_ascii=False)


def test_method_schema():
    model = method_batch_model(METHODS)
    model.model_validate(
        {"decisions": [{"requirement_id": "R1", "methods": ["Test", "Analiz"], "rationale": "x"}]}
    )
    with pytest.raises(ValidationError):
        model.model_validate(
            {"decisions": [{"requirement_id": "R1", "methods": [], "rationale": ""}]}
        )


CARD = ProjectCard("P", "Proje", "Alan", tuple(Method(m, f"{m} ölçütü") for m in METHODS))
EXAMPLES = {
    "requirements": [{"id": "EX-1", "text": "x", "language": "tr", "methods": ["Test"]}],
    "output": {"test_cases": [tc(["EX-1"])]},
}


def gen(reqs, methods, **kw):
    return generation_messages(
        CARD,
        reqs,
        methods,
        schema={"type": "object"},
        examples=EXAMPLES,
        test_method="Test",
        types=TYPES,
        priorities=PRIOS,
        **kw,
    )


def test_prompt_prefix_is_stable_and_ordered():
    r1, r2 = (
        Requirement(id="R2", text="b", language="en"),
        Requirement(id="R1", text="a", language="tr"),
    )
    a = gen([r1, r2], {"R1": ["Test"], "R2": ["Analiz"]})
    b = gen([Requirement(id="R9", text="z", language="tr")], {"R9": ["Test"]})
    user_a, user_b = a[1]["content"], b[1]["content"]
    assert a[0] == b[0]
    prefix = user_a[: user_a.index("# Requirements")]
    assert user_b.startswith(prefix)  # layers 1-4 identical across clusters of a project
    assert user_a.index("R1 (tr)") < user_a.index("R2 (en)")  # deterministic order
    order = [
        user_a.index(h)
        for h in (
            "# Project card",
            "# Task",
            "# Output schema",
            "# Example",
            "# Retrieved passages",
            "# Requirements",
        )
    ]
    assert order == sorted(order)
    c = classification_messages(CARD, [r1], schema={"type": "object"})
    assert c[0] == a[0] and c[1]["content"].startswith(CARD.render())


def test_repair_instruction_goes_last():
    m = gen([Requirement(id="R1", text="a")], {"R1": ["Test"]}, only_ids=["R1"])
    content = m[1]["content"]
    assert content.rindex("# Additional instruction") > content.index("# Requirements")


def test_input_hash_changes_with_version_and_params():
    base = dict(inputs=["a"], prompt_version="p1", model="m", params={"t": 0})
    h = input_hash(**base)
    assert h == input_hash(**base)
    assert h != input_hash(**(base | {"prompt_version": "p2"}))
    assert h != input_hash(**(base | {"params": {"t": 1}}))


def test_clustering_deterministic_and_cut():
    ids = ["c", "a", "b", "d"]
    vecs = [[1, 0], [1, 0.05], [0, 1], [0.05, 1]]
    tree = build_tree(ids, vecs)
    assert tree.cut(0.3) == [["a", "c"], ["b", "d"]]
    assert tree.cut(1.5) == [["a", "b", "c", "d"]]
    assert tree.cut(1.5, max_cluster_size=3) == [["a", "b", "c"], ["d"]]


def test_step_structure():
    assert step_structure_ok(tc(["R"]))
    assert not step_structure_ok(tc(["R"], steps=[{"no": 2, "action": "a", "expected": "e"}]))
    assert not step_structure_ok(tc(["R"], steps=[{"no": 1, "action": "a", "expected": " "}]))


def test_layer1_metrics():
    refs = {
        "A": RefRequirement("A", "P", "tr", frozenset({"Test"}), "k1"),
        "B": RefRequirement("B", "P", "en", frozenset({"Test"}), "k1"),
        "C": RefRequirement("C", "P", "en", frozenset({"İnceleme"}), "k2", trap=True),
    }
    outcome = ProjectOutcome(
        project="P",
        clusters=[["A", "B"], ["C"]],
        methods={"A": ["Test"], "B": ["Test", "Analiz"], "C": ["İnceleme"]},
        test_cases=[tc(["A"]), tc(["C"])],
        covered_before_repair={"A"},
    )
    calls = [
        CallStat("generation", True, False, 100, 50, 80, 0.1, 1.0),
        CallStat("classification", False, False, 100, 10, None, 0.1, 1.0),
    ]
    m = layer1([outcome], refs, calls, wall_s=2.0, test_method="Test")
    a = m["all"]
    assert a["coverage_rate"] == 0.5 and a["no_test_violations"] == 1
    assert a["method_exact_match"] == round(2 / 3, 4)
    assert a["method_jaccard"] == round((1 + 0.5 + 1) / 3, 4)
    assert m["by_language"]["tr"]["coverage_rate"] == 1.0
    assert m["traps"]["requirements"] == 1
    assert m["cluster_ari"] == 1.0
    assert m["calls"]["schema_valid_rate"] == 0.5
    assert m["calls"]["tokens_per_second"] == 30.0


def test_empty_test_case_set_rejected():
    model = case_set_model(TYPES, PRIOS)
    with pytest.raises(ValidationError):
        model.model_validate({"test_cases": []})
    assert model.model_json_schema()["properties"]["test_cases"]["minItems"] == 1


def test_coverage_against_predicted_methods():
    """Bitti ölçütü 3 (paket 3): end to end, coverage counts the requirements whose predicted
    methods include Test."""
    from core.metrics import ProjectOutcome, RefRequirement, requirement_metrics

    refs = {
        "R1": RefRequirement("R1", "P", "tr", frozenset({"Test"}), "a"),
        "R2": RefRequirement("R2", "P", "tr", frozenset({"Test"}), "a"),
    }
    tc = {"covers": ["R1"], "steps": [{"no": 1, "action": "a", "expected": "e"}]}
    o = ProjectOutcome("P", [], {"R1": ["Test"], "R2": ["İnceleme"]}, [tc])
    m = requirement_metrics([o], refs, "Test")
    assert m["coverage_rate"] == 0.5 and m["coverage_rate_predicted"] == 1.0
