"""Output nodes of the dependency graph (docs/tasarim.md, Veri modeli).

Every piece of project state is a node addressed by `NodeRef(kind, key)` inside one project.
Source nodes (requirements, project card, knowledge base index, cluster membership) change only
through events. Derived nodes are produced by a stage and carry the `input_hash` they were
produced from; a derived node is stale when that hash differs from the one its current inputs
give. Test cases are children of a test set: produced by the set's call, edited and pinned one by
one.

Contents are plain, frozen pydantic models with a `kind` discriminator so that a store can
persist them without knowing the stage that wrote them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer

from core.schemas import Step


class NodeKind(StrEnum):
    """Declared in topological order: every kind depends only on kinds listed before it."""

    REQUIREMENT = "requirement"
    PROJECT_CARD = "project_card"
    KB_INDEX = "kb_index"
    CLUSTER = "cluster"
    EMBEDDING = "embedding"
    CLUSTERING = "clustering"
    METHOD = "method"
    CLUSTER_LABEL = "cluster_label"
    RETRIEVAL = "retrieval"
    TEST_SET = "test_set"
    TEST_CASE = "test_case"
    MATRIX_ROW = "matrix_row"


SOURCE_KINDS: frozenset[NodeKind] = frozenset(
    {NodeKind.REQUIREMENT, NodeKind.PROJECT_CARD, NodeKind.KB_INDEX, NodeKind.CLUSTER}
)
"""Changed only by events; never stale."""

CHILD_KINDS: frozenset[NodeKind] = frozenset({NodeKind.TEST_CASE})
"""Written by their parent's result (a test set); no stage of their own."""

PROJECT_CARD_KEY = "card"
KB_INDEX_KEY = "index"
CLUSTERING_KEY = "tree"


class Status(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    RUNNING = "running"
    FAILED = "failed"


class Origin(StrEnum):
    GENERATED = "generated"
    EDITED = "edited"


_ORDER = {k: i for i, k in enumerate(NodeKind)}


class NodeRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: NodeKind
    key: str = Field(min_length=1)

    def sort_key(self) -> tuple[int, str]:
        return (_ORDER[self.kind], self.key)

    # Pydantic's generated hash and eq are generic and dominate graph work; refs are compared by
    # kind and key only. Enum members are singletons, so `is` compares kinds.
    def __hash__(self) -> int:
        return hash(self.key) * 31 + str.__hash__(self.kind)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NodeRef):
            return NotImplemented
        return self.kind is other.kind and self.key == other.key

    def __str__(self) -> str:
        return f"{self.kind.value}:{self.key}"


def ref(kind: NodeKind, key: str) -> NodeRef:
    return NodeRef(kind=kind, key=key)


def case_key(cluster: str, case_id: str) -> str:
    """Node key of a test case: unique inside the project, scoped by the owning cluster."""
    return f"{cluster}:{case_id}"


# Contents ---------------------------------------------------------------------------------------

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class RequirementContent(BaseModel):
    model_config = _FROZEN
    kind: Literal["requirement"] = "requirement"
    id: str = Field(min_length=1)
    text: str
    language: str = ""
    source: str = ""


class MethodDef(BaseModel):
    """One verification method of the project and its criterion (docs/tasarim.md, Proje kartı)."""

    model_config = _FROZEN
    name: str = Field(min_length=1)
    criterion: str = ""


class ProjectCardContent(BaseModel):
    """`text`: the card body (system, glossary, rules). `methods`: the project's method list;
    the rendered card lists them after the text and the method schema's values come from it
    (paket 3; `core.prompts.render_card`)."""

    model_config = _FROZEN
    kind: Literal["project_card"] = "project_card"
    text: str
    methods: tuple[MethodDef, ...] = ()


class KbIndexContent(BaseModel):
    model_config = _FROZEN
    kind: Literal["kb_index"] = "kb_index"
    version: str = Field(min_length=1)


class ClusterContent(BaseModel):
    """Membership. `pinned_members` were placed by the user and survive re-clustering; they do
    not enter any hash."""

    model_config = _FROZEN
    kind: Literal["cluster"] = "cluster"
    members: tuple[str, ...] = Field(min_length=1)
    pinned_members: tuple[str, ...] = ()

    @field_validator("members", "pinned_members")
    @classmethod
    def _sorted_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(v)))


