"""Wiring of the knowledge base into the stages (paket 7): `Retrieve`, `PassageSource` and the
example hooks of `core.stages.base.ProduceContext`.

The query of a cluster is the member texts only: their vectors are averaged for the dense search
and the texts joined for the keyword search. The cluster name is not part of it (docs/tasarim.md,
İndeks).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np

from core.kb.settings import KbSettings
from core.nodes import RequirementContent
from core.stages.base import Embed, ExampleSource, PassageSource, Retrieve, SelectExamples
from services.kb_examples import ExamplePool
from services.kb_index import KbIndex


class Reranker(Protocol):
    async def rerank(self, query: str, candidates: Sequence[tuple[str, str]], k: int) -> list[str]:
        """`candidates` are (passage id, prompt text); returns the best `k` ids, best first."""


async def query_vector(texts: Sequence[str], embed: Embed) -> list[float]:
    """Mean of the member vectors (each unit length), the dense query of a cluster."""
    vectors = await embed(list(texts))
    mean = np.mean(
        [np.asarray(v, dtype=np.float32) / (np.linalg.norm(v) or 1.0) for v in vectors], axis=0
    )
    return [float(x) for x in mean]


def make_retrieve(
    index: KbIndex,
    project_id: str,
    embed: Embed,
    k: int,
    *,
    reranker: Reranker | None = None,
    candidates: int = 3,
    query_chars: int = 1600,
) -> Retrieve:
    async def retrieve(members: Sequence[RequirementContent]) -> list[str]:
        if not members:
            return []
        texts = [m.text for m in members]
        vector = await query_vector(texts, embed)
        if reranker is None:
            return index.search(project_id, texts, k, vector)
        found = index.search(project_id, texts, k * candidates, vector)
        if not found:
            return []
        pairs = list(zip(found, index.texts(project_id, found), strict=True))
        query = " ".join(texts)[:query_chars]
        return await reranker.rerank(query, pairs, k)

    return retrieve


def make_passages(index: KbIndex, project_id: str) -> PassageSource:
    def passages(ids: Sequence[str]) -> list[str]:
        return index.texts(project_id, ids)

    return passages


def build_retrieval(
    index: KbIndex,
    project_id: str,
    embed: Embed,
    settings: KbSettings,
    reranker: Reranker | None = None,
) -> tuple[Retrieve, PassageSource]:
    """`make_retrieve` and `make_passages` with the settings of the `kb:` section."""
    retrieve = make_retrieve(
        index,
        project_id,
        embed,
        settings.top_k,
        reranker=reranker,
        candidates=settings.rerank_candidates,
        query_chars=settings.chunk_chars,
    )
    return retrieve, make_passages(index, project_id)


def make_select_examples(
    pool: ExamplePool, project_id: str, embed: Embed, n: int
) -> SelectExamples | None:
    """None when `n` is 0 (examples off): the retrieval then writes no example keys."""
    if n <= 0:
        return None

    async def select(members: Sequence[RequirementContent]) -> list[str]:
        if not members:
            return []
        vector = await query_vector([m.text for m in members], embed)
        return pool.select(project_id, vector, n, exclude=[m.id for m in members])

    return select


def make_example_source(pool: ExamplePool, project_id: str) -> ExampleSource:
    def texts(keys: Sequence[str]) -> list[str]:
        return pool.texts(project_id, keys)

    return texts


def index_version(index: KbIndex, pool: ExamplePool, project_id: str) -> str:
    """Version of the project's knowledge base: it changes when a document or an example
    changes. Goes into `KbDocumentAdded.index_version`; retrieval searches again, and a test set
    goes stale only when its passage ids or example keys come out different."""
    return f"{index.version(project_id)}.{pool.version(project_id)}"
