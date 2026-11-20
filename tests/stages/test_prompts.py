"""Prompt layers and per-stage versions (docs/tasarim.md, Prompt düzeni; Veri modeli kuralları)."""

from __future__ import annotations

import hashlib
import re

import pytest

from core import prompts
from core.nodes import NodeKind, ProjectCardContent
from core.prompts import (
    SYSTEM,
    ContentCard,
    Method,
    ProjectCard,
    append_tail,
    card_text,
    generation_messages,
    label_messages,
    prompt_version,
    render_card,
    repair_section,
)
from core.schemas import ClusterLabel, Requirement, case_set_model
from tests.stages.helpers import CARD_METHODS, EXAMPLES, SETTINGS

MODEL_STAGES = (NodeKind.METHOD, NodeKind.CLUSTER_LABEL, NodeKind.TEST_SET)
REQS = [
    Requirement(
        id="R2",
        text="Sistem, parola sıfırlama bağlantısını 30 dakika geçerli tutmalıdır.",
        language="tr",
    ),
    Requirement(
        id="R1", text="The system shall lock the account after 3 failed logins.", language="en"
    ),
]


def card() -> ContentCard:
    return ContentCard(
        ProjectCardContent(text=card_text("KMU", "Kamu portalı", "Kamu"), methods=CARD_METHODS)
    )


def full_messages(**kw):
    return generation_messages(
        card(),
        REQS,
        {"R1": ["Test"], "R2": ["Test", "İnceleme"]},
        schema=case_set_model(SETTINGS.test_types, SETTINGS.priorities).model_json_schema(),
        examples=EXAMPLES,
        test_method="Test",
        types=SETTINGS.test_types,
        priorities=SETTINGS.priorities,
        **kw,
    )


# Card and layers ------------------------------------------------------------------------------


def test_render_card_equals_paket1_card():
    old = ProjectCard(
        "KMU", "Kamu portalı", "Kamu", tuple(Method(m.name, m.criterion) for m in CARD_METHODS)
    ).render()
    assert render_card(card().content) == old


def test_repair_tail_equals_paket1_repair_prompt():
    assert append_tail(full_messages(), repair_section(["R2", "R1"])) == full_messages(
        only_ids=["R1", "R2"]
    )


def test_append_tail_keeps_prefix_and_skips_empty_sections():
    base = full_messages()
    out = append_tail(base, "# A\nx", "", "# B\ny")
    assert out[0] == base[0]
    assert out[1]["content"] == base[1]["content"] + "\n\n# A\nx\n\n# B\ny"
    assert base == full_messages()  # input not mutated


def test_label_prompt_shares_layers_1_and_2():
    msgs = label_messages(card(), REQS, schema=ClusterLabel.model_json_schema())
    assert msgs[0] == {"role": "system", "content": SYSTEM}
    assert msgs[1]["content"].startswith(card().render() + "\n\n")
    assert msgs[1]["content"].index("R1") < msgs[1]["content"].index("R2")  # id order
    assert "# Task: cluster name" in msgs[1]["content"]


# Versions -------------------------------------------------------------------------------------


def test_prompt_version_format():
    for stage in MODEL_STAGES:
        v = prompt_version(stage, SETTINGS)
        assert re.fullmatch(
            rf"{prompts.SHARED_VERSION}\.{prompts.STAGE_VERSIONS[stage]}\+[0-9a-f]{{12}}", v
        ), v
    with pytest.raises(KeyError):
        prompt_version(NodeKind.EMBEDDING, SETTINGS)


def test_examples_or_labels_change_only_the_test_set_version():
    before = {s: prompt_version(s, SETTINGS) for s in MODEL_STAGES}
    ex = dict(EXAMPLES, output={"test_cases": EXAMPLES["output"]["test_cases"][:1]})
    for changed in (
        SETTINGS.model_copy(update={"examples": ex}),
        SETTINGS.model_copy(update={"test_types": ("Normal", "Hata")}),
    ):
        after = {s: prompt_version(s, changed) for s in MODEL_STAGES}
        assert after[NodeKind.TEST_SET] != before[NodeKind.TEST_SET]
        assert after[NodeKind.METHOD] == before[NodeKind.METHOD]
        assert after[NodeKind.CLUSTER_LABEL] == before[NodeKind.CLUSTER_LABEL]


