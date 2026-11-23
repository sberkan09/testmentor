"""Corpus loading and chunk vectors for `passages: index` (paket 7, D9).

The documents are the writer-visible texts of the project's corpus cache
(`python -m eval.corpus fetch --project <key>`, `eval/corpus/cache/<key>/`, not in git): `corpus`
documents and the stripped view of `mixed` ones. `reference` documents are the answer key of
golden set v1 and never enter the index; a cache that lists one is refused. A missing cache is an
error, never a silent fall back to "no passages" (that would measure the wrong arm).

Chunk vectors are cached apart from the requirement vectors (`eval/cache/embeddings.json` is
tracked in git and rewritten whole per call): one `.npz` per project, named by a hash of the
embedding model version and the chunks' passage ids, under the git-ignored `eval/cache/kb/`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

import numpy as np

from core.kb.chunking import Chunk
from eval.corpus.manifest import CORPUS_DIR

ROOT = CORPUS_DIR.parent.parent
VECTOR_CACHE = ROOT / "eval" / "cache" / "kb"
EmbedFn = Callable[[Sequence[str]], Awaitable[list[list[float]]]]
EMBED_BATCH = 128


class CorpusMissing(RuntimeError):
    pass


def _flatten_json(text: str) -> str:
    """OSCAL catalogs and the like: the string values, one paragraph each, in document order."""
    out: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            out.append(node.strip())
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(text))
    return "\n\n".join(s for s in out if s)


def _document_text(text: str) -> str:
    if text.lstrip().startswith(("{", "[")):
        try:
            return _flatten_json(text)
        except json.JSONDecodeError:
            return text
    return text


def load_corpus(project_key: str, root: Path | None = None) -> list[tuple[str, str]]:
    """(document id, text) of the writer-visible documents, in id order. A zip member document is
    `<doc>/<member stem>`."""
    base = (root or CORPUS_DIR) / "cache" / project_key.lower()
    index_path, visible_path = base / "index.json", base / "writer_visible.txt"
    if not index_path.exists() or not visible_path.exists():
        raise CorpusMissing(
            f"no corpus cache for {project_key} at {base}: "
            f"run `python -m eval.corpus fetch --project {project_key.lower()}` first"
        )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    visible = {ln.strip() for ln in visible_path.read_text(encoding="utf-8").splitlines() if ln}
    docs: dict[str, str] = {}
    for doc_id, entry in index.items():
        for t in entry["texts"]:
            file = t["file"] if entry["role"] == "corpus" else t.get("writer_file")
            if file is None:
                continue  # reference documents, and mixed ones without a stripped view
            if file not in visible:
                continue
            if entry["role"] == "reference":
                raise CorpusMissing(f"{doc_id}: a reference document is listed as writer-visible")
            name = doc_id if not t.get("member") else f"{doc_id}/{Path(file).stem}"
            docs[name] = _document_text((base / file).read_text(encoding="utf-8"))
    for file in visible:  # a reference file in the visible list is refused even if unindexed
        for doc_id, entry in index.items():
            if entry["role"] == "reference" and any(t["file"] == file for t in entry["texts"]):
                raise CorpusMissing(f"{doc_id}: a reference document is listed as writer-visible")
    if not docs:
        raise CorpusMissing(f"{project_key}: the corpus cache has no writer-visible document")
    return sorted(docs.items())


class ChunkVectorCache:
    def __init__(self, directory: Path | None, model_version: str, embed: EmbedFn | None) -> None:
        self.directory = directory or VECTOR_CACHE
        self.model_version, self.embed = model_version, embed

    def _path(self, project: str, chunks: Sequence[Chunk]) -> Path:
        h = hashlib.sha256(self.model_version.encode("utf-8"))
        for c in chunks:
            h.update(b"\n" + c.passage_id.encode("utf-8"))
        return self.directory / f"{project.lower()}-{h.hexdigest()[:20]}.npz"

    async def get(self, project: str, chunks: Sequence[Chunk]) -> list[list[float]]:
        path = self._path(project, chunks)
        if path.exists():
            data = np.load(path)
            if data["vectors"].shape[0] == len(chunks):
                return data["vectors"].tolist()
        if self.embed is None:
            raise RuntimeError(
                f"{len(chunks)} chunk vectors missing and no embedding service (EMBEDDING_BASE_URL)"
            )
        vectors: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH):
            vectors += await self.embed([c.text for c in chunks[i : i + EMBED_BATCH]])
        self.directory.mkdir(parents=True, exist_ok=True)
        np.savez(path, vectors=np.asarray(vectors, dtype=np.float32))
        return vectors
