"""Knowledge base uploads (paket 10): file text, document id, add / list / remove and the
orchestrator notification, on the in-memory index (no model, no network)."""

from __future__ import annotations

import pytest

from core.kb.settings import KbSettings
from services.fake_llm import FakeEmbed
from services.kb_documents import (
    KbDocuments,
    MemoryRegistry,
    UploadRejected,
    UploadSettings,
    document_id_for,
    extract_text,
    load_upload_settings,
)
from services.kb_examples import ExamplePool
from services.kb_index import InMemoryIndex

KB = KbSettings(chunk_tokens=40, chunk_overlap_tokens=0, top_k=4)
UPLOAD = UploadSettings()


def pdf_bytes(*pages: str) -> bytes:
    """A minimal PDF with one text line per page (Helvetica, ASCII)."""
    objects: list[bytes] = []
    n = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    font = 3 + 2 * n
    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


def test_document_id_is_the_safe_file_name():
    assert document_id_for("KVKK Rehberi.pdf") == "KVKK-Rehberi.pdf"
    assert document_id_for("C:\\belgeler\\Şartname#2@v1.md") == "Şartname-2-v1.md"
    assert document_id_for("../../etc/passwd") == "passwd"
    assert document_id_for("###") == "belge"
    assert document_id_for("") == "belge"


async def test_text_markdown_and_pdf_are_read():
    assert await extract_text("a.md", "# Başlık\n\nŞifre".encode(), UPLOAD) == "# Başlık\n\nŞifre"
    assert await extract_text("a.txt", "Şifre".encode("cp1254"), UPLOAD) == "Şifre"
    text = await extract_text("a.pdf", pdf_bytes("Password lockout", "Audit log export"), UPLOAD)
    assert "Password lockout" in text and "Audit log export" in text


async def test_other_types_large_files_and_broken_pdfs_are_refused():
    with pytest.raises(UploadRejected, match="desteklenmeyen"):
        await extract_text("a.docx", b"x", UPLOAD)
    with pytest.raises(UploadRejected, match="MB"):
        await extract_text("a.txt", b"x" * 2048, UploadSettings(max_mb=0.001))
    with pytest.raises(UploadRejected, match="PDF"):
        await extract_text("a.pdf", b"%PDF-1.4 bozuk", UPLOAD)


def test_upload_settings_come_from_config():
    s = load_upload_settings()
    assert ".pdf" in s.extensions and s.max_mb > 0


def make_kb(calls: list) -> tuple[KbDocuments, InMemoryIndex]:
    index = InMemoryIndex(KB)

    def on_change(project_id, document_id, version, actor):
        calls.append((project_id, document_id, version, actor))
        return len(calls)

    kb = KbDocuments(
        index, MemoryRegistry(), ExamplePool(), FakeEmbed(), KB, UPLOAD, on_change, clock=lambda: 7
    )
    return kb, index


DOC = "# Kilitleme\n\nHesap 3 başarısız denemeden sonra 15 dakika kilitlenir.\n\n" * 3


async def test_add_list_replace_and_remove_notify_the_orchestrator():
    calls: list = []
    kb, index = make_kb(calls)
    info, seq = await kb.add("P", "Güvenlik Politikası.md", DOC.encode(), "ayse")
    assert info.id == "Güvenlik-Politikası.md" and info.name == "Güvenlik Politikası.md"
    assert info.chunks >= 2 and seq == 1
    assert calls == [("P", info.id, "v1.e0", "ayse")]
    assert [(d.id, d.chunks, d.added_by, d.added_at) for d in kb.list("P")] == [
        (info.id, info.chunks, "ayse", 7)
    ]
    assert kb.list("Q") == []
    first_ids = set(index.search("P", ["kilitleme"], 10))
    # the same file again: same passage ids, the document is replaced, not doubled
    again, _ = await kb.add("P", "Güvenlik Politikası.md", DOC.encode(), "mehmet")
    assert again.chunks == info.chunks and set(index.search("P", ["kilitleme"], 10)) == first_ids
    assert calls[-1][2] == "v2.e0" and kb.list("P")[0].added_by == "mehmet"
    assert kb.remove("P", info.id, "ayse") == 3
    assert kb.list("P") == [] and index.search("P", ["kilitleme"], 10) == []
    with pytest.raises(KeyError):
        kb.remove("P", info.id, "ayse")


async def test_a_file_without_text_is_refused_and_nothing_changes():
    calls: list = []
    kb, _ = make_kb(calls)
    with pytest.raises(UploadRejected, match="metin yok"):
        await kb.add("P", "taranmis.pdf", pdf_bytes(""), "ayse")
    with pytest.raises(UploadRejected, match="metin yok"):
        await kb.add("P", "bos.txt", b"  \n ", "ayse")
    assert calls == [] and kb.list("P") == []
