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
- `expected_hash(state, ref)` = `core.hashing.input_hash` over the identities of the node's
  dependencies, with the stage config's prompt version, model and parameters.
- `cache_key(state, ref)` = hash of the expected hash and the stage context.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from core.nodes import (
    ClusterContent,
    Node,
    NodeKind,
    NodeRef,
    RequirementContent,
    StageConfig,
    TestCaseContent,
)


class ProjectState(BaseModel):
    """Treat as immutable: every change returns a new state (`model_copy(update=...)`)."""

    model_config = ConfigDict(frozen=True)

    project_id: str
    nodes: dict[NodeRef, Node]
    stage_configs: dict[NodeKind, StageConfig]

    # Plain accessors (no hashing) ---------------------------------------------------------------

    def node(self, ref: NodeRef) -> Node:
        return self.nodes[ref]

    def get(self, ref: NodeRef) -> Node | None:
        return self.nodes.get(ref)

    def keys_of(self, kind: NodeKind) -> list[str]:
        """Keys of the existing nodes of a kind, sorted."""
        return sorted(r.key for r in self.nodes if r.kind == kind)

    def requirement(self, req_id: str) -> RequirementContent:
        content = self.nodes[NodeRef(kind=NodeKind.REQUIREMENT, key=req_id)].content
        assert isinstance(content, RequirementContent)
        return content

    def members(self, cluster: str) -> tuple[str, ...]:
        content = self.nodes[NodeRef(kind=NodeKind.CLUSTER, key=cluster)].content
        assert isinstance(content, ClusterContent)
        return content.members

    def cluster_of(self, req_id: str) -> str | None:
        for key in self.keys_of(NodeKind.CLUSTER):
            if req_id in self.members(key):
                return key
        return None

    def test_cases(self, cluster: str) -> list[NodeRef]:
        """Case nodes owned by a cluster's test set, in case key order."""
        prefix = f"{cluster}:"
        return [
            NodeRef(kind=NodeKind.TEST_CASE, key=k)
            for k in self.keys_of(NodeKind.TEST_CASE)
            if k.startswith(prefix)
        ]

    def cases_covering(self, req_id: str) -> list[NodeRef]:
        out = []
        for k in self.keys_of(NodeKind.TEST_CASE):
            r = NodeRef(kind=NodeKind.TEST_CASE, key=k)
            content = self.nodes[r].content
            if isinstance(content, TestCaseContent) and req_id in content.covers:
                out.append(r)
        return out


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
    raise NotImplementedError


def upstream(state: ProjectState, ref: NodeRef) -> tuple[NodeRef, ...]:
    """Declared dependencies of a derived node; the owning test set for a test case; nothing for
    a source node."""
    raise NotImplementedError


def dependents(state: ProjectState, ref: NodeRef) -> frozenset[NodeRef]:
    """Direct downstream nodes (reverse of `upstream`)."""
    raise NotImplementedError


def identity(state: ProjectState, ref: NodeRef) -> str | None:
    """How dependents see a node; None for a placeholder that was never produced."""
    raise NotImplementedError


def expected_hash(state: ProjectState, ref: NodeRef) -> str:
    """`input_hash` the derived node would have if produced from the current state."""
    raise NotImplementedError


def cache_key(state: ProjectState, ref: NodeRef) -> str:
    """Output cache key: the expected hash combined with the stage context."""
    raise NotImplementedError
