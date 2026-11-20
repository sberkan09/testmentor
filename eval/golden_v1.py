"""Golden set v1 (paket 1b): requirements derived from a public document corpus.

One file per project: `eval/golden/v1/<project>.json`. Stage 4 writes requirements; stage 5 adds
reference checks, support passages and `needs_documents`. `load_golden_v1` returns the same
`Golden` structure as v0, so the runner and `make batch` work unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.schemas import Requirement
from eval.corpus.manifest import Role, load_manifest
from eval.golden import Golden, GoldenProject

ROOT = Path(__file__).resolve().parent.parent
V1_DIR = Path(__file__).resolve().parent / "golden" / "v1"

Origin = Literal["official", "official_tagged", "claude"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    doc: str  # manifest document id
    section: str
    clauses: list[str] = []  # clauses the requirement covers (ERTMS: SRS clause numbers)


class Passage(Strict):
    id: str
    doc: str  # manifest document id; must be writer-visible (role corpus)
    section: str
    text: str


class Check(Strict):
    action: str
    expected: str
    clause: str = ""  # SRS clause the step verifies (ERTMS, step-level judging unit)
    channel_note: str = ""  # interface detail kept apart from the behaviour (RTM, JRU, DMI)
    passages: list[str] = []  # support passage ids needed to write this check
    not_in_corpus: bool = False  # the expected result relies on text outside the corpus


class RequirementV1(Strict):
    id: str = Field(pattern=r"^[A-Z]{2,5}-\d{3}$")
    language: Literal["tr", "en"]
    text: str = Field(min_length=20)
    source: Source
    stratum: Literal["core", "non_testable", "control"]
    split: Literal["dev", "holdout"]
    reference_origin: Origin
    reference_candidates: list[str] = Field(min_length=1)  # TC ids, criteria, rules, measures
    reference_cluster: str
    verification_methods: list[str] = Field(min_length=1)
    method_rationale: str
    difficulty: Literal["Kolay", "Orta", "Zor"] = "Orta"
    note: str = ""
    # stage 5
    needs_documents: bool | None = None
    reference_preconditions: str = ""
    reference_checks: list[Check] = []
    support_passages: list[Passage] = []


class ProjectV1(Strict):
    key: str = Field(pattern=r"^[A-Z]{2,5}$")
    name: str
    domain: str
    version: Literal["v1"] = "v1"
    requirements: list[RequirementV1]

    @model_validator(mode="after")
    def _ids(self) -> ProjectV1:
        ids = [r.id for r in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate requirement ids")
        bad = [i for i in ids if not i.startswith(self.key + "-")]
        if bad:
            raise ValueError(f"ids outside project {self.key}: {bad[:3]}")
        return self


def pipeline_config(root: Path = ROOT) -> dict:
    return yaml.safe_load((root / "config" / "pipeline.yaml").read_text(encoding="utf-8"))


def validate_project(p: ProjectV1, root: Path = ROOT) -> list[str]:
    """Cross-file rules; returns problems (empty list = valid)."""
    cfg = pipeline_config(root)
    methods = {m["name"] for m in cfg["methods"]}
    limit = int(cfg["clustering"]["max_cluster_size"])
    manifest = load_manifest(root / "eval" / "corpus" / p.key.lower() / "manifest.yaml")
    roles = {d.id: d.role for d in manifest.documents}
    problems: list[str] = []
    clusters: dict[str, int] = {}
    for r in p.requirements:
        where = r.id
        if r.source.doc not in roles:
            problems.append(f"{where}: source.doc {r.source.doc!r} is not a manifest id")
        if unknown := set(r.verification_methods) - methods:
            problems.append(f"{where}: unknown methods {sorted(unknown)}")
        if r.stratum == "non_testable" and cfg["test_method"] in r.verification_methods:
            if len(r.verification_methods) == 1:
                problems.append(f"{where}: non_testable requirement with Test as only method")
        for ps in r.support_passages:
            if roles.get(ps.doc) != Role.corpus:
                problems.append(f"{where}: passage {ps.id} from non-corpus document {ps.doc!r}")
        ids = {ps.id for ps in r.support_passages}
        for c in r.reference_checks:
            if missing := set(c.passages) - ids:
                problems.append(f"{where}: check cites unknown passages {sorted(missing)}")
        clusters[r.reference_cluster] = clusters.get(r.reference_cluster, 0) + 1
    for name, n in clusters.items():
        if n > limit:
            problems.append(f"cluster {name!r} has {n} requirements (limit {limit})")
    return problems


def project_paths(directory: Path = V1_DIR) -> list[Path]:
    return sorted(directory.glob("*.json"))


def load_project(path: Path) -> ProjectV1:
    return ProjectV1.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_golden_v1(directory: Path = V1_DIR, projects: list[str] | None = None) -> Golden:
    selected = []
    for path in project_paths(directory):
        p = load_project(path)
        if projects and p.key not in projects:
            continue
        reqs = tuple(
            Requirement(id=r.id, text=r.text, language=r.language)
            for r in sorted(p.requirements, key=lambda r: r.id)
        )
        raw = p.model_dump()
        raw["test_cases"] = []  # stage 5 references are checks per requirement, not test cases
        selected.append(GoldenProject(p.key, p.name, p.domain, reqs, raw))
    return Golden("v1", tuple(selected))
