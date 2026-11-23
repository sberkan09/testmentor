"""One project in the orchestrator (docs/tasarim.md, Sunucu mimarisi ve API; İş kuyruğu; Aşama
kapıları; Çok kullanıcılı çalışma).

`ProjectRuntime` owns the project's in-memory `ProjectState` and is its only writer. Every change
goes through `_commit`, in this order:

1. compute the new state (pure: `core.invalidation.apply`, `settle_many`, `mark_running`, ...);
2. persist it in one store transaction: node versions and statuses, core events of the event log
   (with the actor), output cache entries, job records and the project record (approvals, hints,
   undo stacks, last server event number);
3. swap the in-memory state; cancel running jobs whose node the change cancelled
   (`Invalidation.cancel`);
4. publish server events with consecutive `seq` (node events, then the command or job event);
5. schedule: every ready node that no gate holds gets a queued job (`worker.queue`).

Nothing awaits between 1 and 5 and the service runs on one event loop, so commands and job steps
never interleave inside a commit. A store error leaves memory as it was.

Commands: version check (`expected_versions`), lock check (edit commands only), command → core
events → `apply` with the output cache (cache hits settle without a model call) → commit. An
undoable command pushes an `UndoEntry` (the previous content of the source and edited nodes it
changed) on the actor's stack; undo writes that content back with new events, so derived nodes
come from the cache.

Jobs: a job's key is a node, or a batched stage (embedding, method, matrix: one job takes every
ready node of the stage). At start: cache hits settle first, then `mark_running` (job_started),
then the stage producer with a `ProduceContext` (hint and, for a merge, the source sets' cases from
store history). At the end every result goes to the output cache; `settle_many` writes those
still valid; rejected nodes are released (`core.invalidation.release`), failed ones marked failed.
A job is cancelled when its node's input or context changes; a batched job only when all its
nodes are cancelled (the rest of the batch stays useful; the changed node's old result only
reaches the cache).

Priorities: P0 a node someone focuses (`Focus`) or asked for (`Regenerate`), P1 a node a user
command changed (directly, or its expected hash), P2 everything else. Jobs of command-changed
nodes wait `debounce_s`; a newer command restarts the wait.

Gates: a stage in `approval` mode holds its ready nodes until `approve_stage`, which releases the
stage's stale nodes at that moment. Nodes an approval event (project card, stage config) changed
wait for `approve_stage` in either mode.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import re
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core import stages
from core.events import (
    ClusterCreated,
    ClusterDeleted,
    ClusterRenamed,
    ClustersMerged,
    Event,
    MembershipChanged,
    MethodEdited,
    NodeKept,
    NodePinned,
    NodeUnpinned,
    ProjectCardChanged,
    RequirementMoved,
    RequirementTextChanged,
    StageConfigChanged,
    TestCaseEdited,
)
from core.graph import ProjectState, cache_key, expected_hash, upstream, with_declared_nodes
from core.hashing import plain_hash
from core.invalidation import (
    Hint,
    Invalidation,
    analyze,
    apply,
    mark_failed,
    mark_running,
    release,
    settle_many,
)
from core.llm import Complete
from core.nodes import (
    CHILD_KINDS,
    PROJECT_CARD_KEY,
    SOURCE_KINDS,
    ClusterContent,
    ClusterLabelContent,
    EmbeddingContent,
    Node,
    NodeKind,
    NodeRef,
    ProjectCardContent,
    Result,
    StageConfig,
    Status,
    TestCaseContent,
    TestSetContent,
)
from core.settings import StageSettings
from core.stages.base import Embed, PassageSource, ProduceContext, ProduceOutcome, Retrieve
from core.stages.clustering import recut
from core.stages.test_generation import BASIS_PARAM
from core.store import OutputCache
from worker.contracts import (
    ApproveStage,
    Command,
    CommandRequest,
    CommandResult,
    CreateCluster,
    DeleteCluster,
    EditMethod,
    EditProjectCard,
    EditRequirement,
    EditTestCase,
    Focus,
    JobView,
    KeepMine,
    MergeClusters,
    MoveRequirement,
    NodeView,
    Pin,
    Priority,
    Regenerate,
    RenameCluster,
    ServerEvent,
    ServerEventType,
    SetGranularity,
    SetStageMode,
    Snapshot,
    StageView,
    Undo,
    Unpin,
)
from worker.queue import JobQueue, better
from worker.settings import OrchestratorSettings
from worker.store import JobRecord, ProjectRecord, ProjectStore, UndoEntry, UndoStep

log = logging.getLogger(__name__)

UNDO_LIMIT = 100
"""Undo entries kept per user."""

_PROGRESS: contextvars.ContextVar[Callable[[str], None] | None] = contextvars.ContextVar(
    "testmentor_job_progress", default=None
)


def report_progress(text: str) -> None:
    """Streamed text of the model call in flight, published as `job_progress` (live only, not
    persisted, not replayed). A streaming `Complete` calls it; outside a job it does nothing."""
    sink = _PROGRESS.get()
    if sink is not None:
        sink(text)


@dataclass(frozen=True)
class RuntimeDeps:
    complete: Complete
    settings: StageSettings
    stage_configs: Mapping[NodeKind, StageConfig]
    """The configuration the code runs with. A loaded project whose stored configs differ gets
    `StageConfigChanged` events (approval required)."""
    orchestrator: OrchestratorSettings
    embed: Embed | None = None
    retrieve: Retrieve | None = None
    """Knowledge base search (paket 7); None: no passages."""
    passages: PassageSource | None = None
    clock: Callable[[], float] = time.monotonic
    """Edit locks."""


class Rejected(Exception):
    def __init__(self, reason: str, current_versions: Mapping[str, int] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.current_versions = dict(current_versions or {})


@dataclass
class _Draft:
    type: ServerEventType
    payload: dict[str, Any]
    actor: str = ""


@dataclass
class _Job:
    job_id: int
    key: str
    stage: NodeKind
    refs: tuple[NodeRef, ...]
    priority: Priority
    record: JobRecord
    calls: int = 0

    def view(self, state: str = "running") -> JobView:
        return JobView(
            id=self.record.job_id,
            node=self.refs[0],
            priority=self.priority,
            state=state,  # type: ignore[arg-type]
        )


class _Subscription:
    """Live events from the moment it is created (`ProjectService.subscribe`)."""

    def __init__(self, owner: ProjectRuntime) -> None:
        self.owner = owner
        self.queue: asyncio.Queue[ServerEvent] = asyncio.Queue()

    def __aiter__(self) -> _Subscription:
        return self

    async def __anext__(self) -> ServerEvent:
        if self not in self.owner._subscribers:
            raise StopAsyncIteration
        return await self.queue.get()

    async def aclose(self) -> None:
        self.owner._subscribers.discard(self)


class _Tx:
    """The core transitions behind one commit, in order. Each step writes a node at most once,
    so persisting the steps one after the other keeps every stored version at +1."""

    def __init__(self, state: ProjectState) -> None:
        self.state = state
        self.chain: list[ProjectState] = []
        self.invs: list[Invalidation] = []
        self.settled: set[NodeRef] = set()
        self.events: list[Event] = []

    def apply(self, event: Event) -> None:
        self.state, inv = apply(self.state, event)
        self.chain.append(self.state)
        self.invs.append(inv)
        self.events.append(event)

    def settle(self, results: Sequence[tuple[NodeRef, Result]]):
        out = settle_many(self.state, results)
        if out.accepted:
            self.state = out.state
            self.chain.append(out.state)
            self.invs.append(out.invalidation)
            self.settled |= out.accepted
        return out

    def resolve(self, cache: OutputCache) -> None:
        """Settle ready nodes whose cache key hits, round by round (ready nodes never depend on
        each other), until nothing more hits: `core.invalidation.apply(cache=...)` in steps."""
        while True:
            state = self.state
            hits = []
            for r in analyze(state).ready:
                cached = cache.get(state.project_id, cache_key(state, r))
                if cached is not None:
                    hits.append((r, cached))
            if not hits or not self.settle(hits).accepted:
                return


def _fingerprint(node: Node | None) -> str | None:
    """Content and pin of a node, for undo's conflict check."""
    if node is None:
        return None
    content = node.content.model_dump(mode="json") if node.content is not None else None
    return plain_hash({"content": content, "pinned": node.pinned})


