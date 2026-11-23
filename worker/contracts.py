"""Contracts between the packages (frozen on 23 November 2026, docs/paketler/durum.md).

- Paket 5 (orchestrator, `worker/`) implements `ProjectService`.
- Paket 6 (`api/`) exposes it over REST and WebSocket with exactly these models as bodies.
- Paket 8 (`web/`) generates its TypeScript types from these models (`api/schema.json`).
- Paket 4 (`core/importing.py`, `services/importer.py`, `core/matrix_view.py`) supplies
  `ImportRequest`, `MatrixRowView` and the xlsx export used by `ProjectService`.

Changing a model here is a design change: update docs/tasarim.md (Sunucu mimarisi ve API) and
this file in a separate commit, then every package that uses it.

Commands are user intents. Most map one to one onto a core event (`core.events`); the
orchestrator validates them, applies the event (`core.invalidation.apply`), persists, queues jobs
and publishes `ServerEvent`s. Each command may carry the versions of the nodes it changes
(`expected_versions`, keyed by `str(NodeRef)`, e.g. "test_case:A:TC-1"); a stale version rejects
the command with the current versions (docs/tasarim.md, Çok kullanıcılı çalışma).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from core.nodes import MethodDef, NodeKind, NodeRef, TestCaseContent

_FROZEN = ConfigDict(frozen=True, extra="forbid")

StageMode = Literal["auto", "approval"]
"""Aşama kapısı: `auto` queues jobs at once, `approval` waits for `approve_stage`."""

Priority = Literal["P0", "P1", "P2"]
"""P0 the user's selected or visible item, P1 other user-triggered work, P2 automatic progress."""


# Import (paket 4) --------------------------------------------------------------------------------


class ColumnMapping(BaseModel):
    """Which source columns hold what. Only `text` is required; a missing id gets `REQ-<n>`."""

    model_config = _FROZEN
    text: str
    id: str | None = None
    language: str | None = None
    """Missing: detected per requirement (`tr` / `en`)."""
    source: str | None = None


class ImportRequest(BaseModel):
    """`POST /projects` body (multipart: this as JSON field `meta` plus the file)."""

    model_config = _FROZEN
    name: str = Field(min_length=1)
    key: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    """Short project key, e.g. `KDH`; also the project id."""
    card_text: str = ""
    """Project card body (system, glossary, rules). Empty: `Project: <name> (<key>)`."""
    methods: tuple[MethodDef, ...] = ()
    """Empty: the defaults from config/pipeline.yaml."""
    mapping: ColumnMapping
    sheet: str | None = None
    """xlsx: sheet name; default the first sheet. csv: ignored."""


# Commands (paket 5 implements, paket 6 routes, paket 8 sends) ------------------------------------


class MoveRequirement(BaseModel):
    model_config = _FROZEN
    type: Literal["move_requirement"] = "move_requirement"
    requirement: str
    to_cluster: str


class CreateCluster(BaseModel):
    model_config = _FROZEN
    type: Literal["create_cluster"] = "create_cluster"
    members: tuple[str, ...] = Field(min_length=1)
    cluster: str | None = None
    """None: the server picks a new key."""


class DeleteCluster(BaseModel):
    model_config = _FROZEN
    type: Literal["delete_cluster"] = "delete_cluster"
    cluster: str
    destinations: dict[str, str]
    """Every member → an existing cluster."""


class MergeClusters(BaseModel):
    model_config = _FROZEN
    type: Literal["merge_clusters"] = "merge_clusters"
    sources: tuple[str, ...] = Field(min_length=2)
    new_cluster: str | None = None


class RenameCluster(BaseModel):
    model_config = _FROZEN
    type: Literal["rename_cluster"] = "rename_cluster"
    cluster: str
    name: str = Field(min_length=1)


class SetGranularity(BaseModel):
    """Re-cut the clustering tree (`core.stages.clustering.recut`); pinned assignments stay."""

    model_config = _FROZEN
    type: Literal["set_granularity"] = "set_granularity"
    distance_threshold: float = Field(gt=0, lt=2)


