"""Project state and the dependency graph over it (docs/tasarim.md, Özet).

`ProjectState` is an immutable snapshot of one project's nodes. The same graph is the cache's
structure and what the UI draws: edges come from the stage declarations (`core.stages`) plus the
parent edge from a test set to its test cases.

Hashes:
- identity of a node, as its dependents see it: the content hash (`plain_hash` of the content),
  or the expected `input_hash` for stages declared `identity_by_input`. Stale upstream nodes
  contribute their current (old) content, so a node is stale only when an input it can already
  see changed; otherwise it waits in `to_verify` (early cutoff, `core.invalidation`).
  A test case's identity also covers its key, so a matrix row notices an identical case that
  moved to another cluster. Other identities do not include keys, so that a set's hash is not
  tied to its cluster id (a merged cluster with old members still hits the cache).
- `expected_hash(state, ref)` = `core.hashing.input_hash` over the node kind and the identities
  of the node's dependencies, with the stage config's prompt version, model and parameters.
- `cache_key(state, ref)` = hash of the expected hash and the stage context.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr

from core import stages
from core.hashing import canonical, input_hash, plain_hash
from core.nodes import (
    CHILD_KINDS,
    KB_INDEX_KEY,
    PROJECT_CARD_KEY,
    SOURCE_KINDS,
    ClusterContent,
    KbIndexContent,
    Node,
    NodeKind,
    NodeRef,
    ProducedBy,
    ProjectCardContent,
    RequirementContent,
    StageConfig,
    Status,
    TestCaseContent,
)


class _Index:
    """Lookups derived from one state's nodes; built once per state."""

    def __init__(self, nodes: Mapping[NodeRef, Node]) -> None:
        by_kind: dict[NodeKind, list[str]] = {k: [] for k in NodeKind}
        for r in nodes:
            by_kind[r.kind].append(r.key)
        self.by_kind = {k: tuple(sorted(v)) for k, v in by_kind.items()}
        self.cluster_of: dict[str, str] = {}
        for c in self.by_kind[NodeKind.CLUSTER]:
            content = nodes[NodeRef(kind=NodeKind.CLUSTER, key=c)].content
            assert isinstance(content, ClusterContent)
            for m in content.members:
                self.cluster_of[m] = c
        self.cases_of: dict[str, list[NodeRef]] = {}
        self.covering: dict[str, list[NodeRef]] = {}
        for k in self.by_kind[NodeKind.TEST_CASE]:
            r = NodeRef(kind=NodeKind.TEST_CASE, key=k)
            self.cases_of.setdefault(case_cluster(k), []).append(r)
            content = nodes[r].content
            if isinstance(content, TestCaseContent):
                for req in content.covers:
                    self.covering.setdefault(req, []).append(r)
        self.order = tuple(sorted(nodes, key=NodeRef.sort_key))


def case_cluster(case_key: str) -> str:
    """Owning cluster of a test case key (`<cluster>:<case id>`)."""
    return case_key.split(":", 1)[0]


class ProjectState(BaseModel):
    """Treat as immutable: every change returns a new state (`model_copy(update=...)`).

    Lookups and hashes are memoised per instance; `model_copy` starts a fresh memo. Never write
    into `nodes` in place: the memo would silently go stale.
    """

    model_config = ConfigDict(frozen=True)

    project_id: str
    nodes: dict[NodeRef, Node]
    stage_configs: dict[NodeKind, StageConfig]

    _memo: dict[str, Any] = PrivateAttr(default_factory=dict)

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False):
        copied = super().model_copy(update=update, deep=deep)
        copied._memo = {}
        return copied

    def _index(self) -> _Index:
        memo = memo_of(self)
        idx = memo.get("index")
        if idx is None:
            idx = memo["index"] = _Index(self.nodes)
        return idx

    # Plain accessors (no hashing) ---------------------------------------------------------------

    def node(self, ref: NodeRef) -> Node:
        return self.nodes[ref]

    def get(self, ref: NodeRef) -> Node | None:
        return self.nodes.get(ref)

    def keys_of(self, kind: NodeKind) -> tuple[str, ...]:
        """Keys of the existing nodes of a kind, sorted."""
        return self._index().by_kind[kind]

    def ordered_refs(self) -> tuple[NodeRef, ...]:
        """Every node in topological order (kind order, then key)."""
        return self._index().order

    def requirement(self, req_id: str) -> RequirementContent:
        content = self.nodes[NodeRef(kind=NodeKind.REQUIREMENT, key=req_id)].content
        assert isinstance(content, RequirementContent)
        return content

    def members(self, cluster: str) -> tuple[str, ...]:
        content = self.nodes[NodeRef(kind=NodeKind.CLUSTER, key=cluster)].content
        assert isinstance(content, ClusterContent)
        return content.members

    def cluster_of(self, req_id: str) -> str | None:
        return self._index().cluster_of.get(req_id)

    def test_cases(self, cluster: str) -> list[NodeRef]:
        """Case nodes owned by a cluster's test set, in case key order."""
        return list(self._index().cases_of.get(cluster, ()))

    def cases_covering(self, req_id: str) -> list[NodeRef]:
        return list(self._index().covering.get(req_id, ()))


