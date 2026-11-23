"""Project card draft from the knowledge base documents (docs/tasarim.md, Proje kartı; paket 7).

One model call: the documents' leading excerpts in, the card text (at most `kb.card_tokens`) and
the verification method list out. The result is a draft the user edits and approves; it is not a
graph node, so it has no `input_hash`. The prompt template has its own version
(`core.prompts.CARD_DRAFT_VERSION`) and uses the shared system instruction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.kb.chunking import Chunk
from core.kb.settings import KbSettings
from core.llm import Complete, LLMParams
from core.nodes import MethodDef, NodeKind, ProjectCardContent
from core.prompts import CARD_DRAFT_VERSION, card_draft_messages
from core.schemas import card_draft_model
from core.stages.calls import CallFailed, CallLog, call

__all__ = ["CallFailed", "CardDraft", "draft_card", "excerpts"]


@dataclass(frozen=True)
class CardDraft:
    text: str
    methods: tuple[MethodDef, ...]
    template_version: str = CARD_DRAFT_VERSION

    def content(self) -> ProjectCardContent:
        return ProjectCardContent(text=self.text, methods=self.methods)


def excerpts(
    chunks_by_document: Mapping[str, Sequence[Chunk]], budget_tokens: int, chars_per_token: int = 4
) -> list[tuple[str, str]]:
    """(document id, excerpt) pairs within the token budget: one chunk at a time from each
    document in turn (document id order), so every document is represented and the start of each
    document, where scope and glossary usually are, comes first."""
    budget = budget_tokens * chars_per_token
    taken: dict[str, list[str]] = {d: [] for d in sorted(chunks_by_document)}
    position = {d: 0 for d in taken}
    used = 0
    progressed = True
    while progressed and used < budget:
        progressed = False
        for doc in taken:
            chunks = chunks_by_document[doc]
            if position[doc] >= len(chunks):
                continue
            chunk = chunks[position[doc]]
            if used + len(chunk.text) > budget and used > 0:
                continue
            position[doc] += 1
            taken[doc].append(chunk.text)
            used += len(chunk.text)
            progressed = True
    return [(d, "\n\n".join(parts)) for d, parts in taken.items() if parts]


async def draft_card(
    complete: Complete,
    documents: Sequence[tuple[str, str]],
    default_methods: Sequence[MethodDef],
    settings: KbSettings,
) -> CardDraft:
    """Raises `CallFailed` when the reply does not match the schema after the one retry (for
    example a text over `kb.card_tokens`)."""
    schema = card_draft_model(settings.card_tokens * settings.chars_per_token)
    messages = card_draft_messages(
        documents,
        [(m.name, m.criterion) for m in default_methods],
        max_tokens=settings.card_tokens,
        schema=schema.model_json_schema(),
    )
    out = await call(
        complete,
        CallLog(),
        stage=NodeKind.PROJECT_CARD,
        unit="card/draft",
        messages=messages,
        schema=schema,
        params=LLMParams(
            temperature=0.0, thinking=False, max_tokens=settings.card_draft_max_tokens
        ),
    )
    methods: dict[str, MethodDef] = {}
    for m in out["methods"]:
        methods.setdefault(m["name"], MethodDef(name=m["name"], criterion=m["criterion"]))
    return CardDraft(text=out["text"], methods=tuple(methods.values()))