def _ref_of(text: str) -> NodeRef:
    kind, key = text.split(":", 1)
    return NodeRef(kind=NodeKind(kind), key=key)


def _CL(key: str) -> NodeRef:  # noqa: N802
    return NodeRef(kind=NodeKind.CLUSTER, key=key)


CARD = NodeRef(kind=NodeKind.PROJECT_CARD, key=PROJECT_CARD_KEY)


def node_view(state: ProjectState, node: Node, waiting: frozenset[NodeRef]) -> NodeView:
    produced = None
    if node.produced_by is not None:
        produced = node.produced_by.model_dump(mode="json")
        produced["params"] = {k: v for k, v in produced["params"].items() if k != BASIS_PARAM}
    return NodeView(
        ref=node.ref,
        status=node.status.value,  # type: ignore[arg-type]
        pinned=node.pinned,
        origin=node.origin.value,  # type: ignore[arg-type]
        version=node.version,
        content=node.content.model_dump(mode="json") if node.content is not None else None,
        produced_by=produced,
        waiting=node.ref in waiting,
        pinned_warning=node.pinned and node.status == Status.STALE,
    )


class ProjectRuntime:
    def __init__(
        self,
        record: ProjectRecord,
        state: ProjectState,
        store: ProjectStore,
        queue: JobQueue,
        deps: RuntimeDeps,
    ) -> None:
        self.record = record
        self.state = state
        self.store = store
        self.queue = queue
        self.deps = deps
        self.pid = state.project_id
        self._buffer: deque[ServerEvent] = deque(maxlen=deps.orchestrator.event_buffer)
        self._subscribers: set[_Subscription] = set()
        self._locks: dict[NodeRef, tuple[str, float]] = {}
        self._focus: dict[str, frozenset[NodeRef]] = {}
        self._forced: set[NodeRef] = set()
        self._user: set[NodeRef] = set()
        self._owner: dict[NodeRef, int] = {}
        self._jobs: dict[int, _Job] = {}
        self._key_refs: dict[str, NodeRef] = {}
        self._waiting: dict[NodeKind, frozenset[NodeRef]] = {}
        self._session = uuid.uuid4().hex[:8]  # job record ids stay unique across restarts

    # Construction -------------------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        name: str,
        state: ProjectState,
        store: ProjectStore,
        queue: JobQueue,
        deps: RuntimeDeps,
    ) -> ProjectRuntime:
        """A new project from an imported state: every node is written, first jobs queued."""
        record = ProjectRecord(
            project_id=state.project_id,
            name=name,
            stage_configs=dict(state.stage_configs),
            cluster_counter=_max_cluster_number(state.keys_of(NodeKind.CLUSTER)),
        )
        empty = ProjectState(project_id=state.project_id, nodes={}, stage_configs={})
        rt = cls(record, empty, store, queue, deps)
        rt._commit(state)
        rt._schedule()
        return rt

    @classmethod
    def load(
        cls, record: ProjectRecord, store: ProjectStore, queue: JobQueue, deps: RuntimeDeps
    ) -> ProjectRuntime:
        """From the store: current nodes, placeholders for never-produced nodes, running nodes
        released (their jobs died with the process), changed stage configs applied as approval
        events, jobs queued."""
        nodes = store.load(record.project_id)
        loaded = with_declared_nodes(
            ProjectState(
                project_id=record.project_id, nodes=nodes, stage_configs=record.stage_configs
            )
        )
        rt = cls(record, loaded, store, queue, deps)
        state = loaded
        for r, node in loaded.nodes.items():
            if node.status == Status.RUNNING:
                state = release(state, r)
        if state is not loaded:
            rt._commit(state)
        changed = [
            StageConfigChanged(stage=k, config=c)
            for k, c in sorted(deps.stage_configs.items())
            if rt.state.stage_configs.get(k) != c
        ]
        if changed:
            tx = _Tx(rt.state)
            for event in changed:
                tx.apply(event)
            tx.resolve(store)
            touched = rt._touched(rt.state, tx.state)
            rt._commit(tx.state, tx=tx, actor="system", touched=touched, approval=True)
        rt._schedule()
        return rt

    # Reading ------------------------------------------------------------------------------------

    @property
    def last_seq(self) -> int:
        return self.record.last_seq

    def snapshot(self, matrix: Sequence[Any] = ()) -> Snapshot:
        state = self.state
        an = analyze(state)
        nodes = tuple(node_view(state, state.nodes[r], an.to_verify) for r in state.ordered_refs())
        stage_views = []
        for spec in stages.all_specs():
            counts = {s: 0 for s in Status}
            for key in state.keys_of(spec.kind):
                counts[state.nodes[NodeRef(kind=spec.kind, key=key)].status] += 1
            stage_views.append(
                StageView(
                    stage=spec.kind,
                    mode=self.record.stage_modes.get(spec.kind, "auto"),
                    fresh=counts[Status.FRESH],
                    stale=counts[Status.STALE],
                    running=counts[Status.RUNNING],
                    failed=counts[Status.FAILED],
                    waiting_approval=bool(self._waiting.get(spec.kind)),
                )
            )
        return Snapshot(
            project_id=self.pid,
            name=self.record.name,
            seq=self.record.last_seq,
            nodes=nodes,
            stages=tuple(stage_views),
            jobs=tuple(self.job_views()),
            matrix=tuple(matrix),
            locks={
                str(r): u
                for r, (u, exp) in sorted(self._locks.items(), key=lambda x: x[0].sort_key())
                if exp > self.deps.clock()
            },
        )

    def job_views(self) -> list[JobView]:
        views: list[JobView] = []
        for job in sorted(self._jobs.values(), key=lambda j: j.job_id):
            for r in job.refs:
                if self._owner.get(r) == job.job_id:
                    views.append(
                        JobView(
                            id=job.record.job_id, node=r, priority=job.priority, state="running"
                        )
                    )
        prefix = f"{self.pid}|"
        for p in self.queue.pending():
            if p.key.startswith(prefix):
                for r in self._collect(p.key):
                    views.append(
                        JobView(
                            id=f"q:{p.key[len(prefix) :]}",
                            node=r,
                            priority=p.priority,
                            state="queued",
                        )
                    )
        for kind in sorted(self._waiting, key=lambda k: list(NodeKind).index(k)):
            for r in sorted(self._waiting[kind], key=NodeRef.sort_key):
                views.append(
                    JobView(
                        id=f"w:{r}", node=r, priority=self._priority(r), state="waiting_approval"
                    )
                )
        return views

    def events_after(self, seq: int) -> list[ServerEvent] | None:
        if seq >= self.record.last_seq:
            return []
        if not self._buffer or self._buffer[0].seq > seq + 1:
            return None
        return [e for e in self._buffer if e.seq > seq]

    def subscribe(self) -> _Subscription:
        sub = _Subscription(self)
        self._subscribers.add(sub)
        return sub

    def idle(self) -> bool:
        prefix = f"{self.pid}|"
        return not self._jobs and not any(p.key.startswith(prefix) for p in self.queue.pending())

    # Locks --------------------------------------------------------------------------------------

    def lock(self, ref: NodeRef, actor: str) -> bool:
        now = self.deps.clock()
        held = self._locks.get(ref)
        if held is not None and held[0] != actor and held[1] > now:
            return False
        self._locks[ref] = (actor, now + self.deps.orchestrator.lock_s)
        if held is None or held[0] != actor or held[1] <= now:
            self._commit(
                self.state,
                after=[_Draft("lock_changed", {"ref": str(ref), "user": actor}, actor)],
            )
        return True

    def _lock_holder(self, ref: NodeRef) -> str | None:
        held = self._locks.get(ref)
        if held is None:
            return None
        if held[1] <= self.deps.clock():
            del self._locks[ref]
            return None
        return held[0]

    # Commands -----------------------------------------------------------------------------------

    def command(self, request: CommandRequest, actor: str) -> CommandResult:
        cmd = request.command
        try:
            self._check_versions(request.expected_versions)
            for r in _lock_targets(cmd):
                holder = self._lock_holder(r)
                if holder is not None and holder != actor:
                    raise Rejected(f"locked: {r} by {holder}")
            return self._dispatch(cmd, actor)
        except Rejected as exc:
            return self._reject(cmd, actor, exc.reason, exc.current_versions)
        except (ValueError, KeyError) as exc:
            return self._reject(cmd, actor, f"invalid: {exc}", {})

    def _check_versions(self, expected: Mapping[str, int]) -> None:
        current = {}
        for key in expected:
            try:
                node = self.state.get(_ref_of(key))
            except ValueError as exc:
                raise Rejected(f"invalid: bad node ref {key!r}") from exc
            current[key] = node.version if node is not None else 0
        if any(current[k] != v for k, v in expected.items()):
            raise Rejected("version_conflict", current)

    def _reject(
        self, cmd: Command, actor: str, reason: str, current: Mapping[str, int]
    ) -> CommandResult:
        result = CommandResult(accepted=False, seq=0, reason=reason, current_versions=dict(current))
        seq = self._commit(
            self.state, after=[_command_draft("command_rejected", cmd, result, actor)]
        )
        return result.model_copy(update={"seq": seq})

    def _dispatch(self, cmd: Command, actor: str) -> CommandResult:
        state = self.state
        match cmd:
            case MoveRequirement(requirement=req, to_cluster=to):
                return self._events(cmd, actor, [RequirementMoved(requirement=req, to_cluster=to)])
            case CreateCluster(members=members, cluster=key):
                key = key or self._new_cluster_key()
                return self._events(cmd, actor, [ClusterCreated(cluster=key, members=members)])
            case DeleteCluster(cluster=c, destinations=dest):
                return self._events(cmd, actor, [ClusterDeleted(cluster=c, destinations=dest)])
            case MergeClusters(sources=sources, new_cluster=new):
                new = new or self._new_cluster_key()
                return self._events(cmd, actor, [ClustersMerged(sources=sources, new_cluster=new)])
            case RenameCluster(cluster=c, name=name):
                if NodeRef(kind=NodeKind.CLUSTER_LABEL, key=c) not in state.nodes:
                    raise ValueError(f"no cluster {c}")
                return self._events(cmd, actor, [ClusterRenamed(cluster=c, name=name)])
            case SetGranularity(distance_threshold=threshold):
                return self._events(cmd, actor, [self._recut(threshold)])
            case EditRequirement(requirement=req, text=text):
                state.requirement(req)
                return self._events(
                    cmd, actor, [RequirementTextChanged(requirement=req, text=text)]
                )
            case EditTestCase(case=key, content=content):
                if NodeRef(kind=NodeKind.TEST_CASE, key=key) not in state.nodes:
                    raise ValueError(f"no test case {key}")
                return self._events(cmd, actor, [TestCaseEdited(case=key, content=content)])
            case EditMethod(requirement=req, methods=methods):
                card = state.node(CARD).content
                assert isinstance(card, ProjectCardContent)
                names = {m.name for m in card.methods}
                if names and not set(methods) <= names:
                    raise ValueError(f"unknown methods {sorted(set(methods) - names)}")
                state.requirement(req)
                return self._events(cmd, actor, [MethodEdited(requirement=req, methods=methods)])
            case EditProjectCard(text=text, methods=methods):
                return self._events(cmd, actor, [ProjectCardChanged(text=text, methods=methods)])
            case Pin(node=r):
                return self._events(cmd, actor, [NodePinned(node=r)])
            case Unpin(node=r):
                return self._events(cmd, actor, [NodeUnpinned(node=r)])
            case KeepMine(node=r):
                return self._events(cmd, actor, [NodeKept(node=r)])
            case SetStageMode(stage=kind, mode=mode):
                stages.get(kind)

                def set_mode(rec: ProjectRecord) -> None:
                    rec.stage_modes[kind] = mode

                return self._applied(cmd, actor, mutate=set_mode)
            case ApproveStage(stage=kind):
                stages.get(kind)
                return self._applied(cmd, actor, mutate=self._approver(kind))
            case Regenerate(node=r):
                node = state.get(r)
                if node is None or r.kind in SOURCE_KINDS or r.kind in CHILD_KINDS:
                    raise ValueError(f"{r} is not produced by a stage")
                if node.pinned or node.status not in (Status.STALE, Status.FAILED):
                    raise ValueError(f"{r} is {node.status.value}; nothing to produce")
                self._forced.add(r)
                return self._applied(cmd, actor)
            case Undo():
                return self._undo(cmd, actor)
            case Focus(nodes=nodes):
                self._focus[actor] = frozenset(nodes)
                self._schedule()
                return CommandResult(accepted=True, seq=self.record.last_seq)
        raise ValueError(f"unknown command {cmd!r}")  # pragma: no cover

    def _events(self, cmd: Command, actor: str, events: list[Event]) -> CommandResult:
        tx = _Tx(self.state)
        for event in events:
            tx.apply(event)
        tx.resolve(self.store)
        entry = self._undo_entry(cmd, self.state, tx.state)
        approval = any(inv.requires_approval for inv in tx.invs)

        def push(rec: ProjectRecord) -> None:
            if entry is not None:
                stack = rec.undo.setdefault(actor, [])
                stack.append(entry)
                del stack[:-UNDO_LIMIT]

        return self._applied(cmd, actor, tx, mutate=push, approval=approval)

    def _applied(
        self,
        cmd: Command,
        actor: str,
        tx: _Tx | None = None,
        *,
        mutate: Callable[[ProjectRecord], None] | None = None,
        approval: bool = False,
    ) -> CommandResult:
        tx = tx or _Tx(self.state)
        touched = self._touched(self.state, tx.state)
        result = CommandResult(accepted=True, seq=0)
        seq = self._commit(
            tx.state,
            tx=tx,
            actor=actor,
            mutate=mutate,
            touched=touched,
            approval=approval,
            after=[_command_draft("command_applied", cmd, result, actor)],
        )
        return result.model_copy(update={"seq": seq})

    def _approver(self, kind: NodeKind) -> Callable[[ProjectRecord], None]:
        state = self.state

        def approve(rec: ProjectRecord) -> None:
            rec.needs_approval = [r for r in rec.needs_approval if r.kind != kind]
            if rec.stage_modes.get(kind, "auto") == "approval":
                stale = [
                    NodeRef(kind=kind, key=k)
                    for k in state.keys_of(kind)
                    if state.nodes[NodeRef(kind=kind, key=k)].status
                    in (Status.STALE, Status.FAILED)
                ]
                rec.approved = sorted(set(rec.approved) | set(stale), key=NodeRef.sort_key)

        return approve

    def _new_cluster_key(self) -> str:
        n = self.record.cluster_counter
        existing = set(self.state.keys_of(NodeKind.CLUSTER))
        while True:
            n += 1
            key = f"C{n:03d}"
            if key not in existing:
                self.record.cluster_counter = n  # persisted with the command's commit
                return key

    def _recut(self, threshold: float) -> MembershipChanged:
        vectors = {}
        for rid in self.state.keys_of(NodeKind.REQUIREMENT):
            emb = self.state.get(NodeRef(kind=NodeKind.EMBEDDING, key=rid))
            if emb is None or not isinstance(emb.content, EmbeddingContent):
                raise ValueError(f"embedding of {rid} is not ready")
            vectors[rid] = emb.content.vector
        settings = self.deps.settings.clustering.model_copy(
            update={"distance_threshold": threshold}
        )
        return recut(self.state, vectors, settings, self._new_cluster_key)

    # Undo ---------------------------------------------------------------------------------------

    def _undo_entry(self, cmd: Command, old: ProjectState, new: ProjectState) -> UndoEntry | None:
        """What undoing `cmd` writes back, or None for a command that changed nothing or is not
        undoable (keep_mine, stage modes, approvals, regenerate, focus)."""
        steps: list[UndoStep] = []
        touched: list[NodeRef] = []
        match cmd:
            case (
                MoveRequirement()
                | CreateCluster()
                | DeleteCluster()
                | MergeClusters()
                | SetGranularity()
            ):
                keys = set(old.keys_of(NodeKind.CLUSTER)) | set(new.keys_of(NodeKind.CLUSTER))
                affected = sorted(k for k in keys if old.get(_CL(k)) is not new.get(_CL(k)))
                if not affected:
                    return None
                prev = {k: old.node(_CL(k)).content for k in affected if _CL(k) in old.nodes}
                steps.append(
                    UndoStep(
                        clusters={k: c.members for k, c in prev.items()},  # type: ignore[union-attr]
                        pinned={k: c.pinned_members for k, c in prev.items()},  # type: ignore[union-attr]
                        remove=tuple(k for k in affected if k not in prev),
                    )
                )
                for k in prev:
                    label = old.get(NodeRef(kind=NodeKind.CLUSTER_LABEL, key=k))
                    if (
                        _CL(k) not in new.nodes
                        and label is not None
                        and label.pinned
                        and isinstance(label.content, ClusterLabelContent)
                    ):
                        steps.append(
                            UndoStep(
                                event=ClusterRenamed(
                                    cluster=k,
                                    name=label.content.name,
                                    rationale=label.content.rationale,
                                )
                            )
                        )
                touched = [_CL(k) for k in affected]
            case EditRequirement(requirement=req):
                r = NodeRef(kind=NodeKind.REQUIREMENT, key=req)
                if old.node(r) is new.node(r):
                    return None
                steps.append(
                    UndoStep(
                        event=RequirementTextChanged(
                            requirement=req, text=old.requirement(req).text
                        )
                    )
                )
                touched = [r]
            case EditProjectCard():
                if old.node(CARD) is new.node(CARD):
                    return None
                card = old.node(CARD).content
                assert isinstance(card, ProjectCardContent)
                steps.append(
                    UndoStep(event=ProjectCardChanged(text=card.text, methods=card.methods))
                )
                touched = [CARD]
            case RenameCluster(cluster=c):
                r = NodeRef(kind=NodeKind.CLUSTER_LABEL, key=c)
                steps = _undo_edit(
                    old.node(r),
                    lambda content: ClusterRenamed(
                        cluster=c, name=content.name, rationale=content.rationale
                    ),
                )
                touched = [r]
            case EditMethod(requirement=req):
                r = NodeRef(kind=NodeKind.METHOD, key=req)
                steps = _undo_edit(
                    old.node(r),
                    lambda content: MethodEdited(
                        requirement=req, methods=content.methods, rationale=content.rationale
                    ),
                )
                touched = [r]
            case EditTestCase(case=key):
                r = NodeRef(kind=NodeKind.TEST_CASE, key=key)
                steps = _undo_edit(
                    old.node(r), lambda content: TestCaseEdited(case=key, content=content)
                )
                touched = [r]
            case Pin(node=r):
                steps, touched = [UndoStep(event=NodeUnpinned(node=r))], [r]
            case Unpin(node=r):
                steps, touched = [UndoStep(event=NodePinned(node=r))], [r]
            case _:
                return None
        expected = {str(r): (new.nodes[r].version if r in new.nodes else 0) for r in touched}
        contents = {str(r): _fingerprint(new.nodes.get(r)) for r in touched}
        return UndoEntry(command=cmd.type, expected=expected, contents=contents, steps=tuple(steps))

    def _undo(self, cmd: Undo, actor: str) -> CommandResult:
        stack = self.record.undo.get(actor) or []
        if not stack:
            raise Rejected("nothing_to_undo")
        entry = stack[-1]
        self._check_undo(entry)
        tx = _Tx(self.state)
        for step in entry.steps:
            if step.event is not None:
                tx.apply(step.event)
            elif step.restore is not None:
                cached = self.store.get(self.pid, step.cache_key) if step.cache_key else None
                if cached is not None:
                    tx.settle([(step.restore, cached)])
            else:
                state = tx.state
                clusters = {
                    c: state.members(c)
                    for c in state.keys_of(NodeKind.CLUSTER)
                    if c not in step.remove
                }
                pinned = {c: _pinned_members(state, c) for c in clusters}
                clusters.update(step.clusters or {})
                pinned.update(step.pinned or {})
                tx.apply(MembershipChanged(clusters=clusters, pinned=pinned))
        tx.resolve(self.store)

        def pop(rec: ProjectRecord) -> None:
            rec.undo[actor] = rec.undo[actor][:-1]

        return self._applied(cmd, actor, tx, mutate=pop)

    def _check_undo(self, entry: UndoEntry) -> None:
        """Each node the undo writes back must be as the command left it: same version, or the
        same content and pin (another undo may have restored it with a newer version)."""
        current = {}
        for key, version in entry.expected.items():
            node = self.state.get(_ref_of(key))
            current[key] = node.version if node is not None else 0
            if current[key] != version and _fingerprint(node) != entry.contents.get(key):
                conflict = True
                break
        else:
            conflict = False
        if conflict:
            raise Rejected(
                "version_conflict",
                {
                    k: (n.version if (n := self.state.get(_ref_of(k))) else 0)
                    for k in entry.expected
                },
            )

    # Commit -------------------------------------------------------------------------------------

    def _touched(self, old: ProjectState, new: ProjectState) -> frozenset[NodeRef]:
        """Nodes a change wrote, created, or whose expected hash it changed (stale ones)."""
        out = set()
        for r in new.ordered_refs():
            n, o = new.nodes[r], old.nodes.get(r)
            if o is not n:
                out.add(r)
            elif (
                n.status == Status.STALE
                and r.kind not in SOURCE_KINDS
                and r.kind not in CHILD_KINDS
                and old.stage_configs
                and expected_hash(old, r) != expected_hash(new, r)
            ):
                out.add(r)
        return frozenset(out)

    def _commit(
        self,
        new: ProjectState,
        *,
        tx: _Tx | None = None,
        invs: Sequence[Invalidation] = (),
        actor: str = "",
        before: Sequence[_Draft] = (),
        after: Sequence[_Draft] = (),
        cache_puts: Sequence[Result] = (),
        job_records: Sequence[JobRecord] = (),
        mutate: Callable[[ProjectRecord], None] | None = None,
        touched: frozenset[NodeRef] = frozenset(),
        approval: bool = False,
        settled: Iterable[NodeRef] = (),
    ) -> int:
        """See the module docstring. Returns the number of the last published event. `tx`: the
        steps that led to `new` (each persisted in order, so every stored version is +1)."""
        old = self.state
        chain = [*(tx.chain if tx else ()), new]
        invs = [*(tx.invs if tx else ()), *invs]
        settled = {*(tx.settled if tx else ()), *settled}
        log_events = tx.events if tx else ()
        record = self.record.model_copy(deep=True)
        if mutate is not None:
            mutate(record)
        record.stage_configs = dict(new.stage_configs) or record.stage_configs
        done = set(settled) | {r for r in old.nodes if r not in new.nodes}
        for inv in invs:
            done |= inv.cache_hits
            for r, hint in inv.hints.items():
                record.hints[str(r)] = hint
        for r in done:
            record.hints.pop(str(r), None)
        if approval:
            derived = {
                r
                for r in touched
                if r.kind not in SOURCE_KINDS
                and r.kind not in CHILD_KINDS
                and new.nodes[r].status == Status.STALE
            }
            record.needs_approval = sorted(
                set(record.needs_approval) | derived, key=NodeRef.sort_key
            )
        if done:
            record.needs_approval = [r for r in record.needs_approval if r not in done]
            record.approved = [r for r in record.approved if r not in done]

        waiting = self._gated(new, record)
        gate_drafts = [
            _Draft("stage_waiting_approval", {"stage": k.value, "count": len(v)})
            for k, v in sorted(waiting.items(), key=lambda kv: list(NodeKind).index(kv[0]))
            if v and not self._waiting.get(k)
        ]
        drafts = [*before, *self._node_drafts(old, new, actor), *gate_drafts, *after]
        first = record.last_seq + 1
        record.last_seq += len(drafts)

        with self.store.transaction():
            prev = old
            for step in chain:
                if step is not prev:
                    self._persist_nodes(prev, step)
                prev = step
            for event in log_events:
                self.store.append_event(self.pid, event, actor=actor or "system")
            for res in cache_puts:
                self.store.put(self.pid, res.cache_key, res)
            for job in job_records:
                self.store.put_job(self.pid, job)
            self.store.save_project(record)

        self.state = new
        self.record = record
        self._waiting = waiting
        self._user -= done
        self._forced -= {r for r in done}
        cancel = frozenset().union(*(inv.cancel for inv in invs)) if invs else frozenset()
        self._cancel(cancel)
        self._owner = {
            r: j
            for r, j in self._owner.items()
            if (n := new.nodes.get(r)) is not None and n.status == Status.RUNNING
        }
        events = []
        for i, d in enumerate(drafts):
            seq = first + i
            payload = d.payload
            if d.type in ("command_applied", "command_rejected"):
                payload = {**payload, "result": {**payload["result"], "seq": seq}}
            events.append(
                ServerEvent(
                    seq=seq, project_id=self.pid, type=d.type, actor=d.actor, payload=payload
                )
            )
        self._publish(events)
        self._user |= {
            r for r in touched - done if r.kind not in SOURCE_KINDS and r.kind not in CHILD_KINDS
        }
        self._schedule(touched)
        return record.last_seq

    def _persist_nodes(self, old: ProjectState, new: ProjectState) -> None:
        """Write the difference: new versions (compare-and-set on the stored version), removals,
        status changes. Placeholders (version 0) are never stored; memory mirrors the store for
        every node with a version."""
        pid = self.pid
        refs = [
            r
            for r in old.nodes.keys() | new.nodes.keys()
            if old.nodes.get(r) is not new.nodes.get(r)
        ]
        for r in sorted(refs, key=NodeRef.sort_key):
            o, n = old.nodes.get(r), new.nodes.get(r)
            stored = o.version if o is not None else 0
            if n is None:
                if stored:
                    self.store.remove_node(pid, r, expected_version=stored)
            elif n.version == 0:
                if stored:  # pragma: no cover - versions only grow while a node exists
                    raise RuntimeError(f"{r}: version went from {stored} to 0")
            elif n.version != stored:
                if n.version != stored + 1:
                    if n.version != 1:  # pragma: no cover - one transition writes one version
                        raise RuntimeError(f"{r}: version jumped from {stored} to {n.version}")
                    self.store.remove_node(pid, r, expected_version=stored)  # removed, recreated
                    stored = 0
                self.store.put_node(pid, n, expected_version=stored)
            elif o is not None and o.status != n.status and n.version:
                self.store.set_status(pid, r, n.status)

    def _node_drafts(self, old: ProjectState, new: ProjectState, actor: str) -> list[_Draft]:
        a0, a1 = analyze(old), analyze(new)
        refs = {
            r
            for r in old.nodes.keys() | new.nodes.keys()
            if old.nodes.get(r) is not new.nodes.get(r)
        }
        refs |= a0.to_verify ^ a1.to_verify
        out = []
        for r in sorted(refs, key=NodeRef.sort_key):
            o, n = old.nodes.get(r), new.nodes.get(r)
            if n is None:
                out.append(_Draft("node_removed", {"ref": r.model_dump(mode="json")}, actor))
                continue
            vn = node_view(new, n, a1.to_verify)
            if o is None:
                out.append(_Draft("node_created", {"node": vn.model_dump(mode="json")}, actor))
                continue
            vo = node_view(old, o, a0.to_verify)
            if vo == vn:
                continue
            kind: ServerEventType = (
                "node_stale" if vn.status == "stale" and vo.status != "stale" else "node_updated"
            )
            out.append(_Draft(kind, {"node": vn.model_dump(mode="json")}, actor))
        return out

    def _publish(self, events: Sequence[ServerEvent], *, keep: bool = True) -> None:
        for e in events:
            if keep:
                self._buffer.append(e)
            for sub in list(self._subscribers):
                sub.queue.put_nowait(e)

    def _cancel(self, cancel: frozenset[NodeRef]) -> None:
        by_job: dict[int, set[NodeRef]] = {}
        for r in cancel:
            j = self._owner.get(r)
            if j is not None:
                by_job.setdefault(j, set()).add(r)
        for j, refs in by_job.items():
            owned = {r for r, o in self._owner.items() if o == j}
            if owned <= refs:
                self.queue.cancel(j)

    # Scheduling ---------------------------------------------------------------------------------

    def _gated(
        self, state: ProjectState, record: ProjectRecord
    ) -> dict[NodeKind, frozenset[NodeRef]]:
        """Ready nodes a gate holds, by stage."""
        needs = set(record.needs_approval)
        approved = set(record.approved)
        out: dict[NodeKind, set[NodeRef]] = {}
        for r in analyze(state).ready:
            if r in self._forced:
                continue
            mode = record.stage_modes.get(r.kind, "auto")
            if r in needs or (mode == "approval" and r not in approved):
                out.setdefault(r.kind, set()).add(r)
        return {k: frozenset(v) for k, v in out.items()}

    def _eligible_forced(self, state: ProjectState) -> list[NodeRef]:
        an = analyze(state)
        out = []
        for r in sorted(self._forced, key=NodeRef.sort_key):
            node = state.get(r)
            if node is None or node.pinned or node.status not in (Status.STALE, Status.FAILED):
                continue
            if all(
                (u_node := state.nodes[u]).status == Status.FRESH
                and u not in an.to_verify
                or (u_node.pinned and u_node.status == Status.STALE)
                for u in upstream(state, r)
            ):
                out.append(r)
        return out

    def _key(self, r: NodeRef) -> str:
        if stages.get(r.kind).batched:
            return f"{self.pid}|{r.kind.value}"
        key = f"{self.pid}|{r}"
        self._key_refs[key] = r
        return key

    def _priority(self, r: NodeRef) -> Priority:
        if r in self._forced or any(r in f for f in self._focus.values()):
            return "P0"
        return "P1" if r in self._user else "P2"

    def _collect(self, key: str) -> list[NodeRef]:
        """The nodes a job with this key produces now: ready and not held by a gate, or forced."""
        state = self.state
        held = frozenset().union(*self._waiting.values()) if self._waiting else frozenset()
        candidates = [r for r in analyze(state).ready if r not in held]
        candidates += [r for r in self._eligible_forced(state) if r not in candidates]
        if key in self._key_refs:
            return [r for r in candidates if r == self._key_refs[key]]
        kind = NodeKind(key.split("|", 1)[1])
        return sorted((r for r in candidates if r.kind == kind), key=NodeRef.sort_key)

    def _schedule(self, touched: frozenset[NodeRef] = frozenset()) -> None:
        state = self.state
        held = frozenset().union(*self._waiting.values()) if self._waiting else frozenset()
        candidates = [r for r in analyze(state).ready if r not in held]
        candidates += [r for r in self._eligible_forced(state) if r not in candidates]
        wanted: dict[str, tuple[Priority, bool]] = {}
        for r in candidates:
            key = self._key(r)
            prio, restart = wanted.get(key, ("P2", False))
            wanted[key] = (better(prio, self._priority(r)), restart or r in touched)
        delay = self.deps.orchestrator.debounce_s
        for key, (prio, restart) in wanted.items():
            if restart or not self.queue.is_pending(key):
                self.queue.submit(key, prio, self._runner(key), delay=delay if restart else 0.0)
            else:
                self.queue.reprioritize(key, prio)
        prefix = f"{self.pid}|"
        for p in self.queue.pending():
            if p.key.startswith(prefix) and p.key not in wanted:
                self.queue.drop(p.key)

    def _runner(self, key: str) -> Callable[[int], Any]:
        async def run(job_id: int) -> None:
            await self._run_job(key, job_id)

        return run

    # Jobs ---------------------------------------------------------------------------------------

    async def _run_job(self, key: str, job_id: int) -> None:
        refs = self._collect(key)
        if not refs:
            return
        state = self.state
        hits = []
        for r in refs:
            cached = self.store.get(self.pid, cache_key(state, r))
            if cached is not None:
                hits.append((r, cached))
        if hits:
            tx = _Tx(state)
            out = tx.settle(hits)
            self._commit(tx.state, tx=tx)
            refs = [r for r in self._collect(key) if r not in out.accepted]
            if not refs:
                return
        kind = refs[0].kind
        spec = stages.get(kind)
        if spec.produce is None:  # pragma: no cover - every stage has a producer (paket 3)
            raise RuntimeError(f"stage {kind} has no producer")
        running = self.state
        for r in refs:
            running = mark_running(running, r)
        priority = next((x.priority for x in self.queue.running() if x.job_id == job_id), "P2")
        record = JobRecord(
            job_id=f"{self.pid}-{self._session}-j{job_id}",
            stage=kind,
            nodes=list(refs),
            priority=priority,
            state="running",
            started_at=time.time(),
        )
        job = _Job(job_id, key, kind, tuple(refs), priority, record)
        self._jobs[job_id] = job
        self._forced -= set(refs)
        self._commit(
            running,
            before=[_job_draft("job_started", job)],
            job_records=[record],
        )
        for r in refs:
            self._owner[r] = job_id
        hint = self._hint(refs[0]) if len(refs) == 1 else None
        ctx = ProduceContext(
            state=self.state,
            refs=tuple(refs),
            settings=self.deps.settings,
            hint=hint,
            sources=self._sources(hint),
            embed=self.deps.embed,
            retrieve=self.deps.retrieve,
            passages=self.deps.passages,
        )
        token = _PROGRESS.set(lambda text: self._progress(job, text))
        try:
            outcome = await spec.produce(ctx, self.deps.complete)
        except asyncio.CancelledError:
            self._end_cancelled(job)
            raise
        except Exception as exc:  # noqa: BLE001 - fails the job's nodes only
            why = f"{type(exc).__name__}: {exc}"[:2000]
            log.warning("job %s failed: %s", record.job_id, why)
            outcome = ProduceOutcome(failed={r: why for r in refs})
        finally:
            _PROGRESS.reset(token)
        self._finish(job, outcome)

    def _finish(self, job: _Job, outcome: ProduceOutcome) -> None:
        tx = _Tx(self.state)
        settled = tx.settle(list(outcome.results))
        new = tx.state
        owned = {r for r in job.refs if self._owner.get(r) == job.job_id}
        failed: dict[NodeRef, str] = {}
        for r, why in outcome.failed.items():
            node = new.nodes.get(r)
            if r in owned and node is not None and node.status == Status.RUNNING:
                new = mark_failed(new, r)
                failed[r] = why
        for r in owned - settled.accepted - set(failed):
            new = release(new, r)
        calls = sum(int(s.get("calls") or 0) for s in outcome.stats.values())
        record = job.record.model_copy(
            update={
                "state": "failed" if failed else "done",
                "finished_at": time.time(),
                "error": "; ".join(
                    f"{r}: {w}" for r, w in sorted(failed.items(), key=lambda x: x[0].sort_key())
                )[:4000],
                "calls": calls,
            }
        )
        draft = _job_draft("job_failed" if failed else "job_done", job)
        draft.payload["accepted"] = sorted(str(r) for r in settled.accepted)
        if failed:
            draft.payload["errors"] = {str(r): w for r, w in failed.items()}
        self._jobs.pop(job.job_id, None)
        self._commit(
            new,
            tx=tx,
            cache_puts=[res for _, res in outcome.results],
            job_records=[record],
            after=[draft],
        )

    def _end_cancelled(self, job: _Job) -> None:
        self._jobs.pop(job.job_id, None)
        new = self.state
        for r in job.refs:
            if self._owner.get(r) == job.job_id:
                new = release(new, r)
        record = job.record.model_copy(update={"state": "cancelled", "finished_at": time.time()})
        draft = _job_draft("job_done", job)
        draft.payload["cancelled"] = True
        try:
            self._commit(new, job_records=[record], after=[draft])
        except Exception:  # noqa: BLE001 - shutting down; the reload releases running nodes
            log.exception("could not record the cancellation of %s", record.job_id)

    def _progress(self, job: _Job, text: str) -> None:
        event = ServerEvent(
            seq=self.record.last_seq,
            project_id=self.pid,
            type="job_progress",
            payload={"job": job.view().model_dump(mode="json"), "text": text},
        )
        self._publish([event], keep=False)

    def _hint(self, r: NodeRef) -> Hint | None:
        return self.record.hints.get(str(r))

    def _sources(self, hint: Hint | None) -> dict[NodeRef, list[TestCaseContent]]:
        """Merge: the unpinned cases of each removed source set, from store history (the set's
        last version and each case's last version)."""
        out: dict[NodeRef, list[TestCaseContent]] = {}
        if hint is None or hint.mode != "merge":
            return out
        for src in hint.sources:
            versions = [
                n
                for n in self.store.history(self.pid, src)
                if isinstance(n.content, TestSetContent)
            ]
            if not versions:
                continue
            cases = []
            for key in versions[-1].content.case_keys:  # type: ignore[union-attr]
                hist = self.store.history(self.pid, NodeRef(kind=NodeKind.TEST_CASE, key=key))
                if hist and isinstance(hist[-1].content, TestCaseContent) and not hist[-1].pinned:
                    cases.append(hist[-1].content)
            out[src] = cases
        return out


