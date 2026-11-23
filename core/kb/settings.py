"""Knowledge base settings (`config/pipeline.yaml`, `kb:`). Plain data; `core/` reads no files."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KbSettings(BaseModel):
    """D9 working assumption: 300–500 token chunks, top 6–8, no reranker; D10: no examples."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_tokens: int = Field(default=400, ge=1)
    chunk_overlap_tokens: int = Field(default=40, ge=0)
    chars_per_token: int = Field(default=4, ge=1)
    """Token estimate: characters / `chars_per_token` (no tokenizer in `core/`)."""
    top_k: int = Field(default=8, ge=1)
    rrf_k: int = Field(default=60, ge=1)
    rrf_depth: int = Field(default=50, ge=1)
    """Length of each ranking (dense, keyword) that enters the fusion."""
    bm25_k1: float = 1.2
    bm25_b: float = 0.75
    reranker: str = "none"
    """`none`, or the model id of a cross-encoder (D9)."""
    rerank_candidates: int = Field(default=3, ge=1)
    """The reranker sees the first `rerank_candidates * top_k` fused candidates."""
    rerank_max_tokens: int = Field(default=512, ge=16)
    """Input cap of the cross-encoder per (query, passage) pair, in model tokens. Without it the
    model's own limit (8192 for bge-reranker-v2-m3) applies and CPU scoring is ~3x slower."""
    examples: int = Field(default=0, ge=0)
    """D10: examples from the example pool that enter the prompt (0 = off)."""
    card_tokens: int = Field(default=1500, ge=1)
    """Upper bound of the project card text (docs/tasarim.md, Proje kartı)."""
    card_draft_input_tokens: int = Field(default=12000, ge=1)
    card_draft_max_tokens: int = Field(default=4096, ge=1)

    def retrieval_params(self) -> dict[str, object]:
        """What decides the retrieval stage's output (enters its `StageConfig.params`): chunking,
        search, fusion, reranker and example count. The card draft settings do not."""
        return self.model_dump(
            mode="json", exclude={"card_tokens", "card_draft_input_tokens", "card_draft_max_tokens"}
        )

    @property
    def chunk_chars(self) -> int:
        return self.chunk_tokens * self.chars_per_token

    @property
    def overlap_chars(self) -> int:
        return self.chunk_overlap_tokens * self.chars_per_token