class EditRequirement(BaseModel):
    model_config = _FROZEN
    type: Literal["edit_requirement"] = "edit_requirement"
    requirement: str
    text: str = Field(min_length=1)


class EditTestCase(BaseModel):
    model_config = _FROZEN
    type: Literal["edit_test_case"] = "edit_test_case"
    case: str
    """Test case node key `<cluster>:<case id>`."""
    content: TestCaseContent


class EditMethod(BaseModel):
    model_config = _FROZEN
    type: Literal["edit_method"] = "edit_method"
    requirement: str
    methods: tuple[str, ...] = Field(min_length=1)


class EditProjectCard(BaseModel):
    """Stales every model output; the regeneration waits for approval (`APPROVAL_EVENTS`)."""

    model_config = _FROZEN
    type: Literal["edit_project_card"] = "edit_project_card"
    text: str
    methods: tuple[MethodDef, ...] | None = None


class Pin(BaseModel):
    model_config = _FROZEN
    type: Literal["pin"] = "pin"
    node: NodeRef


class Unpin(BaseModel):
    model_config = _FROZEN
    type: Literal["unpin"] = "unpin"
    node: NodeRef


class KeepMine(BaseModel):
    """Fark ekranı "benimkini koru" (`core.events.NodeKept`)."""

    model_config = _FROZEN
    type: Literal["keep_mine"] = "keep_mine"
    node: NodeRef


class SetStageMode(BaseModel):
    model_config = _FROZEN
    type: Literal["set_stage_mode"] = "set_stage_mode"
    stage: NodeKind
    mode: StageMode


class ApproveStage(BaseModel):
    model_config = _FROZEN
    type: Literal["approve_stage"] = "approve_stage"
    stage: NodeKind


class Regenerate(BaseModel):
    """Retry a failed node, or produce a stale node now (priority P0)."""

    model_config = _FROZEN
    type: Literal["regenerate"] = "regenerate"
    node: NodeRef


class Undo(BaseModel):
    """Undo the actor's own last undoable command (per user, docs/tasarim.md)."""

    model_config = _FROZEN
    type: Literal["undo"] = "undo"


class Focus(BaseModel):
    """The nodes the actor is looking at; their jobs get P0. Not an undoable command."""

    model_config = _FROZEN
    type: Literal["focus"] = "focus"
    nodes: tuple[NodeRef, ...] = ()


Command = Annotated[
    MoveRequirement
    | CreateCluster
    | DeleteCluster
    | MergeClusters
    | RenameCluster
    | SetGranularity
    | EditRequirement
    | EditTestCase
    | EditMethod
    | EditProjectCard
    | Pin
    | Unpin
    | KeepMine
    | SetStageMode
    | ApproveStage
    | Regenerate
    | Undo
    | Focus,
    Field(discriminator="type"),
]


class CommandRequest(BaseModel):
    """`POST /projects/{id}/commands` body. The actor comes from the `X-User` header."""

    model_config = _FROZEN
    command: Command
    expected_versions: dict[str, int] = Field(default_factory=dict)


class CommandResult(BaseModel):
    model_config = _FROZEN
    accepted: bool
    seq: int
    """Sequence number of the last event the command produced (or the current one if rejected)."""
    reason: str = ""
    """Rejection: `version_conflict`, `locked`, `invalid`, `nothing_to_undo`, with detail."""
    current_versions: dict[str, int] = Field(default_factory=dict)
    """On `version_conflict`: the current versions of the nodes in `expected_versions`."""


# State views ------------------------------------------------------------------------------------


