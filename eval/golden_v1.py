"""Golden set v1 (paket 1b): requirements derived from a public document corpus.

One file per project: `eval/golden/v1/<project>.json`. Stage 4 writes requirements; stage 5 adds
reference checks, support passages and `needs_documents`. `load_golden_v1` returns the same
`Golden` structure as v0, so the runner and `make batch` work unchanged.
"""

from __future__ import annotations

import json
import re
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


class Basis(Strict):
    """Where an official check comes from; `text` is quoted verbatim from the reference document
    (whitespace-insensitive; separate quoted segments with " … ")."""

    doc: str  # manifest document id of the reference (e.g. SUBSET-076-5-2, NIST-800-63-4-CC)
    ref: str  # test case / criterion / rule / measure / objective id
    text: str


class Check(Strict):
    action: str  # shown to the judge
    expected: str  # shown to the judge: one observable outcome
    clause: str = ""  # clause the step verifies (ERTMS step-level unit); must be in source.clauses
    channel_note: str = (
        ""  # interface detail kept apart from the behaviour (RTM, JRU, DMI); not judged
    )
    basis: Basis | None = None  # required unless reference_origin is claude
    passages: list[str] = []  # support passage ids needed to write this check
    needs_documents: bool | None = None  # cannot be written from the requirement text alone
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
    needs_documents: bool | None = None  # any check needs documents
    reference_note: str = ""  # stage 5: dropped out-of-scope checks, defects found, gaps
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


class CorpusTexts:
    """Extracted corpus texts from the cache (python -m eval.corpus fetch), whitespace-normalised.
    Absent cache → text checks are skipped (unit tests without network)."""

    def __init__(self, project: str, root: Path = ROOT) -> None:
        base = root / "eval" / "corpus" / "cache" / project.lower()
        index_path = base / "index.json"
        self.ok = index_path.exists()
        self.full: dict[str, list[str]] = {}
        self.writer: dict[str, list[str]] = {}
        if not self.ok:
            return
        for doc, v in json.loads(index_path.read_text(encoding="utf-8")).items():
            for e in v["texts"]:
                self.full.setdefault(doc, []).append(
                    _flat((base / e["file"]).read_text(encoding="utf-8"))
                )
                wf = e.get("writer_file") or (e["file"] if v["role"] == "corpus" else None)
                if wf:
                    self.writer.setdefault(doc, []).append(
                        _flat((base / wf).read_text(encoding="utf-8"))
                    )

    def __bool__(self) -> bool:
        return self.ok

    def contains(self, doc: str, text: str, writer: bool = False) -> bool:
        pool = (self.writer if writer else self.full).get(doc, [])
        segments = [_norm(t) for t in re.split(r"\s*(?:…|\[\.\.\.\])\s*", text) if t.strip()]
        return bool(segments) and all(any(seg in t for t in pool) for seg in segments)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _flat(text: str) -> str:
    """Normalised text; for JSON documents (OSCAL) the string values joined, so quoted prose
    matches without JSON escapes."""
    if text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return _norm(text)
        out: list[str] = []

        def walk(n: object) -> None:
            if isinstance(n, str):
                out.append(n)
            elif isinstance(n, dict):
                for v in n.values():
                    walk(v)
            elif isinstance(n, list):
                for v in n:
                    walk(v)

        walk(data)
        return _norm("\n".join(out))
    return _norm(text)


def validate_project(
    p: ProjectV1, root: Path = ROOT, texts: CorpusTexts | None = None
) -> list[str]:
    """Cross-file rules; returns problems (empty list = valid)."""
    texts = texts if texts is not None else CorpusTexts(p.key, root)
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
            if roles.get(ps.doc) not in (Role.corpus, Role.mixed):
                problems.append(f"{where}: passage {ps.id} from non-corpus document {ps.doc!r}")
            elif texts and not texts.contains(ps.doc, ps.text, writer=True):
                problems.append(f"{where}: passage {ps.id} not found in writer view of {ps.doc}")
        ids = {ps.id for ps in r.support_passages}
        for n, c in enumerate(r.reference_checks, start=1):
            if missing := set(c.passages) - ids:
                problems.append(f"{where}: check {n} cites unknown passages {sorted(missing)}")
            if r.reference_origin != "claude" and c.basis is None:
                problems.append(f"{where}: check {n} of an official requirement has no basis")
            if c.basis is not None:
                if c.basis.doc not in roles:
                    problems.append(f"{where}: check {n} basis doc {c.basis.doc!r} unknown")
                elif texts and not texts.contains(c.basis.doc, c.basis.text):
                    problems.append(f"{where}: check {n} basis text not found in {c.basis.doc}")
            if c.clause and r.source.clauses and c.clause not in r.source.clauses:
                problems.append(f"{where}: check {n} clause {c.clause} outside source.clauses")
        if r.reference_checks:
            flags = [c.needs_documents for c in r.reference_checks]
            if r.needs_documents is not None and r.needs_documents != any(bool(f) for f in flags):
                problems.append(f"{where}: needs_documents disagrees with its checks")
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