def test_shared_version_changes_every_model_stage(monkeypatch):
    before = {s: prompt_version(s, SETTINGS) for s in MODEL_STAGES}
    monkeypatch.setattr(prompts, "SHARED_VERSION", "s99")
    assert all(prompt_version(s, SETTINGS) != before[s] for s in MODEL_STAGES)


def test_stage_version_changes_only_that_stage(monkeypatch):
    before = {s: prompt_version(s, SETTINGS) for s in MODEL_STAGES}
    monkeypatch.setitem(prompts.STAGE_VERSIONS, NodeKind.TEST_SET, "g99")
    after = {s: prompt_version(s, SETTINGS) for s in MODEL_STAGES}
    assert after[NodeKind.TEST_SET] != before[NodeKind.TEST_SET]
    assert after[NodeKind.METHOD] == before[NodeKind.METHOD]


# Rendering snapshot: a rendering change without a version bump breaks this test. -----------------
#
# After changing a template's dynamic rendering, bump its version in `core.prompts.STAGE_VERSIONS`
# (or `SHARED_VERSION`) and add the new (stage, version) → hash line that the failure prints.
# Never edit the hash of an existing version.

RENDER_HASHES: dict[tuple[str, str], str] = {
    ("method", "s1.m1"): "f11b68c9892b3bce",
    ("cluster_label", "s1.l1"): "bb68f09522d0a4f1",
    ("test_set", "s1.g3"): "01a6c677cadd67e8",
}


def _render_fixture(stage: NodeKind) -> str:
    from core.nodes import TestCaseContent
    from core.schemas import MergeDecision, Step, incremental_model, method_batch_model

    case = TestCaseContent(
        id="TC-1",
        title="Kilit",
        covers=("R1",),
        type="Normal",
        priority="Orta",
        steps=(Step(no=1, action="Üç kez yanlış parola gir", expected="Hesap kilitlenir"),),
    )
    if stage == NodeKind.TEST_SET:
        inc = incremental_model(SETTINGS.test_types, SETTINGS.priorities).model_json_schema()
        parts = [
            append_tail(full_messages(), prompts.pinned_section([case])),
            append_tail(
                full_messages(),
                prompts.incremental_section(
                    full=[case],
                    summary=[case],
                    added=["R2"],
                    changed=[],
                    removed=["R9"],
                    schema=inc,
                ),
            ),
            append_tail(
                full_messages(),
                prompts.merge_section({"A": [case]}, schema=MergeDecision.model_json_schema()),
            ),
            append_tail(full_messages(), prompts.schema_retry_section("bad")),
        ]
    elif stage == NodeKind.METHOD:
        names = tuple(m.name for m in CARD_METHODS)
        parts = [
            prompts.classification_messages(
                card(), REQS, schema=method_batch_model(names).model_json_schema()
            )
        ]
    else:
        parts = [label_messages(card(), REQS, schema=ClusterLabel.model_json_schema())]
    return repr(parts)


@pytest.mark.parametrize("stage", MODEL_STAGES, ids=lambda s: s.value)
def test_rendering_snapshot_matches_version(stage):
    key = (stage.value, f"{prompts.SHARED_VERSION}.{prompts.STAGE_VERSIONS[stage]}")
    h = hashlib.sha256(_render_fixture(stage).encode("utf-8")).hexdigest()[:16]
    if key not in RENDER_HASHES:
        pytest.fail(f"add to RENDER_HASHES: {key!r}: {h!r}")
    assert RENDER_HASHES[key] == h, "rendering changed: bump the template version"
