"""Registry, card data model, settings and the model adapter (paket 3 step 3 interfaces)."""

from __future__ import annotations

import json

import yaml

from core import stages
from core.events import ProjectCardChanged
from core.invalidation import apply
from core.llm import LLMParams, LLMRequest
from core.nodes import NodeKind, ProjectCardContent, ref
from core.schemas import ClusterLabel
from tests.core.helpers import produce_all
from tests.fake_openai import FakeReply, FakeServer
from tests.stages.helpers import CARD_METHODS, CARD_TEXT, CFG, ROOT, SETTINGS, project


def test_every_stage_has_a_producer():
    specs = {s.kind: s for s in stages.all_specs()}
    assert all(s.produce is not None for s in specs.values())
    assert {k for k, s in specs.items() if s.batched} == {
        NodeKind.EMBEDDING,
        NodeKind.METHOD,
        NodeKind.MATRIX_ROW,
    }
    assert set(SETTINGS.llm) == {k for k, s in specs.items() if s.uses_llm}


def test_project_card_carries_methods():
    state = project()
    card = state.node(ref(NodeKind.PROJECT_CARD, "card")).content
    assert isinstance(card, ProjectCardContent)
    assert card.text == CARD_TEXT and card.methods == CARD_METHODS


def test_card_change_without_methods_keeps_the_method_list():
    state = produce_all(project())
    state, _ = apply(state, ProjectCardChanged(text="Yeni kart."))
    card = state.node(ref(NodeKind.PROJECT_CARD, "card")).content
    assert card.text == "Yeni kart." and card.methods == CARD_METHODS
    state, _ = apply(state, ProjectCardChanged(text="Yeni kart.", methods=CARD_METHODS[:2]))
    assert state.node(ref(NodeKind.PROJECT_CARD, "card")).content.methods == CARD_METHODS[:2]


def test_config_has_generation_unit_and_label_params():
    cfg = yaml.safe_load((ROOT / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
    assert cfg["generation"]["max_unit_size"] == 25
    assert cfg["clustering"]["max_cluster_size"] == 25
    assert set(cfg["cluster_label"]) == {"thinking", "temperature", "max_tokens"}


# Settings (services) ------------------------------------------------------------------------


def test_load_stage_settings_matches_config():
    from services.settings import load_stage_settings

    s = load_stage_settings(ROOT / "config")
    assert s.test_types == SETTINGS.test_types and s.priorities == SETTINGS.priorities
    assert s.examples == SETTINGS.examples
    assert s.max_unit_size == 25 and s.method_batch_size == 25
    assert s.llm[NodeKind.TEST_SET] == LLMParams(temperature=0.0, thinking=False, max_tokens=8192)
    assert s.llm[NodeKind.CLUSTER_LABEL].max_tokens == 512
    assert s.clustering.distance_threshold == CFG["clustering"]["distance_threshold"]


def test_stage_configs_carry_prompt_versions_and_params():
    from core.prompts import prompt_version
    from services.settings import stage_configs

    cfgs = stage_configs(SETTINGS, model="qwen3.8-27b", embedding_model_version="BAAI/bge-m3")
    assert set(cfgs) == {s.kind for s in stages.all_specs()}
    t = cfgs[NodeKind.TEST_SET]
    assert t.prompt_version == prompt_version(NodeKind.TEST_SET, SETTINGS)
    assert t.model == "qwen3.8-27b" and t.params["max_tokens"] == 8192
    assert cfgs[NodeKind.EMBEDDING].prompt_version == "BAAI/bge-m3"
    assert cfgs[NodeKind.CLUSTERING].params["distance_threshold"] == 0.35
    ex = dict(SETTINGS.examples, output={"test_cases": []})
    other = stage_configs(
        SETTINGS.model_copy(update={"examples": ex}),
        model="qwen3.8-27b",
        embedding_model_version="BAAI/bge-m3",
    )
    changed = {k for k in cfgs if cfgs[k] != other[k]}
    assert changed == {NodeKind.TEST_SET}


# Model adapter (services) -------------------------------------------------------------------


async def test_client_complete_returns_parsed_reply():
    from services.llm_client import LLMClient
    from services.settings import LLMSettings
    from services.stage_llm import ClientComplete

    server = FakeServer(
        FakeReply(content=json.dumps({"name": "Kimlik doğrulama", "rationale": "Ortak konu."}))
    )
    settings = LLMSettings(
        engine="vllm", model="m", base_url="http://test/v1", served_model_name="m"
    )
    async with LLMClient(settings, transport=server.transport()) as client:
        complete = ClientComplete(client)
        req = LLMRequest(
            stage=NodeKind.CLUSTER_LABEL,
            unit="A/label",
            messages=({"role": "system", "content": "s"}, {"role": "user", "content": "u"}),
            schema=ClusterLabel,
            params=LLMParams(max_tokens=64),
        )
        reply = await complete(req)
        assert isinstance(reply.parsed, ClusterLabel) and reply.parsed.name == "Kimlik doğrulama"
        assert reply.schema_error is None and reply.usage.completion_tokens == 10
        assert server.requests[0]["max_tokens"] == 64

        server.reply = FakeReply(content='{"name": ""}')
        bad = await complete(req)
        assert bad.parsed is None and bad.schema_error


def test_production_mode_settings_stay_out_of_the_hash():
    """D8 arms run on one baseline: regeneration and prune_removals choose the mode, which never
    enters `input_hash` (core/stages/base.py); max_unit_size and repair change outputs and do."""
    from services.settings import stage_configs

    def cfgs(**update):
        return stage_configs(
            SETTINGS.model_copy(update=update), model="m", embedding_model_version="e"
        )

    base = cfgs()
    assert cfgs(regeneration="full", prune_removals=True) == base
    assert cfgs(max_unit_size=10)[NodeKind.TEST_SET] != base[NodeKind.TEST_SET]
    assert cfgs(repair=False)[NodeKind.TEST_SET] != base[NodeKind.TEST_SET]
