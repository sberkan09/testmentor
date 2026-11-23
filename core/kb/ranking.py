"""Keyword ranking (BM25) and rank fusion (RRF) for the knowledge base search (paket 7).

Pure Python, no dependency. `tokenize` folds case and Turkish letters so that Turkish and English
text, with and without diacritics, meet in the same token space.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

_WORD = re.compile(r"\w+", re.UNICODE)
_TURKISH = str.maketrans({"İ": "i", "I": "i", "ı": "i"})


def tokenize(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.translate(_TURKISH)).lower()
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return _WORD.findall(folded)


class Bm25Index:
    """Okapi BM25 over documents added one by one; scores are computed at query time."""

    def __init__(self, k1: float = 1.2, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self._postings: dict[str, dict[str, int]] = {}
        self._length: dict[str, int] = {}
        self._terms: dict[str, list[str]] = {}
        self._total = 0

    def __len__(self) -> int:
        return len(self._length)

    def add(self, doc_id: str, text: str) -> None:
        if doc_id in self._length:
            self.remove(doc_id)
        tokens = tokenize(text)
        self._length[doc_id] = len(tokens)
        self._total += len(tokens)
        counts = Counter(tokens)
        self._terms[doc_id] = list(counts)
        for term, tf in counts.items():
            self._postings.setdefault(term, {})[doc_id] = tf

    def remove(self, doc_id: str) -> None:
        if doc_id not in self._length:
            return
        self._total -= self._length.pop(doc_id)
        for term in self._terms.pop(doc_id):
            del self._postings[term][doc_id]
            if not self._postings[term]:
                del self._postings[term]

    def search(self, query: str, n: int) -> list[tuple[str, float]]:
        """Up to `n` (id, score) pairs with a positive score, best first; ties by id."""
        if not self._length:
            return []
        n_docs = len(self._length)
        avg = (self._total / n_docs) or 1.0
        scores: dict[str, float] = {}
        for term in dict.fromkeys(tokenize(query)):
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = math.log(1.0 + (n_docs - len(postings) + 0.5) / (len(postings) + 0.5))
            for doc_id, tf in postings.items():
                norm = tf + self.k1 * (1.0 - self.b + self.b * self._length[doc_id] / avg)
                scores[doc_id] = scores.get(doc_id, 0.0) + idf * tf * (self.k1 + 1.0) / norm
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:n]


def rrf(rankings: Sequence[Sequence[str]], k: int) -> list[str]:
    """Reciprocal rank fusion: score(id) = sum over rankings of 1 / (k + rank), rank from 1.
    Ties keep the order of first appearance (earlier ranking first), so the result is
    deterministic."""
    scores: dict[str, float] = {}
    first: dict[str, int] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            first.setdefault(item, len(first))
    return sorted(scores, key=lambda i: (-scores[i], first[i]))
