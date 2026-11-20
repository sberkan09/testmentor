"""Invalidation: from an event to the nodes it stales (docs/tasarim.md, Hangi düzenleme neyi
bayatlatır).

Rules (docs/tasarim.md, Veri modeli kuralları):
- A derived node is stale iff its recorded `input_hash` differs from `expected_hash`, or it was
  never produced. Expected hashes are recomputed for the whole project after every change.
- A node that is not stale but has a non-fresh node upstream (stale, running, failed, or itself
  waiting) is in `to_verify`: its status stays fresh and it is not queued until its upstream
  settles. If the upstream result is unchanged it stays fresh (early cutoff).
- A pinned stale node is never regenerated: it is reported in `pinned_warnings`, not counted in
  `llm_calls`, and does not block its dependents (the user's pinned value is authoritative).
- A running node whose expected hash changes becomes stale and is listed in `cancel`; a result
  produced for an old hash is not written to the node (`settle` rejects it).
- Status changes are not versions; only content changes are (production, edit, carrying a
  pinned case, keep). An edit stamps the node with its current expected hash, so editing a
  stale node makes it fresh; `NodeKept` does the same without changing content.
- A failed node is not queued, blocks its dependents like a stale one, and becomes stale again
  when its inputs change. `mark_running` also accepts a failed node (retry).
- Pinned test cases of a removed set are carried to the set of the cluster that now holds the
  first requirement they cover, re-keyed `<cluster>:<case id>` (`<cluster>:<old cluster>.<case
  id>` on collision), still pinned; listed in `carried`.
- `stale` and `llm_calls` count only nodes in status stale; running and failed nodes are
  reported separately.
- With an output cache, stale nodes whose `cache_key` hits are settled from the cache, in
  topological order until nothing more hits; they are listed in `cache_hits`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.events import Event
from core.graph import ProjectState
from core.nodes import NodeRef, Result
from core.store import OutputCache


class Hint(BaseModel):
    """How the orchestrator should produce a stale node. Never part of a hash.

    `incremental`: the node has an earlier output to update; `full`: new node; `merge`: combine
    the outputs of `sources` (removed test sets of merged clusters, kept in store history).
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["full", "incremental", "merge"]
    sources: tuple[NodeRef, ...] = ()


class Analysis(BaseModel):
    """What the current state needs, independent of how it got there."""

    model_config = ConfigDict(frozen=True)

    stale: frozenset[NodeRef]
    to_verify: frozenset[NodeRef]
    ready: tuple[NodeRef, ...]
    """Stale, unpinned, not running, every upstream fresh or pinned; topological order."""
    pinned_warnings: frozenset[NodeRef]
    failed: frozenset[NodeRef]
    llm_calls: int
    """Stale, unpinned nodes of stages that call the model."""


class Invalidation(BaseModel):
    """Effect of one event or one settled result, relative to the state before it."""

    model_config = ConfigDict(frozen=True)

    stale: frozenset[NodeRef] = frozenset()
    """Nodes stale after the change that were not stale before it (pinned ones included).
    Every field below is likewise relative to the state before the change."""
    to_verify: frozenset[NodeRef] = frozenset()
    cancel: frozenset[NodeRef] = frozenset()
    removed: frozenset[NodeRef] = frozenset()
    carried: dict[NodeRef, NodeRef] = Field(default_factory=dict)
    """Pinned test cases of removed sets: old ref → new ref."""
    pinned_warnings: frozenset[NodeRef] = frozenset()
    cache_hits: frozenset[NodeRef] = frozenset()
    llm_calls: int = 0
    """Model calls the change adds: unpinned stale nodes of model stages after the change (and
    after cache hits) that did not need a call before it. Unpinning a stale node adds one."""
    requires_approval: bool = False
    hints: dict[NodeRef, Hint] = Field(default_factory=dict)


class Settled(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: ProjectState
    accepted: bool
    invalidation: Invalidation


def analyze(state: ProjectState) -> Analysis:
    raise NotImplementedError


def apply(
    state: ProjectState, event: Event, *, cache: OutputCache | None = None
) -> tuple[ProjectState, Invalidation]:
    """Apply one event: update source nodes or write an edited version (version + 1,
    `origin=edited`, `pinned=True`, `input_hash` = current expected hash), create placeholders
    for new derived nodes, remove nodes of deleted clusters and carry their pinned cases,
    recompute staleness, resolve cache hits."""
    raise NotImplementedError


def mark_running(state: ProjectState, ref: NodeRef) -> ProjectState:
    """The orchestrator started producing `ref` for its current expected hash."""
    raise NotImplementedError


def mark_failed(state: ProjectState, ref: NodeRef) -> ProjectState:
    """Production of `ref` failed (schema invalid after the retry, or an error)."""
    raise NotImplementedError


def settle(state: ProjectState, ref: NodeRef, result: Result) -> Settled:
    """Write a produced result if `result.input_hash` equals the node's current expected hash;
    otherwise reject it and leave the state unchanged (the caller may still cache it under its
    own key). For a test set, keep its pinned cases, write `result.cases` as new case nodes and
    remove the set's unpinned cases that are not in the result."""
    raise NotImplementedError
