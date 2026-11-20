"""Persistence interfaces (docs/tasarim.md, Veri modeli; Çok kullanıcılı çalışma).

`core/` imports no database driver: the Postgres implementation lives outside it (paket 5) and
must pass the same contract tests (`tests/core/test_store_contract.py`) as `InMemoryStore`.
Every call carries `project_id`; nothing crosses projects.

- Node versions are never deleted: an edit or a regeneration writes version + 1, undo switches
  versions, `remove` writes a tombstone and keeps the history.
- `put_node` is compare-and-set on `version`: a writer holding an old version gets
  `VersionConflict` and the current node, instead of the last writer silently winning.
- A version is a content change. Status changes go through `set_status`, which writes no version
  and no history entry. After removal the current version is 0 again: a recreated node starts at
  version 1 and its versions are appended to the same history.
"""

from __future__ import annotations

from typing import Protocol

from core.events import Event, EventRecord
from core.nodes import Node, NodeRef, Result, Status


class VersionConflict(Exception):
    def __init__(self, ref: NodeRef, expected: int, current: Node | None) -> None:
        super().__init__(
            f"{ref}: expected version {expected}, current {current and current.version}"
        )
        self.ref = ref
        self.expected = expected
        self.current = current


class OutputCache(Protocol):
    """Produced results by `cache_key`, so undo and repeated inputs cost no model call."""

    def get(self, project_id: str, cache_key: str) -> Result | None: ...

    def put(self, project_id: str, cache_key: str, result: Result) -> None: ...


class NodeStore(OutputCache, Protocol):
    def get_node(self, project_id: str, ref: NodeRef) -> Node | None:
        """Current version; None if absent or removed."""
        ...

    def put_node(self, project_id: str, node: Node, *, expected_version: int) -> None:
        """Store `node` as the new current version. Requires the stored current version to equal
        `expected_version` (0 for a new node) and `node.version == expected_version + 1`."""
        ...

    def remove_node(self, project_id: str, ref: NodeRef, *, expected_version: int) -> None: ...

    def set_status(self, project_id: str, ref: NodeRef, status: Status) -> None:
        """Update the current version's status in place; no version, no history entry."""
        ...

    def history(self, project_id: str, ref: NodeRef) -> list[Node]:
        """Every stored version, oldest first; kept after removal."""
        ...

    def load(self, project_id: str) -> dict[NodeRef, Node]:
        """Current, non-removed nodes of the project."""
        ...

    def append_event(self, project_id: str, event: Event, *, actor: str) -> int:
        """Append to the project's event log; returns its sequence number (1, 2, ...)."""
        ...

    def events(self, project_id: str, *, after: int = 0) -> list[EventRecord]: ...


class InMemoryStore:
    """Reference implementation for tests and the eval runner."""

    def __init__(self) -> None:
        self._current: dict[tuple[str, NodeRef], Node] = {}
        self._history: dict[tuple[str, NodeRef], list[Node]] = {}
        self._cache: dict[tuple[str, str], Result] = {}
        self._events: dict[str, list[EventRecord]] = {}

    def get(self, project_id: str, cache_key: str) -> Result | None:
        return self._cache.get((project_id, cache_key))

    def put(self, project_id: str, cache_key: str, result: Result) -> None:
        self._cache[(project_id, cache_key)] = result

    def get_node(self, project_id: str, ref: NodeRef) -> Node | None:
        return self._current.get((project_id, ref))

    def _check(self, project_id: str, ref: NodeRef, expected_version: int) -> Node | None:
        current = self._current.get((project_id, ref))
        if (current.version if current else 0) != expected_version:
            raise VersionConflict(ref, expected_version, current)
        return current

    def put_node(self, project_id: str, node: Node, *, expected_version: int) -> None:
        current = self._check(project_id, node.ref, expected_version)
        if node.version != expected_version + 1:
            raise VersionConflict(node.ref, expected_version, current)
        self._current[(project_id, node.ref)] = node
        self._history.setdefault((project_id, node.ref), []).append(node)

    def remove_node(self, project_id: str, ref: NodeRef, *, expected_version: int) -> None:
        if self._check(project_id, ref, expected_version) is None:
            raise VersionConflict(ref, expected_version, None)
        del self._current[(project_id, ref)]

    def set_status(self, project_id: str, ref: NodeRef, status: Status) -> None:
        key = (project_id, ref)
        self._current[key] = self._current[key].model_copy(update={"status": status})

    def history(self, project_id: str, ref: NodeRef) -> list[Node]:
        return list(self._history.get((project_id, ref), ()))

    def load(self, project_id: str) -> dict[NodeRef, Node]:
        return {r: n for (p, r), n in self._current.items() if p == project_id}

    def append_event(self, project_id: str, event: Event, *, actor: str) -> int:
        log = self._events.setdefault(project_id, [])
        log.append(EventRecord(seq=len(log) + 1, actor=actor, event=event))
        return len(log)

    def events(self, project_id: str, *, after: int = 0) -> list[EventRecord]:
        return [r for r in self._events.get(project_id, ()) if r.seq > after]
