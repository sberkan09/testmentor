"""Cross-encoder reranker (D9 arm; paket 7). Off by default (`kb.reranker: none`).

The model sits behind `Scorer`, so tests run with a fake and nothing is downloaded. The real one
(`load_cross_encoder`) imports `sentence-transformers` only when a model id is configured; it is
in the optional `d6` dependency group and runs on CPU. The model id is a setting; this module
names none.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence

Scorer = Callable[[list[tuple[str, str]]], Sequence[float]]
"""(query, passage) pairs to relevance scores, same order."""


class CrossEncoderReranker:
    def __init__(self, scorer: Scorer) -> None:
        self._scorer = scorer

    async def rerank(self, query: str, candidates: Sequence[tuple[str, str]], k: int) -> list[str]:
        if not candidates:
            return []
        scores = await asyncio.to_thread(self._scorer, [(query, text) for _, text in candidates])
        if len(scores) != len(candidates):
            raise ValueError("scorer returned a different number of scores than candidates")
        order = sorted(range(len(candidates)), key=lambda i: (-float(scores[i]), i))  # stable
        return [candidates[i][0] for i in order[:k]]


def load_cross_encoder(model_id: str) -> Scorer:
    """The configured cross-encoder as a `Scorer` (downloads the model on first use)."""
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "kb.reranker needs sentence-transformers: `uv run --group d6 ...` (optional group)"
        ) from exc
    model = CrossEncoder(model_id)  # pragma: no cover

    def score(pairs: list[tuple[str, str]]) -> Sequence[float]:  # pragma: no cover
        return [float(x) for x in model.predict(pairs)]

    return score  # pragma: no cover


def make_reranker(name: str) -> CrossEncoderReranker | None:
    """None for `none` (no reranker)."""
    if name.strip().lower() in ("", "none"):
        return None
    return CrossEncoderReranker(load_cross_encoder(name))
