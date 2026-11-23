"""Project example pool (docs/tasarim.md, Örnek havuzu; paket 7, D10).

The pool holds the test cases the user wrote, edited or pinned, each with the requirement text it
covers and the vector of that text. Selection for a cluster: the entries closest to the mean
member vector. A key is `<test case key>@<digest of the rendered text>`, so an example the user
edits is a new key and a test set that used the old one goes stale; the pool changing without the
selection changing does not (the retrieval node has the same content: early cutoff).
Per-project, like the index.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

import numpy as np

from core.nodes import TestCaseContent
from core.prompts import render_example
from core.stages.base import Embed


@dataclass(frozen=True)
class ExampleEntry:
    key: str
    """Test case node key."""
    requirement_text: str
    """What the vector was computed from (the covered requirements' texts)."""
    text: str
    """Prompt text (`core.prompts.render_example`)."""
    vector: tuple[float, ...]
    excluded_with: frozenset[str] = frozenset()
    """Requirement ids whose clusters never get this example: the requirements the test case
    covers (they are in that cluster's prompt as fixed tests already). The eval (D10) adds the
    requirements that share a reference source, so the answer key cannot leak."""

    @property
    def example_key(self) -> str:
        return f"{self.key}@{hashlib.sha256(self.text.encode('utf-8')).hexdigest()[:8]}"


@dataclass
class _Pool:
    entries: dict[str, ExampleEntry] = field(default_factory=dict)  # by test case key
    changes: int = 0


def _unit(vector: Sequence[float]) -> np.ndarray:
    v = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(v))
    return v / norm if norm else v


class ExamplePool:
    def __init__(self) -> None:
        self._projects: dict[str, _Pool] = {}

    def _pool(self, project_id: str) -> _Pool:
        return self._projects.setdefault(project_id, _Pool())

    def add(self, project_id: str, entries: Sequence[ExampleEntry]) -> None:
        """Adds or replaces entries by test case key."""
        pool = self._pool(project_id)
        for e in entries:
            pool.entries[e.key] = e
        pool.changes += 1

    def remove(self, project_id: str, key: str) -> None:
        pool = self._pool(project_id)
        pool.entries.pop(key, None)
        pool.changes += 1

    def entries(self, project_id: str) -> dict[str, ExampleEntry]:
        """Copy of the project's entries by test case key."""
        p = self._projects.get(project_id)
        return dict(p.entries) if p else {}

    def version(self, project_id: str) -> str:
        p = self._projects.get(project_id)
        return f"e{p.changes if p else 0}"

    def select(
        self,
        project_id: str,
        query_vector: Sequence[float],
        n: int,
        exclude: Collection[str] = (),
    ) -> list[str]:
        """Up to `n` example keys, most similar first (ties by test case key). Entries whose
        `excluded_with` meets `exclude` (the cluster's member ids) are skipped."""
        p = self._projects.get(project_id)
        if p is None or n <= 0 or not p.entries:
            return []
        q = _unit(query_vector)
        skip = frozenset(exclude)
        scored = [
            (-float(_unit(e.vector) @ q), e.key)
            for e in p.entries.values()
            if not (e.excluded_with & skip)
        ]
        scored.sort()
        return [p.entries[key].example_key for _, key in scored[:n]]

    def texts(self, project_id: str, example_keys: Sequence[str]) -> list[str]:
        p = self._projects.get(project_id)
        by_key = {e.example_key: e.text for e in p.entries.values()} if p else {}
        out = []
        for k in example_keys:
            if k not in by_key:
                raise KeyError(f"example {k!r} is not in project {project_id!r}")
            out.append(by_key[k])
        return out


async def build_entry(
    key: str,
    case: TestCaseContent,
    requirement_texts: Sequence[str],
    embed: Embed,
    *,
    excluded_with: Collection[str] = (),
) -> ExampleEntry:
    """Entry for one test case: the rendered text and the vector of the covered requirements'
    texts joined. It is never selected for a cluster holding a requirement it covers (or one in
    `excluded_with`)."""
    joined = "\n".join(requirement_texts)
    (vector,) = await embed([joined])
    return ExampleEntry(
        key=key,
        requirement_text=joined,
        text=render_example(requirement_texts, case),
        vector=tuple(vector),
        excluded_with=frozenset(case.covers) | frozenset(excluded_with),
    )
