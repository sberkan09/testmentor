import json

import pytest
from pydantic import ValidationError

from eval.golden_v1 import (
    ProjectV1,
    load_golden_v1,
    load_project,
    project_paths,
    validate_project,
)

REQ = {
    "id": "ETC-001",
    "language": "en",
    "text": "The on-board equipment shall report its position as defined in SUBSET-026 §3.6.5.1.4.",
    "source": {"doc": "SUBSET-026-3", "section": "3.6.5.1.4", "clauses": ["3.6.5.1.4"]},
    "stratum": "core",
    "split": "dev",
    "reference_origin": "official_tagged",
    "reference_candidates": ["3060500/TC1"],
    "reference_cluster": "Position reporting",
    "verification_methods": ["Test"],
    "method_rationale": "Not in SUBSET-076-7 Table 3; official test case exists.",
}


def project(*reqs, key="ETC"):
    return ProjectV1.model_validate(
        {"key": key, "name": "OBU", "domain": "Railway", "requirements": list(reqs)}
    )


def test_valid_requirement_passes_cross_checks():
    assert validate_project(project(REQ)) == []


def test_cross_file_rules():
    bad = project(
        REQ | {"source": {"doc": "SUBSET-026 v4.0.0", "section": "x"}},
        REQ | {"id": "ETC-002", "verification_methods": ["Proof"]},
        REQ | {"id": "ETC-003", "stratum": "non_testable"},
        REQ
        | {
            "id": "ETC-004",
            "support_passages": [
                {"id": "P1", "doc": "SUBSET-076-7", "section": "T3", "text": "answer key"}
            ],
            "reference_checks": [{"action": "a", "expected": "e", "passages": ["P9"]}],
        },
    )
    problems = validate_project(bad)
    assert any("not a manifest id" in p for p in problems)
    assert any("unknown methods" in p for p in problems)
    assert any("non_testable" in p for p in problems)
    assert any("non-corpus document" in p for p in problems)
    assert any("unknown passages" in p for p in problems)


def test_cluster_size_limit():
    reqs = [REQ | {"id": f"ETC-{i:03d}"} for i in range(1, 27)]
    assert any("limit 25" in p for p in validate_project(project(*reqs)))


def test_schema_rules():
    with pytest.raises(ValidationError):
        project(REQ, REQ)  # duplicate id
    with pytest.raises(ValidationError):
        project(REQ, key="KDH")  # id outside project
    with pytest.raises(ValidationError):
        project(REQ | {"reference_candidates": []})
    with pytest.raises(ValidationError):
        project(REQ | {"split": "test"})


def test_loads_into_golden(tmp_path):
    (tmp_path / "etc.json").write_text(
        json.dumps({"key": "ETC", "name": "OBU", "domain": "Railway", "requirements": [REQ]})
    )
    g = load_golden_v1(tmp_path)
    assert g.version == "v1" and g.projects[0].requirements[0].id == "ETC-001"
    assert g.refs()["ETC-001"].methods == frozenset({"Test"})
    assert g.projects[0].reference_clusters() == [["ETC-001"]]


def test_repository_v1_files_are_valid():
    for path in project_paths():
        p = load_project(path)
        assert p.key.lower() == path.stem
        assert validate_project(p) == [], path


def test_passage_and_basis_texts_are_verified():
    from eval.golden_v1 import CorpusTexts

    texts = CorpusTexts.__new__(CorpusTexts)
    texts.ok = True
    texts.full = {
        "SUBSET-026-3": ["the obu shall report"],
        "SUBSET-076-5-2": ["Check on the RTM that x"],
    }
    texts.writer = {"SUBSET-026-3": ["the obu shall report"]}
    check = {
        "action": "a",
        "expected": "e",
        "clause": "3.6.5.1.4",
        "passages": ["P1"],
        "needs_documents": True,
        "basis": {"doc": "SUBSET-076-5-2", "ref": "3060500/TC1", "text": "Check on the  RTM … x"},
    }
    good = REQ | {
        "needs_documents": True,
        "support_passages": [
            {"id": "P1", "doc": "SUBSET-026-3", "section": "s", "text": "obu shall"}
        ],
        "reference_checks": [check],
    }
    assert validate_project(project(good), texts=texts) == []
    bad = good | {
        "needs_documents": False,
        "support_passages": [
            {"id": "P1", "doc": "SUBSET-026-3", "section": "s", "text": "invented"}
        ],
        "reference_checks": [
            check | {"clause": "3.9.9", "basis": check["basis"] | {"text": "not there"}},
            check | {"basis": None},
        ],
    }
    problems = validate_project(project(bad), texts=texts)
    for frag in (
        "not found in writer view",
        "basis text not found",
        "outside source.clauses",
        "has no basis",
        "disagrees",
    ):
        assert any(frag in p for p in problems), frag