class NodeView(BaseModel):
    """One node as clients see it (`core.nodes.Node` without hashes)."""

    model_config = _FROZEN
    ref: NodeRef
    status: Literal["fresh", "stale", "running", "failed"]
    pinned: bool
    origin: Literal["generated", "edited"]
    version: int
    content: dict[str, Any] | None
    """`content.model_dump(mode="json")`; None for a placeholder never produced."""
    produced_by: dict[str, Any] | None = None
    """Mode, model, prompt version; the basis (`params.basis`) is left out."""
    waiting: bool = False
    """In `to_verify` (an input upstream is not fresh yet)."""
    pinned_warning: bool = False
    """Pinned and stale: the client offers the diff screen."""


class MatrixRowView(BaseModel):
    """One row of the matrix view (paket 4, `core.matrix_view`)."""

    model_config = _FROZEN
    requirement_id: str
    text: str
    language: str
    cluster: str
    cluster_name: str
    methods: tuple[str, ...]
    test_case_keys: tuple[str, ...]
    covered: bool
    warning: Literal["", "test_without_case", "case_without_test_method"] = ""
    """The two consistency warnings of docs/tasarim.md (Matris)."""


class JobView(BaseModel):
    model_config = _FROZEN
    id: str
    node: NodeRef
    priority: Priority
    state: Literal["queued", "waiting_approval", "running"]


class StageView(BaseModel):
    model_config = _FROZEN
    stage: NodeKind
    mode: StageMode
    fresh: int
    stale: int
    running: int
    failed: int
    waiting_approval: bool


class Snapshot(BaseModel):
    """`GET /projects/{id}/snapshot`: the whole project at event `seq`."""

    model_config = _FROZEN
    project_id: str
    name: str
    seq: int
    nodes: tuple[NodeView, ...]
    stages: tuple[StageView, ...]
    jobs: tuple[JobView, ...]
    matrix: tuple[MatrixRowView, ...]
    locks: dict[str, str] = Field(default_factory=dict)
    """`str(NodeRef)` → user holding the edit lock."""


# Server events (WebSocket) ----------------------------------------------------------------------

ServerEventType = Literal[
    "command_applied",
    "command_rejected",
    "node_created",
    "node_updated",
    "node_removed",
    "node_stale",
    "job_started",
    "job_progress",
    "job_done",
    "job_failed",
    "stage_waiting_approval",
    "lock_changed",
]


class ServerEvent(BaseModel):
    """`WS /projects/{id}/events` message. `seq` grows by one per event within a project; a
    reconnecting client sends its last `seq` and receives the missed events, or a `snapshot`
    message when they are no longer kept."""

    model_config = _FROZEN
    seq: int
    project_id: str
    type: ServerEventType
    actor: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    """node_*: {"node": NodeView}; node_removed: {"ref": NodeRef}; job_*: {"job": JobView} and
    for job_progress {"text": str} (streamed tokens, not persisted); command_*: {"command":
    Command, "result": CommandResult}; lock_changed: {"ref": str, "user": str | None}."""


# Service (paket 5) -------------------------------------------------------------------------------


class ProjectService(Protocol):
    """What the API (paket 6) calls. One instance per process; projects are kept in memory and
    persisted in the store (Postgres in production, in memory in tests)."""

    async def create_project(self, request: ImportRequest, data: bytes, filename: str) -> Snapshot:
        """Import (paket 4), embed, first cut, `new_project`, queue the first jobs."""
        ...

    async def command(
        self, project_id: str, request: CommandRequest, actor: str
    ) -> CommandResult: ...

    def snapshot(self, project_id: str) -> Snapshot: ...

    def events_after(self, project_id: str, seq: int) -> list[ServerEvent] | None:
        """Events with `seq` greater than the given one, or None when they are no longer kept
        (the client then takes a snapshot)."""
        ...

    def subscribe(self, project_id: str) -> AsyncIterator[ServerEvent]:
        """Live events from now on (job_progress included)."""
        ...

    def lock(self, project_id: str, ref: NodeRef, actor: str) -> bool:
        """Take or refresh the 60 s edit lock; False when another user holds it."""
        ...

    def matrix_xlsx(self, project_id: str) -> bytes: ...

    def projects(self) -> list[tuple[str, str]]:
        """(project id, name) of every project."""
        ...
