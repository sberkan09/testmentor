"""Paket 3b: field length limits in the output schema and the "describe long inputs" rule
(KDH-030: a boundary test wrote an endless input string until max_tokens)."""

from __future__ import annotations

import json

from core import prompts
from core.nodes import NodeKind
from core.prompts import GENERATION_INSTRUCTION, prompt_version
from core.schemas import case_set_model, incremental_model
from services.settings import load_stage_settings
from tests.stages.helpers import (
    ROOT,
    SETTINGS,
    ScriptedComplete,
    case_json,
    drive,
    project,
    requirement_rows,
    smart_reply,
)

LIMITS = {
    "title": 300,
    "preconditions": 1000,
    "test_inputs": 1000,
    "assumptions": 4000,
    "action": 1000,
    "expected": 4000,
}
LIMITED = SETTINGS.model_copy(update={"field_max_chars": LIMITS})


def _props(schema: dict) -> tuple[dict, dict]:
    defs = schema["$defs"]
    return defs["TestCase"]["properties"], defs["Step"]["properties"]


def test_schema_carries_max_length_from_settings():
    case, step = _props(
        case_set_model(
            SETTINGS.test_types, SETTINGS.priorities, LIMITED.field_limits
        ).model_json_schema()
    )
    assert case["title"]["maxLength"] == 300 and case["test_inputs"]["maxLength"] == 1000
    assert step["action"]["maxLength"] == 1000 and step["expected"]["maxLength"] == 4000
    inc_case, _ = _props(
        incremental_model(
            SETTINGS.test_types, SETTINGS.priorities, LIMITED.field_limits
        ).model_json_schema()
    )
    assert inc_case["assumptions"]["maxLength"] == 4000


def test_no_limits_keeps_the_paket1_schema():
    case, step = _props(
        case_set_model(SETTINGS.test_types, SETTINGS.priorities).model_json_schema()
    )
    assert all("maxLength" not in v for v in (*case.values(), *step.values()))


def test_config_limits():
    s = load_stage_settings(ROOT / "config")
    assert s.field_max_chars == LIMITS


def test_limits_and_rule_change_only_the_test_set_version():
    before = {k: prompt_version(k, SETTINGS) for k in prompts.STAGE_VERSIONS}
    after = {k: prompt_version(k, LIMITED) for k in prompts.STAGE_VERSIONS}
    assert after[NodeKind.TEST_SET] != before[NodeKind.TEST_SET]
    assert after[NodeKind.METHOD] == before[NodeKind.METHOD]
    assert after[NodeKind.CLUSTER_LABEL] == before[NodeKind.CLUSTER_LABEL]
    assert prompts.STAGE_VERSIONS[NodeKind.TEST_SET] == "g5"
    assert (
        "describe" in GENERATION_INSTRUCTION and "129-character password" in GENERATION_INSTRUCTION
    )


async def test_too_long_field_is_a_schema_error_and_retried():
    seen: list[int] = []

    def handle(r):
        if r.schema.__name__ == "TestCaseSet" and {i for i, _ in requirement_rows(r)} == {
            "R1",
            "R2",
        }:
            seen.append(1)
            if len(seen) == 1:
                bad = case_json("R1") | {"test_inputs": "A1b2" * 400}  # 1.600 > 1.000
                return {"test_cases": [bad, case_json("R2")]}
        return smart_reply(r)

    complete = ScriptedComplete(handle)
    out = await drive(project(), complete, settings=LIMITED)
    req = [r for r in complete.of(NodeKind.TEST_SET) if "R1 (tr)" in r.messages[1]["content"]]
    assert len(req) == 2  # first reply violated maxLength, the retry carries the error
    assert "at most 1000 characters" in req[1].messages[1]["content"]
    assert (
        json.loads(json.dumps(req[0].schema.model_json_schema()))["$defs"]["TestCase"][
            "properties"
        ]["test_inputs"]["maxLength"]
        == 1000
    )
    assert not out.failed()
