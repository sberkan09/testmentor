"""Chunking (paket 7): heading paths, size, overlap, determinism, no-structure fallback."""

from __future__ import annotations

from core.kb.chunking import approx_tokens, chunk_document

DOC = """# Kimlik doğrulama

Hesap 3 başarısız denemeden sonra 15 dakika kilitlenir.

## Parola kuralları

Parola en az 12 karakter olmalıdır ve sözlükte geçmemelidir.

## Kilitleme

Kilit açma yalnızca yönetici tarafından yapılır, kayıt tutulur.

# Günlükleme

Her yapılandırma değişikliği günlüğe yazılır, kayıt silinemez.
"""
FIT = (
    30  # tokens: 120 characters, about one section each (a chunk ends at a heading once half full)
)


def test_heading_path_and_ids():
    chunks = chunk_document("D1", DOC, chunk_tokens=FIT, overlap_tokens=0)
    assert [c.heading_path for c in chunks] == [
        ("Kimlik doğrulama",),
        ("Kimlik doğrulama", "Parola kuralları"),
        ("Kimlik doğrulama", "Kilitleme"),
        ("Günlükleme",),
    ]
    assert [c.id for c in chunks] == ["D1#0", "D1#1", "D1#2", "D1#3"]
    assert all(c.document_id == "D1" for c in chunks)
    assert chunks[1].text.startswith("## Parola kuralları") and "12 karakter" in chunks[1].text


def test_start_is_the_offset_of_the_text():
    chunks = chunk_document("D1", DOC, chunk_tokens=12, overlap_tokens=3)
    assert len(chunks) > 4
    for c in chunks:
        assert DOC[c.start : c.start + len(c.text)] == c.text


def test_numbered_sections_make_a_path():
    text = (
        "1 Kapsam\n\nBu belge kapsamı tanımlar ve sınırlarını çizer.\n\n"
        "1.1 Amaç\n\nAmaç, testlerin izlenebilirliğini sağlamaktır.\n\n"
        "2 Gereksinimler\n\nSistem günlük tutmalı ve saklamalıdır.\n"
    )
    chunks = chunk_document("S", text, chunk_tokens=20, overlap_tokens=0)
    assert [c.heading_path for c in chunks] == [
        ("1 Kapsam",),
        ("1 Kapsam", "1.1 Amaç"),
        ("2 Gereksinimler",),
    ]


def test_the_first_line_of_a_wrapped_clause_is_not_a_heading():
    text = (
        "# A\n\nIntro paragraph.\n\n"
        "3.1 The system shall lock the account after three failed\n"
        "attempts and keep it locked for fifteen minutes.\n"
    )
    chunks = chunk_document("S", text, chunk_tokens=400, overlap_tokens=0)
    assert [c.heading_path for c in chunks] == [("A",)]


def test_small_sections_share_a_chunk_and_keep_their_headings():
    text = "".join(f"## Madde {i}\n\nKısa metin {i}.\n\n" for i in range(6))
    chunks = chunk_document("D", "# Üst\n\n" + text, chunk_tokens=100, overlap_tokens=0)
    assert len(chunks) == 1
    assert chunks[0].heading_path == ("Üst",)  # the path the merged sections share
    assert "## Madde 0" in chunks[0].text and "## Madde 5" in chunks[0].text  # still searchable


def test_chunk_count_follows_the_target_in_a_heading_dense_document():
    text = "".join(f"## Madde {i}\n\nKısa metin {i}, birkaç sözcük daha.\n\n" for i in range(400))
    counts = {
        t: len(chunk_document("D", text, chunk_tokens=t, overlap_tokens=0)) for t in (300, 400, 800)
    }
    assert counts[300] > counts[400] > counts[800]
    assert counts[300] > 2 * counts[800] * 0.9
    sizes = [len(c.text) for c in chunk_document("D", text, chunk_tokens=400, overlap_tokens=0)]
    assert sorted(sizes)[len(sizes) // 2] > 800  # most chunks near the 1.600 character target


def test_sentences_that_look_numbered_are_not_headings():
    text = "# A\n\n3 failed attempts lock the account.\n\nThe second paragraph follows.\n"
    chunks = chunk_document("S", text, chunk_tokens=400, overlap_tokens=0)
    assert len(chunks) == 1 and chunks[0].heading_path == ("A",)


def test_size_limit_and_overlap():
    para = " ".join(f"sözcük{i}" for i in range(400))  # ~ 3.3k characters
    text = f"# B\n\n{para}\n"
    chunks = chunk_document("D", text, chunk_tokens=100, overlap_tokens=10)  # 400 / 40 characters
    assert len(chunks) > 3
    assert all(len(c.text) <= 400 for c in chunks)
    assert all(approx_tokens(c.text) <= 100 for c in chunks)
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.start < a.start + len(a.text)  # overlap
        assert b.start >= a.start + len(a.text) - 40 - 12  # about overlap_tokens * 4 characters
    assert "sözcük399" in chunks[-1].text and "sözcük0 " in chunks[0].text


def test_no_overlap_when_zero_and_no_word_is_cut():
    para = " ".join(f"w{i:03d}" for i in range(300))
    chunks = chunk_document("D", para, chunk_tokens=50, overlap_tokens=0)
    words = [w for c in chunks for w in c.text.split()]
    assert words == para.split()  # nothing lost, nothing duplicated, no word cut


def test_text_without_structure_is_cut_hard():
    blob = "x" * 5000
    chunks = chunk_document("D", blob, chunk_tokens=100, overlap_tokens=0)
    assert len(chunks) == 13 and all(len(c.text) <= 400 for c in chunks)
    assert "".join(c.text for c in chunks) == blob


def test_deterministic_and_empty():
    a = chunk_document("D1", DOC, chunk_tokens=30, overlap_tokens=5)
    b = chunk_document("D1", DOC, chunk_tokens=30, overlap_tokens=5)
    assert a == b
    assert chunk_document("D1", "  \n\n ", chunk_tokens=30, overlap_tokens=5) == []


def test_chars_per_token_setting():
    text = "# T\n\n" + " ".join(["kelime"] * 200)
    few = chunk_document("D", text, chunk_tokens=100, overlap_tokens=0, chars_per_token=2)
    many = chunk_document("D", text, chunk_tokens=100, overlap_tokens=0, chars_per_token=4)
    assert len(few) > len(many)


def test_passage_text_and_id_follow_the_text():
    a = chunk_document("D1", DOC, chunk_tokens=FIT, overlap_tokens=0)[1]
    assert a.prompt_text() == f"[D1 §Kimlik doğrulama > Parola kuralları] {a.text}"
    edited_doc = DOC.replace("12 karakter", "14 karakter")
    edited = chunk_document("D1", edited_doc, chunk_tokens=FIT, overlap_tokens=0)[1]
    assert edited.id == a.id and edited.passage_id != a.passage_id
    plain = chunk_document("D2", "Başlıksız metin.", chunk_tokens=400, overlap_tokens=0)[0]
    assert plain.prompt_text() == "[D2] Başlıksız metin."
