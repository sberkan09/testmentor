"""Chunking (paket 7): heading paths, size, overlap, determinism, no-structure fallback."""

from __future__ import annotations

from core.kb.chunking import approx_tokens, chunk_document

DOC = """# Kimlik doğrulama

Genel ilkeler burada anlatılır. Oturum güvenliği önemlidir.

## Parola kuralları

Parola en az 12 karakter olmalıdır. Parola sözlükte geçen sözcüklerden oluşmamalıdır.

Parola değiştirme sıklığı zorunlu değildir; ihlal şüphesinde değiştirilir.

## Kilitleme

Hesap 3 başarısız denemeden sonra 15 dakika kilitlenir.

# Günlükleme

Her yapılandırma değişikliği kullanıcı ve zaman damgasıyla günlüğe yazılır.
"""


def test_heading_path_and_ids():
    chunks = chunk_document("D1", DOC, chunk_tokens=400, overlap_tokens=0)
    paths = [c.heading_path for c in chunks]
    assert paths == [
        ("Kimlik doğrulama",),
        ("Kimlik doğrulama", "Parola kuralları"),
        ("Kimlik doğrulama", "Kilitleme"),
        ("Günlükleme",),
    ]
    assert [c.id for c in chunks] == ["D1#0", "D1#1", "D1#2", "D1#3"]
    assert all(c.document_id == "D1" for c in chunks)
    assert "12 karakter" in chunks[1].text and "ihlal şüphesinde" in chunks[1].text


def test_start_is_the_offset_of_the_text():
    chunks = chunk_document("D1", DOC, chunk_tokens=20, overlap_tokens=3)
    assert len(chunks) > 4
    for c in chunks:
        assert DOC[c.start : c.start + len(c.text)] == c.text


def test_numbered_sections_make_a_path():
    text = (
        "1 Kapsam\nBu belge kapsamı tanımlar.\n\n"
        "1.1 Amaç\nAmaç, testlerin izlenebilirliğidir.\n\n"
        "2 Gereksinimler\nSistem günlük tutmalıdır.\n"
    )
    chunks = chunk_document("S", text, chunk_tokens=400, overlap_tokens=0)
    assert [c.heading_path for c in chunks] == [
        ("1 Kapsam",),
        ("1 Kapsam", "1.1 Amaç"),
        ("2 Gereksinimler",),
    ]


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
    a = chunk_document("D1", DOC, chunk_tokens=400, overlap_tokens=0)[1]
    assert a.prompt_text() == f"[D1 §Kimlik doğrulama > Parola kuralları] {a.text}"
    edited_doc = DOC.replace("12 karakter", "14 karakter")
    edited = chunk_document("D1", edited_doc, chunk_tokens=400, overlap_tokens=0)[1]
    assert edited.id == a.id and edited.passage_id != a.passage_id
    plain = chunk_document("D2", "Başlıksız metin.", chunk_tokens=400, overlap_tokens=0)[0]
    assert plain.prompt_text() == "[D2] Başlıksız metin."