# Helpers ----------------------------------------------------------------------------------------


def _command_draft(
    kind: ServerEventType, cmd: Command, result: CommandResult, actor: str
) -> _Draft:
    return _Draft(
        kind,
        {"command": cmd.model_dump(mode="json"), "result": result.model_dump(mode="json")},
        actor,
    )


def _job_draft(kind: ServerEventType, job: _Job) -> _Draft:
    return _Draft(
        kind,
        {
            "job": job.view().model_dump(mode="json"),
            "nodes": [str(r) for r in job.refs],
            "stage": job.stage.value,
        },
    )


def _lock_targets(cmd: Command) -> list[NodeRef]:
    match cmd:
        case EditRequirement(requirement=req):
            return [NodeRef(kind=NodeKind.REQUIREMENT, key=req)]
        case EditTestCase(case=key):
            return [NodeRef(kind=NodeKind.TEST_CASE, key=key)]
        case EditMethod(requirement=req):
            return [NodeRef(kind=NodeKind.METHOD, key=req)]
        case RenameCluster(cluster=c):
            return [NodeRef(kind=NodeKind.CLUSTER_LABEL, key=c)]
        case EditProjectCard():
            return [CARD]
        case Pin(node=r) | Unpin(node=r) | KeepMine(node=r):
            return [r]
    return []


def _undo_edit(old: Node, event_for: Callable[[Any], Event]) -> list[UndoStep]:
    """Undo of a user edit of a derived node or a test case: the old content back as it was
    (pinned edit, generated case, generated output from the cache)."""
    r = old.ref
    if old.content is None:
        return [UndoStep(event=NodeUnpinned(node=r))]
    if old.pinned:
        return [UndoStep(event=event_for(old.content))]
    if r.kind in CHILD_KINDS:
        return [UndoStep(event=event_for(old.content)), UndoStep(event=NodeUnpinned(node=r))]
    return [UndoStep(event=NodeUnpinned(node=r)), UndoStep(restore=r, cache_key=old.cache_key)]


def _pinned_members(state: ProjectState, cluster: str) -> tuple[str, ...]:
    content = state.node(_CL(cluster)).content
    assert isinstance(content, ClusterContent)
    return content.pinned_members


def _max_cluster_number(keys: Iterable[str]) -> int:
    numbers = [int(m.group(1)) for k in keys if (m := re.fullmatch(r"C(\d+)", k))]
    return max(numbers, default=0)


__all__ = [
    "ProjectRuntime",
    "Rejected",
    "RuntimeDeps",
    "node_view",
    "report_progress",
]
