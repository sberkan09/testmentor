"""Document text to chunks with their heading path (docs/tasarim.md, İndeks; paket 7).

Pure and deterministic. Headings are markdown `#` lines or numbered section lines (`1.2 Title`,
followed by a blank line, so the first line of a wrapped clause is not taken for one).

The text is cut into atoms: heading lines and paragraphs (a paragraph longer than the target, as
in extracted PDF text, flattened JSON or CSV rows, is cut at a sentence end, else at a space,
else hard). Atoms are packed in document order up to the target size, so the chunk size follows
`chunk_tokens` and not the size of the sections: small sections share a chunk (their heading
lines stay in its text, which keeps them searchable), and a chunk ends before a heading once it
is at least half full. `heading_path` is the longest heading path the chunk's atoms share.
Consecutive chunks inside one section overlap by about `overlap_tokens`. A chunk's text is always
the document slice starting at `start`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_MARKDOWN = re.compile(r"^(#{1,6})[ \t]+(\S.*?)[ \t]*#*[ \t]*$")
_NUMBERED = re.compile(r"^(\d+(?:\.\d+){0,5})\.?[ \t]+([A-ZÇĞİÖŞÜ][^\n]{0,100})$")
_LEADERS = re.compile(r"\.{3,}|\s\d+$")  # table of contents lines
_PARAGRAPH_BREAK = re.compile(r"\n[ \t\r]*\n")
_LINE = re.compile(r"[^\n]*\n|[^\n]+\Z")
_BLANK = re.compile(r"[ \t\r]*\n?\Z")


@dataclass(frozen=True)
class Chunk:
    id: str
    """`<document_id>#<sequence>` (sequence from 0 in document order)."""
    document_id: str
    heading_path: tuple[str, ...]
    text: str
    start: int
    """Character offset of `text` in the document."""

    def prompt_text(self) -> str:
        """`[<document> §<heading path>] <text>` (the layout of the golden passages)."""
        path = " > ".join(self.heading_path)
        label = f"{self.document_id} §{path}" if path else self.document_id
        return f"[{label}] {self.text}"

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.prompt_text().encode("utf-8")).hexdigest()[:8]

    @property
    def passage_id(self) -> str:
        """`<chunk id>@<digest>`: what retrieval nodes and test sets hash. The digest makes the
        id change when the text behind it changes (a re-chunked or edited document), so a test
        set cannot keep an id whose prompt text is different."""
        return f"{self.id}@{self.digest}"


@dataclass(frozen=True)
class _Atom:
    start: int
    end: int
    path: tuple[str, ...]
    heading: bool = False


def approx_tokens(text: str, chars_per_token: int = 4) -> int:
    return -(-len(text) // chars_per_token)


def _heading(line: str, next_line: str | None) -> tuple[int, str] | None:
    line = line.rstrip("\r\n")
    m = _MARKDOWN.match(line)
    if m:
        return len(m.group(1)), m.group(2).strip()
    m = _NUMBERED.match(line)
    if (
        m
        and not line.endswith((".", ";", ","))
        and not _LEADERS.search(line)
        and (next_line is None or _BLANK.match(next_line))
    ):
        return m.group(1).count(".") + 1, line.strip()
    return None


def _sections(text: str) -> list[tuple[tuple[str, ...], tuple[int, int] | None, int, int]]:
    """(heading path, heading line span, body start, body end) per section in document order.
    The first section has no heading when the text starts with body text."""
    lines = list(_LINE.finditer(text))
    out: list[tuple[tuple[str, ...], tuple[int, int] | None, int, int]] = []
    stack: list[tuple[int, str]] = []
    path: tuple[str, ...] = ()
    heading_span: tuple[int, int] | None = None
    body_start = 0
    for n, m in enumerate(lines):
        nxt = lines[n + 1].group(0) if n + 1 < len(lines) else None
        found = _heading(m.group(0), nxt)
        if found is None:
            continue
        out.append((path, heading_span, body_start, m.start()))
        level, title = found
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        path = tuple(t for _, t in stack)
        heading_span = _strip(text, m.start(), m.end())
        body_start = m.end()
    out.append((path, heading_span, body_start, len(text)))
    return out


def _strip(text: str, s: int, e: int) -> tuple[int, int]:
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return s, e


def _cut_point(text: str, s: int, e: int, limit: int) -> int:
    """Where to end a piece that starts at `s` and may be at most `limit` long (`e - s > limit`)."""
    if text[s + limit].isspace():
        return s + limit
    window = text[s : s + limit]
    floor = limit // 2
    for pattern in (r"[.!?;:]\s", r"\s"):
        last = -1
        for m in re.finditer(pattern, window):
            last = m.start()
        if last >= floor:
            return s + last + (1 if pattern != r"\s" else 0)
    return s + limit


def _paragraphs(text: str, s: int, e: int, limit: int) -> list[tuple[int, int]]:
    """Paragraph spans of `text[s:e]`; a paragraph longer than `limit` is cut into pieces."""
    spans: list[tuple[int, int]] = []
    pos = s
    for m in [*_PARAGRAPH_BREAK.finditer(text, s, e), None]:
        end = m.start() if m else e
        a, b = _strip(text, pos, end)
        while b - a > limit:
            cut = _cut_point(text, a, b, limit)
            piece = _strip(text, a, cut)
            if piece[1] > piece[0]:
                spans.append(piece)
            a, _ = _strip(text, cut, b)
        if b > a:
            spans.append((a, b))
        if m:
            pos = m.end()
    return spans


def _snap(text: str, pos: int, end: int) -> int:
    """`pos` moved forward to the start of a word (never inside one)."""
    if pos <= 0 or pos >= end or text[pos - 1].isspace():
        return pos
    word_end = pos
    while word_end < end and not text[word_end].isspace():
        word_end += 1
    if word_end >= end:
        return pos  # no space to snap to (hard-cut text)
    while word_end < end and text[word_end].isspace():
        word_end += 1
    return word_end


def _common_prefix(paths: list[tuple[str, ...]]) -> tuple[str, ...]:
    prefix = paths[0]
    for p in paths[1:]:
        n = 0
        while n < min(len(prefix), len(p)) and prefix[n] == p[n]:
            n += 1
        prefix = prefix[:n]
    return prefix


def chunk_document(
    document_id: str,
    text: str,
    *,
    chunk_tokens: int,
    overlap_tokens: int,
    chars_per_token: int = 4,
) -> list[Chunk]:
    limit = max(1, chunk_tokens * chars_per_token)
    overlap = min(max(0, overlap_tokens * chars_per_token), limit // 2)
    piece_limit = max(limit - overlap, limit // 2, 1)
    atoms: list[_Atom] = []
    for path, heading_span, b0, b1 in _sections(text):
        if heading_span is not None and heading_span[1] > heading_span[0]:
            atoms.append(_Atom(*heading_span, path, heading=True))
        atoms += [_Atom(s, e, path) for s, e in _paragraphs(text, b0, b1, piece_limit)]
    spans: list[tuple[tuple[str, ...], int, int]] = []
    prev: tuple[int, int, tuple[str, ...]] | None = None
    i = 0
    while i < len(atoms):
        first = atoms[i]
        start = first.start
        if prev is not None and overlap and not first.heading and prev[2] == first.path:
            back = min(overlap, (prev[1] - prev[0]) // 2)
            start = min(start, _snap(text, prev[1] - back, first.end))
        if first.end - start > limit:
            start = _snap(text, first.end - limit, first.end)
        j = i + 1
        while j < len(atoms) and atoms[j].end - start <= limit:
            if atoms[j].heading and atoms[j - 1].end - start >= limit // 2:
                break  # a section boundary once the chunk is at least half full
            j += 1
        end = atoms[j - 1].end
        path = _common_prefix([a.path for a in atoms[i:j]])
        spans.append((path, start, end))
        prev = (start, end, atoms[j - 1].path)
        i = j
    return [
        Chunk(
            id=f"{document_id}#{n}",
            document_id=document_id,
            heading_path=path,
            text=text[s:e],
            start=s,
        )
        for n, (path, s, e) in enumerate(spans)
    ]
