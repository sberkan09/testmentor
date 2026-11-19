"""Golden set loader (eval/golden/altin-set-v0.json). Synthetic data only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.metrics import RefRequirement
from core.schemas import Requirement

DEFAULT_PATH = Path(__file__).resolve().parent / "golden" / "altin-set-v0.json"


@dataclass(frozen=True)
class GoldenProject:
    key: str
    name: str
    domain: str
    requirements: tuple[Requirement, ...]
    raw: dict[str, Any]

    def reference_clusters(self) -> list[list[str]]:
        groups: dict[str, list[str]] = {}
        for r in self.raw["requirements"]:
            groups.setdefault(r["reference_cluster"], []).append(r["id"])
        return sorted((sorted(g) for g in groups.values()), key=lambda c: c[0])


@dataclass(frozen=True)
class Golden:
    version: str
    projects: tuple[GoldenProject, ...]

    def refs(self) -> dict[str, RefRequirement]:
        out = {}
        for p in self.projects:
            for r in p.raw["requirements"]:
                out[r["id"]] = RefRequirement(
                    id=r["id"],
                    project=p.key,
                    language=r["language"],
                    methods=frozenset(r["verification_methods"]),
                    cluster=r["reference_cluster"],
                    trap=str(r.get("note", "")).startswith("Tuzak"),
                )
        return out

    def reference_tests(self) -> dict[str, list[dict[str, Any]]]:
        """Requirement id → reference test cases covering it."""
        out: dict[str, list[dict[str, Any]]] = {}
        for p in self.projects:
            for tc in p.raw["test_cases"]:
                for rid in tc["covers"]:
                    out.setdefault(rid, []).append(tc)
        return out


def load_golden(path: str | Path = DEFAULT_PATH, projects: list[str] | None = None) -> Golden:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    selected = []
    for p in sorted(data["projects"], key=lambda p: p["key"]):
        if projects and p["key"] not in projects:
            continue
        reqs = tuple(
            Requirement(id=r["id"], text=r["text"], language=r["language"])
            for r in sorted(p["requirements"], key=lambda r: r["id"])
        )
        selected.append(GoldenProject(p["key"], p["name"], p["domain"], reqs, p))
    return Golden(data["version"], tuple(selected))
