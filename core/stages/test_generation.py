"""Pure helpers of the test set producer (docs/tasarim.md, Test durumu üretimi; paket 3).

No model call and no I/O here: the producer in `core.stages.test_set` builds prompts with
`core.prompts`, calls the model through `core.llm.Complete` and uses these functions to choose the
mode, compare with the recorded basis, validate covers and assemble the complete set that
`settle` writes.

Terms:
- *basis*: what a set was produced from, recorded in `produced_by.params["basis"]`. Incremental
  production is valid only when the card, the stage config and the passage ids are the same as
  in the basis; members may differ.
- *need*: members whose methods include `StageSettings.test_method`. Only they may appear in
  `covers`, and each must be covered.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

from core.nodes import Node, NodeRef, TestCaseContent

if TYPE_CHECKING:
    from core.graph import ProjectState
    from core.invalidation import Hint

Mode = Literal["full", "incremental", "merge"]

BASIS_PARAM = "basis"
"""Key of the basis in `ProducedBy.params`."""

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class MemberBasis(BaseModel):
    model_config = _FROZEN

    text_hash: str
    methods: tuple[str, ...]
    """Sorted; empty when the requirement has no method output yet."""


class Basis(BaseModel):
    model_config = _FROZEN

    config: str
    """`plain_hash` of the TEST_SET `StageConfig` (prompt version, model, params)."""
    card: str
    """Content hash of the project card node."""
    passages: tuple[str, ...]
    """Passage ids of the cluster's retrieval, in rank order."""
    members: dict[str, MemberBasis]


class Delta(BaseModel):
    """Members compared with the basis; every tuple sorted by id."""

    model_config = _FROZEN

    added: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    """Text or methods differ from the basis."""
    removed: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not (self.added or self.changed or self.removed)

    @property
    def only_removed(self) -> bool:
        return bool(self.removed) and not (self.added or self.changed)


def basis_of(state: ProjectState, cluster: str) -> Basis:
    """The basis the cluster's set would have if produced from `state` now: config hash, card
    content hash, retrieval passage ids (empty if the retrieval has no content), and per member
    the requirement content hash and the sorted methods of its METHOD node."""
    raise NotImplementedError("paket 3 adım 4")


def read_basis(node: Node) -> Basis | None:
    """The basis recorded in `node.produced_by.params`; None when absent or unreadable (for
    example an edited or carried version)."""
    raise NotImplementedError("paket 3 adım 4")


def choose_mode(
    state: ProjectState,
    cluster: str,
    hint: Hint | None,
    sources: Mapping[NodeRef, Sequence[TestCaseContent]],
    *,
    max_unit_size: int | None = None,
) -> Mode:
    """- `merge` when the hint is merge and every hint source is in `sources`;
    - otherwise `incremental` when the set has content, a readable basis, the basis' config,
      card and passages equal `basis_of(state, cluster)` (members may differ), and the cluster
      has at most `max_unit_size` members (None: no limit);
    - `full` in every other case (no content, no basis, card / config / passages changed, a
      cluster larger than one unit). A merge hint without its sources falls through to these
      rules. The hint's `incremental` alone never decides: paket 2 gives it to every stale set
      with content, whatever the cause."""
    raise NotImplementedError("paket 3 adım 4")


def delta(old: Basis, new: Basis) -> Delta:
    """Added, changed (text hash or methods differ) and removed members."""
    raise NotImplementedError("paket 3 adım 4")


def need(state: ProjectState, cluster: str, test_method: str) -> tuple[str, ...]:
    """Members (id order) whose METHOD content includes `test_method`."""
    raise NotImplementedError("paket 3 adım 4")


@dataclass(frozen=True)
class Filtered:
    cases: tuple[TestCaseContent, ...]
    dropped_ids: int
    """Covers entries removed: not a member of the request or not in `allowed`."""
    dropped_cases: int
    """Cases whose covers became empty."""


def filter_covers(cases: Iterable[Mapping[str, Any]], allowed: Iterable[str]) -> Filtered:
    """Validate model output cases (plain JSON, `core.schemas.plain`) into `TestCaseContent`:
    keep in `covers` only ids in `allowed`, first occurrence order, without duplicates; drop the
    case when nothing is left. Ids are kept as the model wrote them (callers renumber)."""
    raise NotImplementedError("paket 3 adım 4")


def split_units(members: Sequence[str], max_size: int) -> list[tuple[str, ...]]:
    """Members in id order cut into ceil(n / max_size) consecutive parts whose sizes differ by
    at most one (larger parts first): 60 / 25 → 20, 20, 20; 26 / 25 → 13, 13; n ≤ max → one."""
    raise NotImplementedError("paket 3 adım 4")


def next_ids(taken: Iterable[str], n: int) -> list[str]:
    """`n` ids of the form `TC-<k>`, k = 1, 2, ... skipping ids in `taken`."""
    raise NotImplementedError("paket 3 adım 4")


def renumber(cases: Sequence[TestCaseContent], taken: Iterable[str]) -> list[TestCaseContent]:
    """Full mode: give the cases `next_ids(taken, len(cases))` in order (pinned ids are
    `taken`). Parts of a split cluster are concatenated in part order before this."""
    raise NotImplementedError("paket 3 adım 4")


def prune_removed(
    existing: Sequence[TestCaseContent], removed: Iterable[str]
) -> tuple[list[TestCaseContent], list[str]]:
    """Unpinned existing cases after members left: a case covering only removed requirements is
    dropped; a mixed case keeps its id with the removed ids taken out of `covers`. Returns the
    kept cases in order and the ids of the trimmed (mixed) cases, which go to the incremental
    tail in full text."""
    raise NotImplementedError("paket 3 adım 4")


def apply_incremental(
    existing: Sequence[TestCaseContent],
    add: Sequence[TestCaseContent],
    update: Sequence[TestCaseContent],
    pinned_ids: Iterable[str],
) -> tuple[list[TestCaseContent], int]:
    """The complete unpinned set after an incremental reply. Existing cases (in set order) keep
    their order, id and content unless updated; an update replaces the case with that id in
    place; an update whose id is pinned is ignored and counted; an update whose id is unknown is
    treated as an add. Adds never keep the model's id: they get `next_ids` after every existing
    and pinned id, in reply order (adds first, then unknown-id updates), and go to the end.
    Returns the cases and the number of ignored pinned updates."""
    raise NotImplementedError("paket 3 adım 4")


def merge_sources(
    sources: Mapping[NodeRef, Sequence[TestCaseContent]], pinned_ids: Iterable[str] = ()
) -> dict[str, list[TestCaseContent]]:
    """Source set cases keyed by source cluster (key order), with colliding ids renamed
    `<cluster>.<id>` (the first cluster in key order keeps its id). `sources` holds the unpinned
    cases only: pinned ones were carried into the new set by core and go to the pinned section;
    an id equal to a pinned id of the new set is also renamed."""
    raise NotImplementedError("paket 3 adım 4")


def apply_merge(
    merged: Mapping[str, Sequence[TestCaseContent]], drop: Iterable[str]
) -> list[TestCaseContent]:
    """Merged cases in cluster then case order without the dropped ids; unknown ids ignored."""
    raise NotImplementedError("paket 3 adım 4")


def uncovered(cases: Iterable[TestCaseContent], need_ids: Iterable[str]) -> list[str]:
    """Sorted `need_ids` that appear in no case's `covers`."""
    raise NotImplementedError("paket 3 adım 4")
