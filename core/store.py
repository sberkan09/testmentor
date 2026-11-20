"""Persistence interfaces (docs/tasarim.md, Veri modeli; Çok kullanıcılı çalışma).

`core/` imports no database driver: the Postgres implementation lives outside it (paket 5) and
must pass the same contract tests (`tests/core/test_store_contract.py`) as `InMemoryStore`.
Every call carries `project_id`; nothing crosses projects.

- Node versions are never deleted: an edit or a regeneration writes version + 1, undo switches
  versions, `remove` writes a tombstone and keeps the history.
- `put` is compare-and-set on `version`: a writer holding an old version gets `VersionConflict`
  and the current node, instead of the last writer silently winning.
"""

from __future__ import annotations

from typing import Protocol

from core.events import Event, EventRecord
from core.nodes import Node, NodeRef, Result


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
        raise NotImplementedError

    def get(self, project_id: str, cache_key: str) -> Result | None:
        raise NotImplementedError

    def put(self, project_id: str, cache_key: str, result: Result) -> None:
        raise NotImplementedError

    def get_node(self, project_id: str, ref: NodeRef) -> Node | None:
        raise NotImplementedError

    def put_node(self, project_id: str, node: Node, *, expected_version: int) -> None:
        raise NotImplementedError

    def remove_node(self, project_id: str, ref: NodeRef, *, expected_version: int) -> None:
        raise NotImplementedError

    def history(self, project_id: str, ref: NodeRef) -> list[Node]:
        raise NotImplementedError

    def load(self, project_id: str) -> dict[NodeRef, Node]:
        raise NotImplementedError

    def append_event(self, project_id: str, event: Event, *, actor: str) -> int:
        raise NotImplementedError

    def events(self, project_id: str, *, after: int = 0) -> list[EventRecord]:
        raise NotImplementedError