def memo_of(state: ProjectState) -> dict[str, Any]:
    """The state's memo dict, read without pydantic's slow private-attribute lookup."""
    return state.__pydantic_private__["_memo"]  # type: ignore[index]


def placeholder(ref: NodeRef) -> Node:
    return Node(ref=ref, status=Status.STALE)


def with_declared_nodes(state: ProjectState) -> ProjectState:
    """Add a stale placeholder for every derived node a stage declares and drop derived nodes no
    stage declares any more. Test cases are left to the caller (`core.invalidation`)."""
    nodes = dict(state.nodes)
    changed = False
    for spec in stages.all_specs():
        wanted = set(spec.keys(state))
        for key in wanted - set(state.keys_of(spec.kind)):
            r = NodeRef(kind=spec.kind, key=key)
            nodes[r] = placeholder(r)
            changed = True
        for key in set(state.keys_of(spec.kind)) - wanted:
            del nodes[NodeRef(kind=spec.kind, key=key)]
            changed = True
    return state.model_copy(update={"nodes": nodes}) if changed else state


def new_project(
    project_id: str,
    *,
    requirements: Sequence[RequirementContent],
    clusters: Mapping[str, Sequence[str]],
    card: str,
    index_version: str,
    stage_configs: Mapping[NodeKind, StageConfig],
) -> ProjectState:
    """Source nodes from an import, plus a stale placeholder for every derived node the stages
    declare. Every requirement must be in exactly one cluster; every derived kind needs a stage
    config."""
    ids = [r.id for r in requirements]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate requirement id")
    placed = [m for members in clusters.values() for m in members]
    if sorted(placed) != sorted(ids):
        raise ValueError("every requirement must be in exactly one cluster")
    missing = {s.kind for s in stages.all_specs()} - set(stage_configs)
    if missing:
        raise ValueError(f"missing stage config: {sorted(missing)}")

    imported = ProducedBy(mode="import")
    nodes: dict[NodeRef, Node] = {}

    def add(kind: NodeKind, key: str, content: Any) -> None:
        r = NodeRef(kind=kind, key=key)
        nodes[r] = Node(ref=r, content=content, version=1, produced_by=imported)

    for req in requirements:
        add(NodeKind.REQUIREMENT, req.id, req)
    for key, members in clusters.items():
        add(NodeKind.CLUSTER, key, ClusterContent(members=tuple(members)))
    add(NodeKind.PROJECT_CARD, PROJECT_CARD_KEY, ProjectCardContent(text=card))
    add(NodeKind.KB_INDEX, KB_INDEX_KEY, KbIndexContent(version=index_version))
    state = ProjectState(project_id=project_id, nodes=nodes, stage_configs=dict(stage_configs))
    return with_declared_nodes(state)


# Graph ------------------------------------------------------------------------------------------


def upstream(state: ProjectState, ref: NodeRef) -> tuple[NodeRef, ...]:
    """Declared dependencies of a derived node; the owning test set for a test case; nothing for
    a source node."""
    if ref.kind in SOURCE_KINDS:
        return ()
    if ref.kind in CHILD_KINDS:
        return (NodeRef(kind=NodeKind.TEST_SET, key=case_cluster(ref.key)),)
    deps = memo_of(state).setdefault("deps", {})
    found = deps.get(ref)
    if found is None:
        found = deps[ref] = tuple(stages.get(ref.kind).dependencies(state, ref.key))
    return found


