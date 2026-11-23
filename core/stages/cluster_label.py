"""Model-written cluster name and rationale. The rename event writes a pinned edited version."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from core.nodes import (
    PROJECT_CARD_KEY,
    ClusterLabelContent,
    NodeKind,
    NodeRef,
    ProjectCardContent,
)
from core.prompts import ContentCard, label_messages
from core.schemas import ClusterLabel, Requirement
from core.stages.base import ProduceContext, ProduceOutcome, StageSpec, register
from core.stages.calls import CallFailed, CallLog, call, result

if TYPE_CHECKING:
    from core.graph import ProjectState
    from core.llm import Complete

CARD = NodeRef(kind=NodeKind.PROJECT_CARD, key=PROJECT_CARD_KEY)


def keys(state: ProjectState) -> Iterable[str]:
    """One per cluster, keyed by cluster id."""
    return state.keys_of(NodeKind.CLUSTER)


def dependencies(state: ProjectState, key: str) -> Sequence[NodeRef]:
    """Member requirements in id order (ids and texts), then the project card."""
    return (*(NodeRef(kind=NodeKind.REQUIREMENT, key=m) for m in state.members(key)), CARD)


async def produce(ctx: ProduceContext, complete: Complete) -> ProduceOutcome:
    """One call per cluster: `core.prompts.label_messages` with the card and the
    members, schema `ClusterLabel`, params `settings.llm[CLUSTER_LABEL]`. Schema error: one retry
    with `schema_retry_section`, then failed. Name trimmed of surrounding whitespace."""
    state = ctx.state
    card = state.node(CARD).content
    assert isinstance(card, ProjectCardContent)
    results, failed, stats = [], {}, {}
    for r in ctx.refs:
        reqs = [
            Requirement(
                id=m, text=state.requirement(m).text, language=state.requirement(m).language
            )
            for m in state.members(r.key)
        ]
        log = CallLog()
        try:
            out = await call(
                complete,
                log,
                stage=NodeKind.CLUSTER_LABEL,
                unit=f"{r.key}/label",
                messages=label_messages(
                    ContentCard(card), reqs, schema=ClusterLabel.model_json_schema()
                ),
                schema=ClusterLabel,
                params=ctx.settings.llm[NodeKind.CLUSTER_LABEL],
            )
        except CallFailed as exc:
            failed[r] = f"schema: {exc}"[:500]
        else:
            name = out["name"].strip()
            if name:
                content = ClusterLabelContent(name=name, rationale=out["rationale"].strip())
                results.append((r, result(state, r, content, mode="full")))
            else:
                failed[r] = "empty name"
        stats[r] = log.stats()
    return ProduceOutcome(results=tuple(results), failed=failed, stats=stats)


SPEC = register(
    StageSpec(
        kind=NodeKind.CLUSTER_LABEL,
        uses_llm=True,
        keys=keys,
        dependencies=dependencies,
        identity_by_input=False,
        produce=produce,
        batched=False,
    )
)
