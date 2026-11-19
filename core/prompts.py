"""Versioned prompt templates.

Layer order (CLAUDE.md, prompt rules), most stable first so the engine's prefix cache is reused:
1. system instruction (shared by every stage and project)
2. project card (per project)
3. stage instruction, output schema and examples (per stage)
4. retrieved passages (per cluster; none yet)
5. requirements (per call)
Corrections, pinned items and extra instructions are appended after layer 5, never inserted
into the prefix. Nothing variable (dates, counters, user names, unsorted lists) goes into
layers 1–3.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.schemas import Requirement

TEMPLATE_VERSION = "t1"

SYSTEM = (
    "You are a senior test engineer working on safety- and mission-critical software. "
    "You work only from the requirements and project information you are given. "
    "Never invent behaviour, values or interfaces that the requirements do not state; when a "
    "concrete value is needed but not specified, choose one and write it as an assumption. "
    "Write every output in the language of the requirement it belongs to. "
    "Answer only with JSON that matches the given schema."
)


@dataclass(frozen=True)
class Method:
    name: str
    criterion: str


@dataclass(frozen=True)
class ProjectCard:
    key: str
    name: str
    domain: str
    methods: tuple[Method, ...]

    def render(self) -> str:
        lines = [
            "# Project card",
            f"Project: {self.name} ({self.key})",
            f"Domain: {self.domain}",
            "Verification methods (choose only from this list):",
        ]
        lines += [f"- {m.name}: {m.criterion}" for m in self.methods]
        return "\n".join(lines)


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _requirements_block(reqs: Sequence[Requirement], methods: Mapping[str, Sequence[str]]) -> str:
    rows = []
    for r in sorted(reqs, key=lambda r: r.id):
        tag = f" [methods: {', '.join(methods[r.id])}]" if r.id in methods else ""
        rows.append(f"{r.id} ({r.language}){tag}: {r.text}")
    return "\n".join(rows)


GENERATION_INSTRUCTION = (
    "# Task: test cases\n"
    "Write test cases for the requirements of one cluster.\n"
    "- Write tests only for requirements whose methods include {test_method}. Every such "
    "requirement must appear in the covers list of at least one test case. Requirements "
    "without {test_method} are context only: do not write tests for them.\n"
    "- covers lists only requirement ids from this request.\n"
    "- Cover normal behaviour, boundaries and error handling where the requirement implies "
    "them; do not add tests for behaviour the requirement does not state.\n"
    "- Every step has its own action and its own expected result.\n"
    "- Leave preconditions, test_inputs and assumptions as empty strings when not needed.\n"
    "- type is one of {types}; priority is one of {priorities}."
)

CLASSIFICATION_INSTRUCTION = (
    "# Task: verification method\n"
    "Choose the verification method(s) for each requirement from the project card list and "
    "give a one-sentence rationale. Return exactly one decision per requirement, using its id."
)


def generation_messages(
    card: ProjectCard,
    reqs: Sequence[Requirement],
    methods: Mapping[str, Sequence[str]],
    *,
    schema: Mapping[str, Any],
    examples: Mapping[str, Any],
    test_method: str,
    types: Sequence[str],
    priorities: Sequence[str],
    passages: Sequence[str] = (),
    only_ids: Sequence[str] = (),
) -> list[dict[str, str]]:
    stage = GENERATION_INSTRUCTION.format(
        test_method=test_method, types=", ".join(types), priorities=", ".join(priorities)
    )
    ex_reqs = [
        Requirement(**{k: r[k] for k in ("id", "text", "language")})
        for r in examples["requirements"]
    ]
    ex_methods = {r["id"]: r["methods"] for r in examples["requirements"]}
    layer3 = (
        f"{stage}\n\n# Output schema\n{_json(schema)}\n\n# Example\n"
        f"Requirements:\n{_requirements_block(ex_reqs, ex_methods)}\n"
        f"Output:\n{_json(examples['output'])}"
    )
    layer4 = "# Retrieved passages\n" + ("\n\n".join(passages) if passages else "(none)")
    layer5 = "# Requirements\n" + _requirements_block(reqs, methods)
    tail = ""
    if only_ids:
        tail = (
            "\n\n# Additional instruction\nThe requirements "
            + ", ".join(sorted(only_ids))
            + " are not covered yet. Write test cases only for them."
        )
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{card.render()}\n\n{layer3}\n\n{layer4}\n\n{layer5}{tail}"},
    ]


def classification_messages(
    card: ProjectCard, reqs: Sequence[Requirement], *, schema: Mapping[str, Any]
) -> list[dict[str, str]]:
    layer3 = f"{CLASSIFICATION_INSTRUCTION}\n\n# Output schema\n{_json(schema)}"
    layer5 = "# Requirements\n" + _requirements_block(reqs, {})
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{card.render()}\n\n{layer3}\n\n{layer5}"},
    ]
