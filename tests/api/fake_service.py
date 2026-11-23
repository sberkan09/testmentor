"""In-memory `ProjectService` for the API tests (paket 6): not the orchestrator.

Projects come from `build_project` and `drive` with the fake model. Commands: version check,
edit locks, an event sequence, a ring of kept events and live subscribers. Only
`move_requirement`, `edit_test_case`, `pin` and `unpin` change the state; the other commands are
accepted and only produce `command_applied` (`undo` is `nothing_to_undo`).
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from core.graph import ProjectState
from core.matrix_view import matrix_rows
from core.nodes import ClusterContent, Node, NodeKind, NodeRef, Origin
from eval.stage_driver import drive
from services.fake_llm import FakeComplete, FakeEmbed
from services.importer import build_project
from services.settings import load_stage_settings, stage_configs
from services.xlsx_export import matrix_xlsx
from worker.contracts import (
    CommandRequest,
    CommandResult,
    EditTestCase,
    ImportRequest,
    MoveRequirement,
    NodeView,
    Pin,
    ServerEvent,
    Snapshot,
    Undo,
    Unpin,
)

HIDDEN = {NodeKind.EMBEDDING, NodeKind.CLUSTERING}
LOCK_S = 60.0


def node_view(node: Node) -> NodeView:
    return NodeView(
        ref=node.ref,
        status=node.status.value,  # type: ignore[arg-type]
        pinned=node.pinned,
        origin=node.origin.value,  # type: ignore[arg-type]
        version=node.version,
        content=node.content.model_dump(mode="json") if node.content is not None else None,
        produced_by=(
            node.produced_by.model_dump(mode="json", exclude={"params"})
            if node.produced_by
            else None
        ),
    )


class _Subscription:
    """Registered when created, so no event between `subscribe` and the first read is lost."""

    def __init__(self, hub: list[asyncio.Queue[ServerEvent]]) -> None:
        self._hub = hub
        self._queue: asyncio.Queue[ServerEvent] = asyncio.Queue()
        hub.append(self._queue)

    def __aiter__(self) -> _Subscription:
        return self

    async def __anext__(self) -> ServerEvent:
        try:
            return await self._queue.get()
        except asyncio.CancelledError:
            self.close()
            raise

    def close(self) -> None:
        if self._queue in self._hub:
            self._hub.remove(self._queue)


@dataclass
class _Project:
    name: str
    state: ProjectState
    seq: int = 0
    ring: deque[ServerEvent] = field(default_factory=deque)
    subscribers: list[asyncio.Queue[ServerEvent]] = field(default_factory=list)
    locks: dict[str, tuple[str, float]] = field(default_factory=dict)


class FakeProjectService:
    def __init__(self, *, ring_size: int = 200) -> None:
        self.ring_size = ring_size
        self._projects: dict[str, _Project] = {}
        self._settings = load_stage_settings()

    # Service ------------------------------------------------------------------------------------

    async def create_project(self, request: ImportRequest, data: bytes, filename: str) -> Snapshot:
        if request.key in self._projects:
            raise ValueError(f"project {request.key} exists")
        embed = FakeEmbed()
        settings = self._settings
        state = await build_project(
            request,
            data,
            filename,
            embed=embed,
            settings=settings,
            stage_configs=stage_configs(settings, model="fake", embedding_model_version="fake-e"),
        )
        driven = await drive(
            state, FakeComplete(settings.test_method), settings=settings, embed=embed
        )
        if driven.errors:
            raise RuntimeError(f"fake generation failed: {driven.errors}")
        self._projects[request.key] = _Project(request.name, driven.state)
        return self.snapshot(request.key)

    def projects(self) -> list[tuple[str, str]]:
        return [(pid, p.name) for pid, p in self._projects.items()]

    def snapshot(self, project_id: str) -> Snapshot:
        p = self._projects[project_id]
        self._expire(p)
        nodes = tuple(
            node_view(p.state.nodes[r]) for r in p.state.ordered_refs() if r.kind not in HIDDEN
        )
        return Snapshot(
            project_id=project_id,
            name=p.name,
            seq=p.seq,
            nodes=nodes,
            stages=(),
            jobs=(),
            matrix=tuple(matrix_rows(p.state, self._settings.test_method)),
            locks={k: user for k, (user, _) in p.locks.items()},
        )

    def events_after(self, project_id: str, seq: int) -> list[ServerEvent] | None:
        p = self._projects[project_id]
        if seq >= p.seq:
            return []
        if not p.ring or p.ring[0].seq > seq + 1:
            return None
        return [e for e in p.ring if e.seq > seq]

    def subscribe(self, project_id: str) -> AsyncIterator[ServerEvent]:
        return _Subscription(self._projects[project_id].subscribers)

    def lock(self, project_id: str, ref: NodeRef, actor: str) -> bool:
        p = self._projects[project_id]
        self._expire(p)
        holder = p.locks.get(str(ref))
        if holder is not None and holder[0] != actor:
            return False
        if holder is None:
            self._emit(p, "lock_changed", actor, {"ref": str(ref), "user": actor})
        p.locks[str(ref)] = (actor, time.monotonic() + LOCK_S)
        return True

    def matrix_xlsx(self, project_id: str) -> bytes:
        return matrix_xlsx(self._projects[project_id].state, self._settings.test_method)

    async def command(self, project_id: str, request: CommandRequest, actor: str) -> CommandResult:
        p = self._projects[project_id]
        self._expire(p)
        cmd = request.command

        def reject(reason: str, versions: dict[str, int] | None = None) -> CommandResult:
            return CommandResult(
                accepted=False, seq=p.seq, reason=reason, current_versions=versions or {}
            )

        # Version check.
        current: dict[str, int] = {}
        stale = False
        for key, expected in request.expected_versions.items():
            kind, _, node_key = key.partition(":")
            node = p.state.get(NodeRef(kind=NodeKind(kind), key=node_key))
            have = node.version if node is not None else 0
            current[key] = have
            stale = stale or have != expected
        if stale:
            return reject("version_conflict", current)

        touched = self._touched(p, cmd)
        for ref in touched:
            holder = p.locks.get(str(ref))
            if holder is not None and holder[0] != actor:
                return reject(f"locked: {ref} is being edited by {holder[0]}")

        if isinstance(cmd, Undo):
            return reject("nothing_to_undo")

        changed: list[Node] = []
        if isinstance(cmd, MoveRequirement):
            src = p.state.cluster_of(cmd.requirement)
            target = NodeRef(kind=NodeKind.CLUSTER, key=cmd.to_cluster)
            if src is None or p.state.get(target) is None:
                return reject("invalid: unknown requirement or cluster")
            if src == cmd.to_cluster:
                return reject("invalid: already in that cluster")
            members = p.state.members(src)
            if len(members) == 1:
                return reject("invalid: a cluster cannot be left empty")
            changed += [
                self._with_members(
                    p, src, tuple(m for m in members if m != cmd.requirement), actor
                ),
                self._with_members(
                    p, cmd.to_cluster, (*p.state.members(cmd.to_cluster), cmd.requirement), actor
                ),
            ]
        elif isinstance(cmd, EditTestCase):
            ref = NodeRef(kind=NodeKind.TEST_CASE, key=cmd.case)
            node = p.state.get(ref)
            if node is None:
                return reject("invalid: unknown test case")
            changed.append(
                node.model_copy(
                    update={
                        "content": cmd.content,
                        "origin": Origin.EDITED,
                        "version": node.version + 1,
                    }
                )
            )
        elif isinstance(cmd, Pin | Unpin):
            node = p.state.get(cmd.node)
            if node is None:
                return reject("invalid: unknown node")
            changed.append(
                node.model_copy(
                    update={"pinned": isinstance(cmd, Pin), "version": node.version + 1}
                )
            )

        if changed:
            nodes = dict(p.state.nodes)
            for n in changed:
                nodes[n.ref] = n
            p.state = p.state.model_copy(update={"nodes": nodes})
        for n in changed:
            self._emit(p, "node_updated", actor, {"node": node_view(n).model_dump(mode="json")})
        result_body = CommandResult(accepted=True, seq=p.seq + 1)
        last = self._emit(
            p,
            "command_applied",
            actor,
            {"command": cmd.model_dump(mode="json"), "result": result_body.model_dump(mode="json")},
        ).seq
        return CommandResult(accepted=True, seq=last)

    # Helpers ------------------------------------------------------------------------------------

    @staticmethod
    def _touched(p: _Project, cmd: Any) -> list[NodeRef]:
        if isinstance(cmd, EditTestCase):
            return [NodeRef(kind=NodeKind.TEST_CASE, key=cmd.case)]
        if isinstance(cmd, Pin | Unpin):
            return [cmd.node]
        return []

    def _with_members(
        self, p: _Project, cluster: str, members: tuple[str, ...], actor: str
    ) -> Node:
        node = p.state.node(NodeRef(kind=NodeKind.CLUSTER, key=cluster))
        assert isinstance(node.content, ClusterContent)
        return node.model_copy(
            update={
                "content": node.content.model_copy(update={"members": members}),
                "version": node.version + 1,
            }
        )

    def _emit(self, p: _Project, type_: str, actor: str, payload: dict[str, Any]) -> ServerEvent:
        p.seq += 1
        event = ServerEvent(
            seq=p.seq,
            project_id=next(pid for pid, q in self._projects.items() if q is p),
            type=type_,  # type: ignore[arg-type]
            actor=actor,
            payload=payload,
        )
        p.ring.append(event)
        while len(p.ring) > self.ring_size:
            p.ring.popleft()
        for q in p.subscribers:
            q.put_nowait(event)
        return event

    def _expire(self, p: _Project) -> None:
        now = time.monotonic()
        for key in [k for k, (_, until) in p.locks.items() if until < now]:
            del p.locks[key]

    # Test hooks ---------------------------------------------------------------------------------

    def publish_progress(self, project_id: str, text: str) -> None:
        """A live `job_progress` event (no seq of its own: carries the current one)."""
        p = self._projects[project_id]
        event = ServerEvent(
            seq=p.seq, project_id=project_id, type="job_progress", payload={"text": text}
        )
        for q in p.subscribers:
            q.put_nowait(event)


__all__ = ["FakeProjectService", "node_view"]
