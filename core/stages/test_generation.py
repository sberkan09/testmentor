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

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from core.hashing import plain_hash
from core.nodes import (
    PROJECT_CARD_KEY,
    MethodContent,
    Node,
    NodeKind,
    NodeRef,
    RetrievalContent,
    TestCaseContent,
    TestSetContent,
)

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
    from core.graph import content_hash  # core.graph imports core.stages at module level

    card = state.node(NodeRef(kind=NodeKind.PROJECT_CARD, key=PROJECT_CARD_KEY)).content
    retrieval = state.node(NodeRef(kind=NodeKind.RETRIEVAL, key=cluster)).content
    members = {}
    for m in state.members(cluster):
        req = state.node(NodeRef(kind=NodeKind.REQUIREMENT, key=m)).content
        assert req is not None
        members[m] = MemberBasis(text_hash=content_hash(req), methods=methods_of(state, m))
    return Basis(
        config=plain_hash(state.stage_configs[NodeKind.TEST_SET].model_dump(mode="json")),
        card=content_hash(card) if card is not None else "",
        passages=retrieval.passage_ids if isinstance(retrieval, RetrievalContent) else (),
        members=members,
    )


def methods_of(state: ProjectState, requirement: str) -> tuple[str, ...]:
    """Sorted methods of the requirement's METHOD node; empty without content."""
    node = state.get(NodeRef(kind=NodeKind.METHOD, key=requirement))
    content = node.content if node is not None else None
    return tuple(sorted(content.methods)) if isinstance(content, MethodContent) else ()


def read_basis(node: Node) -> Basis | None:
    """The basis recorded in `node.produced_by.params`; None when absent or unreadable (for
    example an edited or carried version)."""
    if node.produced_by is None:
        return None
    raw = node.produced_by.params.get(BASIS_PARAM)
    if raw is None:
        return None
    try:
        return Basis.model_validate(raw)
    except ValidationError:
        return None


def choose_mode(
    state: ProjectState,
    cluster: str,
    hint: Hint | None,
    sources: Mapping[NodeRef, Sequence[TestCaseContent]],
    *,
    max_unit_size: int | None = None,
    allow_incremental: bool = True,
) -> Mode:
    """- `merge` when the hint is merge and every hint source is in `sources`;
    - otherwise `incremental` when the set has content, a readable basis, the basis' config,
      card and passages equal `basis_of(state, cluster)` (members may differ), and the cluster
      has at most `max_unit_size` members (None: no limit);
    - `full` in every other case (no content, no basis, card / config / passages changed, a
      cluster larger than one unit). A merge hint without its sources falls through to these
      rules. The hint's `incremental` alone never decides: paket 2 gives it to every stale set
      with content, whatever the cause. `allow_incremental=False` (D8, `regeneration: full`)
      turns every incremental case into `full`."""
    if (
        hint is not None
        and hint.mode == "merge"
        and hint.sources
        and all(s in sources for s in hint.sources)
    ):
        return "merge"
    node = state.node(NodeRef(kind=NodeKind.TEST_SET, key=cluster))
    if not allow_incremental or not isinstance(node.content, TestSetContent):
        return "full"
    old = read_basis(node)
    if old is None:
        return "full"
    if max_unit_size is not None and len(state.members(cluster)) > max_unit_size:
        return "full"
    new = basis_of(state, cluster)
    if (old.config, old.card, old.passages) != (new.config, new.card, new.passages):
        return "full"
    return "incremental"


def delta(old: Basis, new: Basis) -> Delta:
    """Added, changed (text hash or methods differ) and removed members."""
    added = sorted(set(new.members) - set(old.members))
    removed = sorted(set(old.members) - set(new.members))
    changed = sorted(
        m for m in set(old.members) & set(new.members) if old.members[m] != new.members[m]
    )
    return Delta(added=tuple(added), changed=tuple(changed), removed=tuple(removed))


def need(state: ProjectState, cluster: str, test_method: str) -> tuple[str, ...]:
    """Members (id order) whose METHOD content includes `test_method`."""
    return tuple(m for m in state.members(cluster) if test_method in methods_of(state, m))


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
    allowed = set(allowed)
    out: list[TestCaseContent] = []
    dropped_ids = dropped_cases = 0
    for case in cases:
        kept: list[str] = []
        for rid in case["covers"]:
            if rid not in allowed:
                dropped_ids += 1
            elif rid not in kept:
                kept.append(rid)
        if not kept:
            dropped_cases += 1
            continue
        out.append(TestCaseContent.model_validate({**case, "covers": tuple(kept)}))
    return Filtered(cases=tuple(out), dropped_ids=dropped_ids, dropped_cases=dropped_cases)


