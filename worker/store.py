"""What the orchestrator persists besides nodes (docs/tasarim.md, Sunucu mimarisi ve API).

`ProjectStore` = `core.store.NodeStore` (nodes, history, output cache, event log) plus a project
record (name, stage configs and modes, approvals, production hints, per-user undo stacks, the
last server event number) and job records, all written in one transaction per command or job
step (`transaction()`).

`MemoryProjectStore` backs the tests; `worker.store_pg.PostgresStore` is the production store.
Both pass `tests/core/test_store_contract.py` and `tests/worker/test_store.py`.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from core.events import Event
from core.invalidation import Hint
from core.nodes import NodeKind, NodeRef, StageConfig
from core.store import InMemoryStore, NodeStore
from worker.contracts import Priority, StageMode

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class UndoStep(BaseModel):
    """One step of undoing a command, run against the state at undo time.

    - `event`: apply this core event.
    - `membership`: write back the clusters in `clusters` (members) and `pinned` (pinned members)
      and remove the clusters in `remove`; every other cluster keeps its current membership.
    - `restore`: put the cached result `cache_key` back on `node` (a generated node the command
      edited; after `NodeUnpinned` the cached output is still valid for its inputs).
    """

    model_config = _FROZEN
    event: Event | None = None
    clusters: dict[str, tuple[str, ...]] | None = None
    pinned: dict[str, tuple[str, ...]] | None = None
    remove: tuple[str, ...] = ()
    restore: NodeRef | None = None
    cache_key: str | None = None


class UndoEntry(BaseModel):
    model_config = _FROZEN
    command: str
    """The undone command's `type`."""
    expected: dict[str, int]
    """`str(NodeRef)` → version right after the command (0: absent). Undo is refused with
    `version_conflict` when another command changed one of them since, unless its content and
    pin equal `contents` again (another undo restored it)."""
    contents: dict[str, str | None] = Field(default_factory=dict)
    steps: tuple[UndoStep, ...]


class ProjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    name: str
    stage_configs: dict[NodeKind, StageConfig]
    stage_modes: dict[NodeKind, StageMode] = Field(default_factory=dict)
    """Missing stage: `auto`."""
    needs_approval: list[NodeRef] = Field(default_factory=list)
    """Nodes an approval event (card, stage config) staled; produced only after `approve_stage`."""
    approved: list[NodeRef] = Field(default_factory=list)
    """Stale nodes of a stage in approval mode that `approve_stage` released."""
    hints: dict[str, Hint] = Field(default_factory=dict)
    """`str(NodeRef)` → production hint (`Invalidation.hints`) until the node is produced."""
    undo: dict[str, list[UndoEntry]] = Field(default_factory=dict)
    """Per-user undo stacks, newest last."""
    last_seq: int = 0
    """Number of the last server event (`worker.contracts.ServerEvent.seq`)."""
    cluster_counter: int = 0
    """New cluster keys are `C<counter>`; never reused, so undo can recreate a removed key."""


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    stage: NodeKind
    nodes: list[NodeRef]
    priority: Priority
    state: Literal["running", "done", "failed", "cancelled"]
    started_at: float
    finished_at: float | None = None
    error: str = ""
    calls: int = 0
    """Model calls the job made (from the producer's stats)."""


class ProjectStore(NodeStore, Protocol):
    def transaction(self) -> AbstractContextManager[object]:
        """Every write inside commits together or not at all."""
        ...

    def save_project(self, record: ProjectRecord) -> None: ...

    def get_project(self, project_id: str) -> ProjectRecord | None: ...

    def list_projects(self) -> list[ProjectRecord]: ...

    def put_job(self, project_id: str, job: JobRecord) -> None: ...

    def jobs(self, project_id: str) -> list[JobRecord]: ...


class MemoryProjectStore(InMemoryStore):
    """`InMemoryStore` plus project and job records. Transactions are not rolled back."""

    def __init__(self) -> None:
        super().__init__()
        self._projects: dict[str, ProjectRecord] = {}
        self._jobs: dict[tuple[str, str], JobRecord] = {}

    def transaction(self) -> AbstractContextManager[object]:
        return nullcontext()

    def save_project(self, record: ProjectRecord) -> None:
        self._projects[record.project_id] = record.model_copy(deep=True)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        found = self._projects.get(project_id)
        return found.model_copy(deep=True) if found else None

    def list_projects(self) -> list[ProjectRecord]:
        return [self._projects[k].model_copy(deep=True) for k in sorted(self._projects)]

    def put_job(self, project_id: str, job: JobRecord) -> None:
        self._jobs[(project_id, job.job_id)] = job.model_copy()

    def jobs(self, project_id: str) -> list[JobRecord]:
        return [j for (p, _), j in sorted(self._jobs.items()) if p == project_id]
