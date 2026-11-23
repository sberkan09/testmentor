"""The project example pool follows the user's approved test cases (docs/tasarim.md, Örnek havuzu;
paket 11).

A pinned test case (pinned by the user, or written by an edit) is an example of the project's
style: `sync_examples` adds it to the pool with the texts of the requirements it covers and drops
entries whose case is no longer pinned or gone. An edited case is a new example key.

A pool change alone re-checks no retrieval: examples change only when a cluster's retrieval runs
again for its own reasons (a new or changed cluster, a document upload). Pinning one test would
otherwise change the selection of most clusters and regenerate the whole project.

`ExampleSyncingService` wraps the orchestrator for the API: after every accepted command it syncs
that project's pool, and `synced_selection` makes a retrieval sync the pool once per process
before its first selection. The pool lives in memory: after a restart the first retrieval of a
project (a document upload, a membership change) rebuilds it from the stored pinned cases first,
so the selection does not run against an empty pool.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from core.graph import ProjectState
from core.nodes import NodeKind, NodeRef, RequirementContent, TestCaseContent
from core.prompts import render_example
from core.stages.base import Embed, SelectExamples
from services.kb_examples import ExamplePool, build_entry
from worker.contracts import CommandRequest, CommandResult

log = logging.getLogger(__name__)


def approved_cases(state: ProjectState) -> dict[str, tuple[TestCaseContent, list[str]]]:
    """Pinned test cases with the texts of the requirements they cover (missing ones skipped)."""
    out: dict[str, tuple[TestCaseContent, list[str]]] = {}
    requirements = set(state.keys_of(NodeKind.REQUIREMENT))
    for key in state.keys_of(NodeKind.TEST_CASE):
        node = state.node(NodeRef(kind=NodeKind.TEST_CASE, key=key))
        if not node.pinned or not isinstance(node.content, TestCaseContent):
            continue
        texts = []
        for rid in node.content.covers:
            if rid in requirements:
                req = state.node(NodeRef(kind=NodeKind.REQUIREMENT, key=rid)).content
                if isinstance(req, RequirementContent):
                    texts.append(req.text)
        if texts:
            out[key] = (node.content, texts)
    return out


async def sync_examples(
    pool: ExamplePool, project_id: str, state: ProjectState, embed: Embed
) -> bool:
    """Makes the project's pool the approved cases of `state`; True when it changed. Only new
    or edited cases are embedded."""
    desired = approved_cases(state)
    current = pool.entries(project_id)
    changed = False
    for key in sorted(set(current) - set(desired)):
        pool.remove(project_id, key)
        changed = True
    new = []
    for key, (case, texts) in sorted(desired.items()):
        old = current.get(key)
        if old is not None and old.text == render_example(texts, case):
            continue
        new.append(await build_entry(key, case, texts, embed))
    if new:
        pool.add(project_id, new)
        changed = True
    return changed


class ExampleSyncingService:
    """`ProjectService` of the API: the orchestrator, plus the pool sync after each accepted
    command. Everything else is delegated."""

    def __init__(self, inner: Any, pool: ExamplePool, embed: Embed) -> None:
        self._inner = inner
        self._pool = pool
        self._embed = embed
        self._synced: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}

    def bind(self, inner: Any) -> None:
        """Set the orchestrator (built after the tools that refer to this object)."""
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._inner, name)

    async def command(self, project_id: str, request: CommandRequest, actor: str) -> CommandResult:
        result = await self._inner.command(project_id, request, actor)
        if result.accepted:
            try:
                await self.sync(project_id)
            except Exception:  # the command is committed; the next retrieval syncs again
                self._synced.discard(project_id)
                log.exception(
                    "example pool sync failed for %s; retried before next retrieval", project_id
                )
        return result

    async def sync(self, project_id: str) -> bool:
        changed = await sync_examples(
            self._pool, project_id, self._inner.runtime(project_id).state, self._embed
        )
        self._synced.add(project_id)
        return changed

    async def ensure_synced(self, project_id: str) -> None:
        """Sync once per process (later changes come through `command`)."""
        if project_id in self._synced:
            return
        async with self._locks.setdefault(project_id, asyncio.Lock()):
            if project_id not in self._synced:
                await self.sync(project_id)

    def synced_selection(
        self, project_id: str, select: SelectExamples | None
    ) -> SelectExamples | None:
        """`select` that first makes sure the project's pool was built in this process."""
        if select is None:
            return None

        async def selected(members: Sequence[RequirementContent]) -> list[str]:
            await self.ensure_synced(project_id)
            return await select(members)

        return selected