def split_units(members: Sequence[str], max_size: int) -> list[tuple[str, ...]]:
    """Members in id order cut into ceil(n / max_size) consecutive parts whose sizes differ by
    at most one (larger parts first): 60 / 25 → 20, 20, 20; 26 / 25 → 13, 13; n ≤ max → one."""
    ordered = sorted(members)
    if not ordered:
        return []
    parts = math.ceil(len(ordered) / max_size)
    base, extra = divmod(len(ordered), parts)
    out: list[tuple[str, ...]] = []
    start = 0
    for i in range(parts):
        size = base + (1 if i < extra else 0)
        out.append(tuple(ordered[start : start + size]))
        start += size
    return out


def next_ids(taken: Iterable[str], n: int) -> list[str]:
    """`n` ids of the form `TC-<k>`, k = 1, 2, ... skipping ids in `taken`."""
    taken = set(taken)
    out: list[str] = []
    k = 0
    while len(out) < n:
        k += 1
        cid = f"TC-{k}"
        if cid not in taken:
            out.append(cid)
    return out


def renumber(cases: Sequence[TestCaseContent], taken: Iterable[str]) -> list[TestCaseContent]:
    """Full mode: give the cases `next_ids(taken, len(cases))` in order (pinned ids are
    `taken`). Parts of a split cluster are concatenated in part order before this."""
    ids = next_ids(taken, len(cases))
    return [c.model_copy(update={"id": i}) for c, i in zip(cases, ids, strict=True)]


def prune_removed(
    existing: Sequence[TestCaseContent], removed: Iterable[str]
) -> tuple[list[TestCaseContent], list[str]]:
    """Unpinned existing cases after members left: a case covering only removed requirements is
    dropped; a mixed case keeps its id with the removed ids taken out of `covers`. Returns the
    kept cases in order and the ids of the trimmed (mixed) cases, which go to the incremental
    tail in full text."""
    removed = set(removed)
    kept: list[TestCaseContent] = []
    trimmed: list[str] = []
    for case in existing:
        covers = tuple(r for r in case.covers if r not in removed)
        if not covers:
            continue
        if covers != case.covers:
            case = case.model_copy(update={"covers": covers})
            trimmed.append(case.id)
        kept.append(case)
    return kept, trimmed


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
    pinned = set(pinned_ids)
    out = list(existing)
    index = {c.id: i for i, c in enumerate(out)}
    ignored = 0
    unknown: list[TestCaseContent] = []
    for case in update:
        if case.id in pinned:
            ignored += 1
        elif case.id in index:
            out[index[case.id]] = case
        else:
            unknown.append(case)
    new = [*add, *unknown]
    ids = next_ids(set(index) | pinned, len(new))
    out += [c.model_copy(update={"id": i}) for c, i in zip(new, ids, strict=True)]
    return out, ignored


def merge_sources(
    sources: Mapping[NodeRef, Sequence[TestCaseContent]], pinned_ids: Iterable[str] = ()
) -> dict[str, list[TestCaseContent]]:
    """Source set cases keyed by source cluster (key order), with colliding ids renamed
    `<cluster>.<id>` (the first cluster in key order keeps its id). `sources` holds the unpinned
    cases only: pinned ones were carried into the new set by core and go to the pinned section;
    an id equal to a pinned id of the new set is also renamed."""
    seen = set(pinned_ids)
    out: dict[str, list[TestCaseContent]] = {}
    for src in sorted(sources, key=lambda r: r.key):
        cluster = src.key
        cases: list[TestCaseContent] = []
        for case in sources[src]:
            cid = case.id if case.id not in seen else f"{cluster}.{case.id}"
            seen.add(cid)
            cases.append(case if cid == case.id else case.model_copy(update={"id": cid}))
        out[cluster] = cases
    return out


def apply_merge(
    merged: Mapping[str, Sequence[TestCaseContent]], drop: Iterable[str]
) -> list[TestCaseContent]:
    """Merged cases in cluster then case order without the dropped ids; unknown ids ignored."""
    dropped = set(drop)
    return [c for cases in merged.values() for c in cases if c.id not in dropped]


def uncovered(cases: Iterable[TestCaseContent], need_ids: Iterable[str]) -> list[str]:
    """Sorted `need_ids` that appear in no case's `covers`."""
    seen = {r for c in cases for r in c.covers}
    return sorted(set(need_ids) - seen)
