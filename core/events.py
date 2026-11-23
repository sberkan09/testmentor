"""Domain events: what happened to a project. Each command of the API (paket 6) is turned into
one event by the orchestrator (paket 5); `core.invalidation.apply` turns the event into a new
project state and the set of nodes it stales. The event log (`NodeStore.append_event`) keeps
them with their actor for the audit trail and per-user undo (docs/tasarim.md, Veri modeli).

Events carry every id they need (for example the id of a new cluster), so applying an event is
deterministic and core generates no ids.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.nodes import MethodDef, NodeKind, NodeRef, StageConfig, TestCaseContent

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class RequirementMoved(BaseModel):
    """User placement: becomes a pinned assignment in the target cluster. The source cluster is
    removed if it becomes empty."""

    model_config = _FROZEN
    type: Literal["requirement_moved"] = "requirement_moved"
    requirement: str
    to_cluster: str


class ClusterCreated(BaseModel):
    """A new cluster from requirements taken out of their clusters (pinned assignments)."""

    model_config = _FROZEN
    type: Literal["cluster_created"] = "cluster_created"
    cluster: str
    members: tuple[str, ...] = Field(min_length=1)


class ClusterDeleted(BaseModel):
    """`destinations` maps every member of the deleted cluster to an existing cluster."""

    model_config = _FROZEN
    type: Literal["cluster_deleted"] = "cluster_deleted"
    cluster: str
    destinations: dict[str, str]


class ClustersMerged(BaseModel):
    model_config = _FROZEN
    type: Literal["clusters_merged"] = "clusters_merged"
    sources: tuple[str, ...] = Field(min_length=2)
    new_cluster: str


class ClusterRenamed(BaseModel):
    """Writes a pinned, edited version of the cluster label; stales nothing."""

    model_config = _FROZEN
    type: Literal["cluster_renamed"] = "cluster_renamed"
    cluster: str
    name: str = Field(min_length=1)
    rationale: str = ""


class MembershipChanged(BaseModel):
    """A new cut of the clustering tree (granularity slider, re-cluster; paket 3). The caller
    keeps pinned assignments; core only applies the resulting membership. Clusters missing from
    `clusters` are removed."""

    model_config = _FROZEN
    type: Literal["membership_changed"] = "membership_changed"
    clusters: dict[str, tuple[str, ...]]
    pinned: dict[str, tuple[str, ...]] | None = None
    """None: a requirement stays pinned if it was pinned anywhere before (re-cut). Given (undo,
    paket 5): exactly these pinned assignments, each a subset of its cluster's members."""


class RequirementTextChanged(BaseModel):
    model_config = _FROZEN
    type: Literal["requirement_text_changed"] = "requirement_text_changed"
    requirement: str
    text: str


class TestCaseEdited(BaseModel):
    """Writes a pinned, edited version of one test case."""

    __test__ = False  # not a pytest class
    model_config = _FROZEN
    type: Literal["test_case_edited"] = "test_case_edited"
    case: str
    content: TestCaseContent


class MethodEdited(BaseModel):
    """Writes a pinned, edited version of a requirement's verification method."""

    model_config = _FROZEN
    type: Literal["method_edited"] = "method_edited"
    requirement: str
    methods: tuple[str, ...] = Field(min_length=1)
    rationale: str = ""


class KbDocumentAdded(BaseModel):
    """The index was rebuilt with a new document; every retrieval must be re-checked."""

    model_config = _FROZEN
    type: Literal["kb_document_added"] = "kb_document_added"
    document_id: str
    index_version: str


class ProjectCardChanged(BaseModel):
    """Stales every model output of the project; needs user approval before regeneration."""

    model_config = _FROZEN
    type: Literal["project_card_changed"] = "project_card_changed"
    text: str
    methods: tuple[MethodDef, ...] | None = None
    """None keeps the current method list (paket 3)."""


class StageConfigChanged(BaseModel):
    """New prompt version, model or parameters for one stage; needs user approval before
    regeneration."""

    model_config = _FROZEN
    type: Literal["stage_config_changed"] = "stage_config_changed"
    stage: NodeKind
    config: StageConfig


class NodePinned(BaseModel):
    model_config = _FROZEN
    type: Literal["node_pinned"] = "node_pinned"
    node: NodeRef


class NodeUnpinned(BaseModel):
    model_config = _FROZEN
    type: Literal["node_unpinned"] = "node_unpinned"
    node: NodeRef


class NodeKept(BaseModel):
    """ "Benimkini koru" on the diff screen: a pinned node that went stale keeps its content and
    gets a new version stamped with the current expected hash."""

    model_config = _FROZEN
    type: Literal["node_kept"] = "node_kept"
    node: NodeRef


Event = Annotated[
    RequirementMoved
    | ClusterCreated
    | ClusterDeleted
    | ClustersMerged
    | ClusterRenamed
    | MembershipChanged
    | RequirementTextChanged
    | TestCaseEdited
    | MethodEdited
    | KbDocumentAdded
    | ProjectCardChanged
    | StageConfigChanged
    | NodePinned
    | NodeUnpinned
    | NodeKept,
    Field(discriminator="type"),
]

APPROVAL_EVENTS: frozenset[str] = frozenset({"project_card_changed", "stage_config_changed"})
"""Events whose stale nodes wait for user approval instead of being queued automatically."""


class EventRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int = Field(ge=1)
    actor: str
    event: Event