class EmbeddingContent(BaseModel):
    model_config = _FROZEN
    kind: Literal["embedding"] = "embedding"
    vector: tuple[float, ...]


class ClusteringContent(BaseModel):
    """The agglomerative tree (`core.clustering.ClusterTree`) in plain form."""

    model_config = _FROZEN
    kind: Literal["clustering"] = "clustering"
    ids: tuple[str, ...]
    linkage: tuple[tuple[float, ...], ...] = ()


class MethodContent(BaseModel):
    model_config = _FROZEN
    kind: Literal["method"] = "method"
    methods: tuple[str, ...] = Field(min_length=1)
    rationale: str = ""


class ClusterLabelContent(BaseModel):
    model_config = _FROZEN
    kind: Literal["cluster_label"] = "cluster_label"
    name: str = Field(min_length=1)
    rationale: str = ""


class RetrievalContent(BaseModel):
    """Passage ids in rank order. Test sets depend on these ids, not on the index version.

    `example_keys` (paket 7, D10): the project examples selected for the cluster, most similar
    first. A key carries a digest of the example text, so an edited example is a new key. Left
    out of the serialised form when empty, so content hashes and stored JSON of a project
    without examples are the same as before the field existed."""

    model_config = _FROZEN
    kind: Literal["retrieval"] = "retrieval"
    passage_ids: tuple[str, ...] = ()
    example_keys: tuple[str, ...] = ()

    @model_serializer(mode="wrap")
    def _omit_empty_examples(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if not data.get("example_keys"):
            data.pop("example_keys", None)
        return data


class TestSetContent(BaseModel):
    __test__ = False  # not a pytest class
    model_config = _FROZEN
    kind: Literal["test_set"] = "test_set"
    case_keys: tuple[str, ...] = ()


class TestCaseContent(BaseModel):
    """Same fields as the generation schema (`core.schemas.case_set_model`); labels are plain
    strings here because the label lists come from project configuration."""

    __test__ = False  # not a pytest class
    model_config = _FROZEN
    kind: Literal["test_case"] = "test_case"
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    covers: tuple[str, ...] = Field(min_length=1)
    type: str
    priority: str
    preconditions: str = ""
    test_inputs: str = ""
    assumptions: str = ""
    steps: tuple[Step, ...] = Field(min_length=1)


class MatrixRowContent(BaseModel):
    model_config = _FROZEN
    kind: Literal["matrix_row"] = "matrix_row"
    requirement_id: str
    methods: tuple[str, ...] = ()
    test_case_keys: tuple[str, ...] = ()
    covered: bool = False


NodeContent = Annotated[
    RequirementContent
    | ProjectCardContent
    | KbIndexContent
    | ClusterContent
    | EmbeddingContent
    | ClusteringContent
    | MethodContent
    | ClusterLabelContent
    | RetrievalContent
    | TestSetContent
    | TestCaseContent
    | MatrixRowContent,
    Field(discriminator="kind"),
]


# Node -------------------------------------------------------------------------------------------


class ProducedBy(BaseModel):
    """How a version was made. `mode` is one of: import, user, algorithm, full, incremental,
    merge, repair, edit. Never part of a hash."""

    model_config = _FROZEN
    mode: str
    model: str = ""
    prompt_version: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    actor: str = ""


class StageConfig(BaseModel):
    """Injected from config/ (core reads no files). Enters the `input_hash` of every node the
    stage produces; changing it stales the whole stage."""

    model_config = _FROZEN
    prompt_version: str
    model: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class Node(BaseModel):
    """`content is None` only for a derived node that has never been produced (placeholder,
    status stale). Source nodes have no `input_hash`."""

    model_config = ConfigDict(frozen=True)

    ref: NodeRef
    content: NodeContent | None = None
    input_hash: str | None = None
    cache_key: str | None = None
    status: Status = Status.FRESH
    pinned: bool = False
    origin: Origin = Origin.GENERATED
    version: int = Field(default=0, ge=0)
    produced_by: ProducedBy | None = None


class Result(BaseModel):
    """What a producer returns for one derived node. For a test set the generated cases come in
    `cases`; `settle` builds `case_keys` from the set's pinned cases followed by these, and drops
    a generated case whose key collides with a pinned one."""

    model_config = ConfigDict(frozen=True)

    input_hash: str
    cache_key: str
    content: NodeContent
    produced_by: ProducedBy
    cases: tuple[TestCaseContent, ...] = ()
