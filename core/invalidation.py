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

from core import stages
from core.events import (
    APPROVAL_EVENTS,
    ClusterCreated,
    ClusterDeleted,
    ClusterRenamed,
    ClustersMerged,
    Event,
    KbDocumentAdded,
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
from core.graph import (
    ProjectState,
    cache_key,
    case_cluster,
    expected_hash,
    upstream,
    with_declared_nodes,
)
from core.nodes import (
    CHILD_KINDS,
    KB_INDEX_KEY,
    PROJECT_CARD_KEY,
    SOURCE_KINDS,
    ClusterContent,
    ClusterLabelContent,
    KbIndexContent,
    MethodContent,
    Node,
    NodeKind,
    NodeRef,
    Origin,
    ProducedBy,
    ProjectCardContent,
    Result,
    Status,
    TestCaseContent,
    TestSetContent,
    case_key,
)
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
    found = state._memo.get("analysis")
    if found is not None:
        return found
    stale: set[NodeRef] = set()
    failed: set[NodeRef] = set()
    pinned_warnings: set[NodeRef] = set()
    blocking: set[NodeRef] = set()
    waiting: set[NodeRef] = set()
    ready: list[NodeRef] = []
    llm_calls = 0
    for r in state.ordered_refs():
        node = state.nodes[r]
        unsettled = any(u in blocking or u in waiting for u in upstream(state, r))
        if node.status == Status.STALE:
            stale.add(r)
            if node.pinned:
                pinned_warnings.add(r)  # authoritative for its dependents: does not block
                continue
            blocking.add(r)
            if stages.get(r.kind).uses_llm:
                llm_calls += 1
            if not unsettled:
                ready.append(r)
        elif node.status in (Status.RUNNING, Status.FAILED):
            blocking.add(r)
            if node.status == Status.FAILED:
                failed.add(r)
        elif unsettled:
            waiting.add(r)
    analysis = Analysis(
        stale=frozenset(stale),
        to_verify=frozenset(waiting),
        ready=tuple(ready),
        pinned_warnings=frozenset(pinned_warnings),
        failed=frozenset(failed),
        llm_calls=llm_calls,
    )
    state._memo["analysis"] = analysis
    return analysis


def apply(
    state: ProjectState, event: Event, *, cache: OutputCache | None = None
) -> tuple[ProjectState, Invalidation]:
    """Apply one event: update source nodes or write an edited version (version + 1,
    `origin=edited`, `pinned=True`, `input_hash` = current expected hash), create placeholders
    for new derived nodes, remove nodes of deleted clusters and carry their pinned cases,
    recompute staleness, resolve cache hits."""
    nodes = dict(state.nodes)
    configs = state.stage_configs
    merges: dict[NodeRef, tuple[NodeRef, ...]] = {}

    match event:
        case RequirementMoved(requirement=req, to_cluster=to):
            mem = _membership(state)
            src = state.cluster_of(req)
            if src is None or to not in mem:
                raise ValueError(f"cannot move {req} to {to}")
            if src != to:
                _take(mem, req)
                mem[to][0].add(req)
                mem[to][1].add(req)
            _write_membership(state, nodes, mem, mode="user")
        case ClusterCreated(cluster=new, members=members):
            mem = _membership(state)
            if new in mem or any(state.cluster_of(m) is None for m in members):
                raise ValueError(f"cannot create cluster {new}")
            for m in members:
                _take(mem, m)
            mem[new] = (set(members), set(members))
            _write_membership(state, nodes, mem, mode="user")
        case ClusterDeleted(cluster=gone, destinations=dest):
            mem = _membership(state)
            if (
                gone not in mem
                or set(dest) != mem[gone][0]
                or any(d not in mem or d == gone for d in dest.values())
            ):
                raise ValueError(f"cannot delete cluster {gone} with {dest}")
            for req, d in dest.items():
                mem[d][0].add(req)
                mem[d][1].add(req)
            del mem[gone]
            _write_membership(state, nodes, mem, mode="user")
        case ClustersMerged(sources=sources, new_cluster=new):
            mem = _membership(state)
            if new in mem or any(c not in mem for c in sources) or len(set(sources)) < 2:
                raise ValueError(f"cannot merge {sources} into {new}")
            members: set[str] = set()
            pinned: set[str] = set()
            for c in sources:
                members |= mem[c][0]
                pinned |= mem[c][1]
                del mem[c]
            mem[new] = (members, pinned)
            _write_membership(state, nodes, mem, mode="user")
            merges[_ref(NodeKind.TEST_SET, new)] = tuple(
                _ref(NodeKind.TEST_SET, c) for c in sources
            )
        case MembershipChanged(clusters=clusters):
            placed = sorted(m for ms in clusters.values() for m in ms)
            if placed != sorted(state.keys_of(NodeKind.REQUIREMENT)):
                raise ValueError("membership must place every requirement exactly once")
            was_pinned = {m for c in state.keys_of(NodeKind.CLUSTER) for m in _pinned(state, c)}
            mem = {c: (set(ms), set(ms) & was_pinned) for c, ms in clusters.items()}
            _write_membership(state, nodes, mem, mode="algorithm")
        case ClusterRenamed(cluster=c, name=name, rationale=why):
            _edit(
                state,
                nodes,
                _ref(NodeKind.CLUSTER_LABEL, c),
                ClusterLabelContent(name=name, rationale=why),
            )
        case RequirementTextChanged(requirement=req, text=text):
            r = _ref(NodeKind.REQUIREMENT, req)
            _update_source(nodes, r, state.requirement(req).model_copy(update={"text": text}))
        case TestCaseEdited(case=key, content=content):
            _edit(state, nodes, _ref(NodeKind.TEST_CASE, key), content)
        case MethodEdited(requirement=req, methods=methods, rationale=why):
            _edit(
                state,
                nodes,
                _ref(NodeKind.METHOD, req),
                MethodContent(methods=methods, rationale=why),
            )
        case KbDocumentAdded(index_version=version):
            _update_source(
                nodes, _ref(NodeKind.KB_INDEX, KB_INDEX_KEY), KbIndexContent(version=version)
            )
        case ProjectCardChanged(text=text):
            _update_source(
                nodes, _ref(NodeKind.PROJECT_CARD, PROJECT_CARD_KEY), ProjectCardContent(text=text)
            )
        case StageConfigChanged(stage=kind, config=config):
            stages.get(kind)  # KeyError for an unknown stage
            configs = configs | {kind: config}
        case NodePinned(node=r) | NodeUnpinned(node=r):
            node = _editable(state, r)
            nodes[r] = node.model_copy(
                update={"pinned": isinstance(event, NodePinned), "version": node.version + 1}
            )
        case NodeKept(node=r):
            node = _editable(state, r)
            if not node.pinned or r.kind in CHILD_KINDS:
                raise ValueError(f"only a pinned derived node can be kept: {r}")
            nodes[r] = node.model_copy(
                update={
                    "input_hash": expected_hash(state, r),
                    "status": Status.FRESH,
                    "version": node.version + 1,
                    "produced_by": ProducedBy(mode="keep"),
                }
            )
        case _:
            raise ValueError(f"unknown event: {event!r}")

    new = state.model_copy(update={"nodes": nodes, "stage_configs": configs})
    new = with_declared_nodes(new)
    new, carried = _carry_cases(new)
    new = _refresh(state, new)
    new, hits = _resolve_cache(new, cache)
    return new, _diff(
        state,
        new,
        carried=carried,
        cache_hits=hits,
        requires_approval=event.type in APPROVAL_EVENTS,
        merges=merges,
    )


def mark_running(state: ProjectState, ref: NodeRef) -> ProjectState:
    """The orchestrator started producing `ref` for its current expected hash."""
    node = state.node(ref)
    if node.status not in (Status.STALE, Status.FAILED) or node.pinned:
        raise ValueError(f"{ref} is not waiting for production ({node.status})")
    return _with_statuses(state, {ref: Status.RUNNING})


def mark_failed(state: ProjectState, ref: NodeRef) -> ProjectState:
    """Production of `ref` failed (schema invalid after the retry, or an error)."""
    if not _is_derived(ref):
        raise ValueError(f"{ref} is not produced by a stage")
    return _with_statuses(state, {ref: Status.FAILED})


def settle(state: ProjectState, ref: NodeRef, result: Result) -> Settled:
    """Write a produced result if `result.input_hash` equals the node's current expected hash;
    otherwise reject it and leave the state unchanged (the caller may still cache it under its
    own key). For a test set, keep its pinned cases, write `result.cases` as new case nodes and
    remove the set's unpinned cases that are not in the result."""
    node = state.get(ref)
    if (
        node is None
        or not _is_derived(ref)
        or node.pinned
        or result.input_hash != expected_hash(state, ref)
    ):
        return Settled(state=state, accepted=False, invalidation=Invalidation())
    nodes = dict(state.nodes)
    content = result.content
    if ref.kind == NodeKind.TEST_SET:
        content = _write_cases(state, nodes, ref, result)
    nodes[ref] = node.model_copy(
        update={
            "content": content,
            "input_hash": result.input_hash,
            "cache_key": result.cache_key,
            "status": Status.FRESH,
            "origin": Origin.GENERATED,
            "version": node.version + 1,
            "produced_by": result.produced_by,
        }
    )
    new = _refresh(state, state.model_copy(update={"nodes": nodes}))
    return Settled(state=new, accepted=True, invalidation=_diff(state, new))


# Internals --------------------------------------------------------------------------------------

_HASH_MEMO = ("index", "deps", "reverse", "expected", "config_keys")


def _ref(kind: NodeKind, key: str) -> NodeRef:
    return NodeRef(kind=kind, key=key)


def _is_derived(ref: NodeRef) -> bool:
    return ref.kind not in SOURCE_KINDS and ref.kind not in CHILD_KINDS


def _with_statuses(state: ProjectState, statuses: dict[NodeRef, Status]) -> ProjectState:
    """Status-only change: hashes and lookups stay valid, so the memo is shared."""
    nodes = state.nodes | {
        r: state.nodes[r].model_copy(update={"status": st}) for r, st in statuses.items()
    }
    new = state.model_copy(update={"nodes": nodes})
    new._memo = {k: v for k, v in state._memo.items() if k in _HASH_MEMO}
    return new


def _refresh(before: ProjectState, state: ProjectState) -> ProjectState:
    """Recompute the status of every derived node from its hashes."""
    statuses: dict[NodeRef, Status] = {}
    for r in state.ordered_refs():
        if not _is_derived(r):
            continue
        node = state.nodes[r]
        expected = expected_hash(state, r)
        if node.status in (Status.RUNNING, Status.FAILED):
            unchanged = r in before.nodes and expected_hash(before, r) == expected
            status = node.status if unchanged else Status.STALE
        elif node.content is None or node.input_hash != expected:
            status = Status.STALE
        else:
            status = Status.FRESH
        if status != node.status:
            statuses[r] = status
    return _with_statuses(state, statuses) if statuses else state


def _resolve_cache(
    state: ProjectState, cache: OutputCache | None
) -> tuple[ProjectState, frozenset[NodeRef]]:
    hits: set[NodeRef] = set()
    if cache is None:
        return state, frozenset()
    progressed = True
    while progressed:
        progressed = False
        for r in analyze(state).ready:
            result = cache.get(state.project_id, cache_key(state, r))
            if result is None:
                continue
            out = settle(state, r, result)
            if out.accepted:
                state = out.state
                hits.add(r)
                progressed = True
    return state, frozenset(hits)


def _diff(
    before: ProjectState,
    after: ProjectState,
    *,
    carried: dict[NodeRef, NodeRef] | None = None,
    cache_hits: frozenset[NodeRef] = frozenset(),
    requires_approval: bool = False,
    merges: dict[NodeRef, tuple[NodeRef, ...]] | None = None,
) -> Invalidation:
    a0, a1 = analyze(before), analyze(after)
    calls0 = _llm_stale(a0)
    calls1 = _llm_stale(a1)
    stale = a1.stale - a0.stale
    hints: dict[NodeRef, Hint] = {}
    for r in stale:
        if r.kind != NodeKind.TEST_SET:
            continue
        if merges and r in merges:
            hints[r] = Hint(mode="merge", sources=merges[r])
        elif after.nodes[r].content is not None:
            hints[r] = Hint(mode="incremental")
        else:
            hints[r] = Hint(mode="full")
    cancel = {
        r
        for r, n in before.nodes.items()
        if n.status == Status.RUNNING and r in after.nodes and after.nodes[r].status == Status.STALE
    }
    return Invalidation(
        stale=stale,
        to_verify=a1.to_verify - a0.to_verify,
        cancel=frozenset(cancel),
        removed=frozenset(before.nodes.keys() - after.nodes.keys()),
        carried=carried or {},
        pinned_warnings=a1.pinned_warnings - a0.pinned_warnings,
        cache_hits=cache_hits,
        llm_calls=len(calls1 - calls0),
        requires_approval=requires_approval,
        hints=hints,
    )


def _llm_stale(a: Analysis) -> frozenset[NodeRef]:
    return frozenset(r for r in a.stale - a.pinned_warnings if stages.get(r.kind).uses_llm)


def _editable(state: ProjectState, ref: NodeRef) -> Node:
    node = state.get(ref)
    if node is None or ref.kind in SOURCE_KINDS:
        raise ValueError(f"not an editable node: {ref}")
    return node


def _edit(state: ProjectState, nodes: dict[NodeRef, Node], ref: NodeRef, content) -> None:
    """User edit: new version, pinned, stamped with the current expected hash."""
    node = _editable(state, ref)
    stamped = node.input_hash if ref.kind in CHILD_KINDS else expected_hash(state, ref)
    nodes[ref] = node.model_copy(
        update={
            "content": content,
            "input_hash": stamped,
            "cache_key": None,
            "status": Status.FRESH,
            "pinned": True,
            "origin": Origin.EDITED,
            "version": node.version + 1,
            "produced_by": ProducedBy(mode="edit"),
        }
    )


def _update_source(nodes: dict[NodeRef, Node], ref: NodeRef, content) -> None:
    node = nodes[ref]
    if node.content == content:
        return
    nodes[ref] = node.model_copy(
        update={
            "content": content,
            "origin": Origin.EDITED,
            "version": node.version + 1,
            "produced_by": ProducedBy(mode="user"),
        }
    )


Membership = dict[str, tuple[set[str], set[str]]]


def _pinned(state: ProjectState, cluster: str) -> tuple[str, ...]:
    content = state.node(_ref(NodeKind.CLUSTER, cluster)).content
    assert isinstance(content, ClusterContent)
    return content.pinned_members


def _membership(state: ProjectState) -> Membership:
    return {
        c: (set(state.members(c)), set(_pinned(state, c))) for c in state.keys_of(NodeKind.CLUSTER)
    }


def _take(mem: Membership, req: str) -> None:
    for members, pinned in mem.values():
        members.discard(req)
        pinned.discard(req)


def _write_membership(
    state: ProjectState, nodes: dict[NodeRef, Node], mem: Membership, *, mode: str
) -> None:
    """Write changed clusters; an emptied or dropped cluster is removed."""
    for c in state.keys_of(NodeKind.CLUSTER):
        if c not in mem or not mem[c][0]:
            del nodes[_ref(NodeKind.CLUSTER, c)]
    for c, (members, pinned) in mem.items():
        if not members:
            continue
        r = _ref(NodeKind.CLUSTER, c)
        content = ClusterContent(members=tuple(members), pinned_members=tuple(pinned & members))
        old = state.get(r)
        if old is not None and old.content == content:
            continue
        nodes[r] = Node(
            ref=r,
            content=content,
            origin=Origin.EDITED if mode == "user" else Origin.GENERATED,
            version=(old.version + 1) if old else 1,
            produced_by=ProducedBy(mode=mode),
        )


def _carry_cases(state: ProjectState) -> tuple[ProjectState, dict[NodeRef, NodeRef]]:
    """Drop test cases whose set is gone; carry the pinned ones (see module rules)."""
    sets = set(state.keys_of(NodeKind.TEST_SET))
    nodes: dict[NodeRef, Node] | None = None
    carried: dict[NodeRef, NodeRef] = {}
    for key in state.keys_of(NodeKind.TEST_CASE):
        old_cluster = case_cluster(key)
        if old_cluster in sets:
            continue
        if nodes is None:
            nodes = dict(state.nodes)
        r = _ref(NodeKind.TEST_CASE, key)
        node = nodes.pop(r)
        content = node.content
        if not node.pinned or not isinstance(content, TestCaseContent):
            continue
        dest = state.cluster_of(content.covers[0])
        if dest is None:
            continue
        new = _ref(NodeKind.TEST_CASE, case_key(dest, content.id))
        if new in nodes:
            new = _ref(NodeKind.TEST_CASE, case_key(dest, f"{old_cluster}.{content.id}"))
        nodes[new] = node.model_copy(
            update={"ref": new, "version": 1, "produced_by": ProducedBy(mode="carry")}
        )
        carried[r] = new
    if nodes is None:
        return state, carried
    return state.model_copy(update={"nodes": nodes}), carried


def _write_cases(
    state: ProjectState, nodes: dict[NodeRef, Node], set_ref: NodeRef, result: Result
) -> TestSetContent:
    cluster = set_ref.key
    existing = state.test_cases(cluster)
    pinned = {r for r in existing if state.node(r).pinned}
    previous = state.node(set_ref).content
    order = previous.case_keys if isinstance(previous, TestSetContent) else ()
    pinned_keys = [k for k in order if _ref(NodeKind.TEST_CASE, k) in pinned]
    pinned_keys += sorted(r.key for r in pinned if r.key not in pinned_keys)
    generated: list[str] = []
    for case in result.cases:
        r = _ref(NodeKind.TEST_CASE, case_key(cluster, case.id))
        if r in pinned or r.key in generated:
            continue
        old = state.get(r)
        version = 1 if old is None else old.version + int(old.content != case)
        nodes[r] = Node(
            ref=r,
            content=case,
            input_hash=result.input_hash,
            cache_key=result.cache_key,
            version=version,
            produced_by=result.produced_by,
        )
        generated.append(r.key)
    for r in existing:
        if r not in pinned and r.key not in generated:
            del nodes[r]
    return TestSetContent(case_keys=(*pinned_keys, *generated))