def _reverse(state: ProjectState) -> dict[NodeRef, set[NodeRef]]:
    memo = memo_of(state)
    rev = memo.get("reverse")
    if rev is None:
        rev = {}
        for r in state.ordered_refs():
            for u in upstream(state, r):
                rev.setdefault(u, set()).add(r)
        memo["reverse"] = rev
    return rev


def dependents(state: ProjectState, ref: NodeRef) -> frozenset[NodeRef]:
    """Direct downstream nodes (reverse of `upstream`)."""
    return frozenset(_reverse(state).get(ref, ()))


def downstream_closure(state: ProjectState, refs: set[NodeRef]) -> set[NodeRef]:
    """`refs` and every node reachable from them through dependents."""
    rev = _reverse(state)
    seen = set(refs)
    todo = list(refs)
    while todo:
        for d in rev.get(todo.pop(), ()):
            if d not in seen:
                seen.add(d)
                todo.append(d)
    return seen


# Hashes -----------------------------------------------------------------------------------------

# Content hash by object identity. Contents are immutable and the entry holds a reference, so an
# id cannot be reused while its entry exists. Shared by every state; bounded by clearing.
_CONTENT_HASHES: dict[int, tuple[object, str]] = {}
# input_hash by (stage, config, dependency identities): the same inputs give the same hash.
_INPUT_HASHES: dict[tuple[NodeKind, str, tuple[str | None, ...]], str] = {}
_MEMO_LIMIT = 1_000_000


def content_hash(content: BaseModel) -> str:
    entry = _CONTENT_HASHES.get(id(content))
    if entry is not None and entry[0] is content:
        return entry[1]
    h = plain_hash(content.model_dump(mode="json"))
    if len(_CONTENT_HASHES) >= _MEMO_LIMIT:
        _CONTENT_HASHES.clear()
    _CONTENT_HASHES[id(content)] = (content, h)
    return h


def identity(state: ProjectState, ref: NodeRef) -> str | None:
    """How dependents see a node; None for a placeholder that was never produced."""
    node = state.nodes.get(ref)
    if node is None:
        return None
    if ref.kind not in SOURCE_KINDS and ref.kind not in CHILD_KINDS:
        if stages.get(ref.kind).identity_by_input:
            return expected_hash(state, ref)
    if node.content is None:
        return None
    h = content_hash(node.content)
    if ref.kind == NodeKind.TEST_CASE:
        return plain_hash({"key": ref.key, "content": h})
    return h


def _config_key(state: ProjectState, kind: NodeKind) -> str:
    keys = memo_of(state).setdefault("config_keys", {})
    found = keys.get(kind)
    if found is None:
        found = keys[kind] = canonical(state.stage_configs[kind].model_dump(mode="json"))
    return found


def expected_hash(state: ProjectState, ref: NodeRef) -> str:
    """`input_hash` the derived node would have if produced from the current state."""
    memo = memo_of(state).setdefault("expected", {})
    found = memo.get(ref)
    if found is not None:
        return found
    if ref.kind in SOURCE_KINDS or ref.kind in CHILD_KINDS:
        raise ValueError(f"{ref} is not produced by a stage")
    idents = tuple(identity(state, u) for u in upstream(state, ref))
    key = (ref.kind, _config_key(state, ref.kind), idents)
    h = _INPUT_HASHES.get(key)
    if h is None:
        cfg = state.stage_configs[ref.kind]
        h = input_hash(
            inputs=[ref.kind.value, *idents],  # the kind keeps two stages apart
            prompt_version=cfg.prompt_version,
            model=cfg.model,
            params=cfg.params,
        )
        if len(_INPUT_HASHES) >= _MEMO_LIMIT:
            _INPUT_HASHES.clear()
        _INPUT_HASHES[key] = h
    memo[ref] = h
    return h


def cache_key(state: ProjectState, ref: NodeRef) -> str:
    """Output cache key: the expected hash combined with the stage context."""
    context = stages.get(ref.kind).context(state, ref.key)
    return plain_hash({"input_hash": expected_hash(state, ref), "context": context})
