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

Paket 3: every production mode of the test set (full, incremental, merge, repair, schema retry)
uses layers 1–5 byte for byte as full generation does (`generation_messages`, unchanged since
paket 1 so the paket 1 baseline stays comparable); mode material goes after layer 5 through
`append_tail`. Versions are per stage (`prompt_version`, docs/tasarim.md Veri modeli kuralları).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from core.nodes import NodeKind, ProjectCardContent, TestCaseContent
from core.schemas import Requirement
from core.settings import StageSettings

TEMPLATE_VERSION = "t2"  # t2: test_cases has at least one item. Removed in paket 3 step 5 (eval).

# Versions (paket 3) ------------------------------------------------------------------------------

SHARED_VERSION = "s1"
"""System instruction and card rendering (layers 1–2); shared by every model stage."""

STAGE_VERSIONS: dict[NodeKind, str] = {
    NodeKind.METHOD: "m1",
    NodeKind.CLUSTER_LABEL: "l1",
    NodeKind.TEST_SET: "g3",  # g3: t2 prompt plus mode tails (incremental, merge, pinned, retry)
}
"""Template version per model stage. Bump when the dynamic rendering (requirement block, tails)
changes; tests/stages/test_prompts.py pins a rendering hash per version."""

FINGERPRINT_LENGTH = 12

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


class RenderableCard(Protocol):
    def render(self) -> str: ...


@dataclass(frozen=True)
class ContentCard:
    """The project card node as a prompt layer (`render_card`)."""

    content: ProjectCardContent

    def render(self) -> str:
        return render_card(self.content)


def card_text(key: str, name: str, domain: str) -> str:
    """Card body of a golden-set project: `Project: <name> (<key>)` and `Domain: <domain>` lines.
    With it, `render_card` equals `ProjectCard(key, name, domain, methods).render()`."""
    raise NotImplementedError("paket 3 adım 4")


def render_card(content: ProjectCardContent) -> str:
    """`# Project card`, the body text, then `Verification methods (choose only from this list):`
    and one `- <name>: <criterion>` line per method in the card's order (the order is the
    project's, kept stable). Byte-identical to `ProjectCard.render` for the same data."""
    raise NotImplementedError("paket 3 adım 4")


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
    card: RenderableCard,
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
    card: RenderableCard, reqs: Sequence[Requirement], *, schema: Mapping[str, Any]
) -> list[dict[str, str]]:
    layer3 = f"{CLASSIFICATION_INSTRUCTION}\n\n# Output schema\n{_json(schema)}"
    layer5 = "# Requirements\n" + _requirements_block(reqs, {})
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{card.render()}\n\n{layer3}\n\n{layer5}"},
    ]


# Paket 3: cluster label, mode tails, versions ----------------------------------------------------

LABEL_INSTRUCTION = (
    "# Task: cluster name\n"
    "Name the cluster formed by the requirements below.\n"
    "- name: 3 to 6 words that say what the requirements have in common; no ids, no "
    "punctuation at the end.\n"
    "- rationale: one sentence on why these requirements belong together.\n"
    "- Write both in the language most of the requirements use; on a tie, in the language of "
    "the requirement with the smallest id."
)

PINNED_HEADER = (
    "# Fixed test cases\n"
    "The user wrote or approved these test cases. They are part of the set and cannot be "
    "changed. Do not repeat them and do not write test cases that check the same thing; "
    "write only what they do not already cover."
)

INCREMENTAL_INSTRUCTION = (
    "# Change\n"
    "The test cases above already exist for this cluster. Requirements were added, changed or "
    "removed (listed below). Do not rewrite the set. Return only:\n"
    "- add: new test cases for requirements that are not covered yet or whose new text needs "
    "a test the set does not have;\n"
    "- update: the complete new version of an existing test case whose content no longer "
    "matches its requirements, with that test case's id.\n"
    "Leave both lists empty if nothing needs to change. Answer with JSON that matches this "
    "schema:"
)

MERGE_INSTRUCTION = (
    "# Merge\n"
    "Two clusters were merged; their test cases are listed above. Find test cases that check "
    "the same behaviour as another one in the list and return their ids in drop. Keep the more "
    "complete one of each pair. Do not drop a test case only because it is similar. Answer "
    "with JSON that matches this schema:"
)

SCHEMA_RETRY_INSTRUCTION = (
    "# Correction\nYour previous answer did not match the output schema. Error:"
)


def label_messages(
    card: RenderableCard, reqs: Sequence[Requirement], *, schema: Mapping[str, Any]
) -> list[dict[str, str]]:
    """Layers 1–2 shared with every stage, layer 3 `LABEL_INSTRUCTION` and the schema, layer 5
    the member requirements (no methods tag). No passages layer."""
    raise NotImplementedError("paket 3 adım 4")


def append_tail(messages: Sequence[dict[str, str]], *sections: str) -> list[dict[str, str]]:
    """Copy of `messages` with each non-empty section appended to the last user message, each
    preceded by a blank line (`"\n\n" + section`). The prefix is never touched."""
    raise NotImplementedError("paket 3 adım 4")


def case_summary(case: TestCaseContent) -> str:
    """`<id> [covers: R1, R2]: <title>`; used for existing cases that a change does not touch."""
    raise NotImplementedError("paket 3 adım 4")


def case_block(cases: Sequence[TestCaseContent]) -> str:
    """Full JSON of each case (one compact `_json` line per case, in the given order)."""
    raise NotImplementedError("paket 3 adım 4")


def pinned_section(cases: Sequence[TestCaseContent]) -> str:
    """`PINNED_HEADER` and `case_block(cases)` in id order; empty string when there are none."""
    raise NotImplementedError("paket 3 adım 4")


def incremental_section(
    *,
    full: Sequence[TestCaseContent],
    summary: Sequence[TestCaseContent],
    added: Sequence[str],
    changed: Sequence[str],
    removed: Sequence[str],
    schema: Mapping[str, Any],
) -> str:
    """`# Existing test cases` with `full` as `case_block` (cases touching a changed or removed
    requirement) and `summary` as `case_summary` lines (the rest), both in id order; then
    `INCREMENTAL_INSTRUCTION`, the schema as `_json`, and the sorted `Added:`, `Changed:`,
    `Removed:` id lines (a line is left out when its list is empty)."""
    raise NotImplementedError("paket 3 adım 4")


def merge_section(
    sources: Mapping[str, Sequence[TestCaseContent]], *, schema: Mapping[str, Any]
) -> str:
    """`# Existing test cases` grouped by source cluster in key order (`## <cluster>` and
    `case_block`), then `MERGE_INSTRUCTION` and the schema. Ids are the merged ids (collisions
    already renamed `<cluster>.<id>`)."""
    raise NotImplementedError("paket 3 adım 4")


def repair_section(ids: Sequence[str]) -> str:
    """Exactly the paket 1 repair text (`generation_messages(..., only_ids=ids)` tail without
    its leading blank line): `# Additional instruction` and the sorted ids."""
    raise NotImplementedError("paket 3 adım 4")


def schema_retry_section(error: str) -> str:
    """`SCHEMA_RETRY_INSTRUCTION`, the error (first 1.000 characters), and `Answer again.`"""
    raise NotImplementedError("paket 3 adım 4")


def layer3(stage: NodeKind, settings: StageSettings) -> str:
    """The stage's fixed layer 3 rendered with `settings`: test set `GENERATION_INSTRUCTION`
    with labels, the case set schema and the examples (as in `generation_messages`); method
    `CLASSIFICATION_INSTRUCTION` and its schema; label `LABEL_INSTRUCTION` and its schema. The
    method enum comes from the project card (a dependency, already in `input_hash`); the
    method schema is rendered here with the placeholder list `("<method>",)`."""
    raise NotImplementedError("paket 3 adım 4")


def prompt_version(stage: NodeKind, settings: StageSettings) -> str:
    """`<SHARED_VERSION>.<STAGE_VERSIONS[stage]>+<fingerprint>`; fingerprint = first
    `FINGERPRINT_LENGTH` hex chars of SHA-256 over `SYSTEM` and `layer3(stage, settings)`.
    KeyError for a stage without a template (non-model stages take their version from config)."""
    raise NotImplementedError("paket 3 adım 4")
