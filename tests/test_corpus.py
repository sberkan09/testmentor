import hashlib
import io
import json
import zipfile

import httpx
import pytest
from pydantic import ValidationError

from eval.corpus.fetch import (
    CorpusError,
    HashMismatch,
    extract_text,
    fetch_manifest,
    html_to_text,
    make_client,
    safe_member,
    verify_manifest,
    xlsx_to_text,
    zip_members,
)
from eval.corpus.manifest import Manifest, Role, load_manifest, manifest_paths

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
DOC = {
    "title": "t",
    "publisher": "p",
    "version": "1",
    "kind": "standard",
    "role": "corpus",
    "language": "en",
    "extract": {"method": "raw"},
    "license": "CC BY 4.0",
    "license_evidence": "colophon",
    "repo_text": "yes",
}


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_repository_manifests_are_valid():
    paths = manifest_paths()
    assert {p.parent.name for p in paths} >= {"etc", "kdh"}
    for p in paths:
        m = load_manifest(p)
        assert m.project == p.parent.name.upper()
        # every document states a licence source; reference documents exist in each project
        assert all(d.license_evidence for d in m.documents)
        assert any(d.role == Role.reference for d in m.documents)
        assert all(dl.sha256 for dl in m.downloads.values()), "unpinned download"
        for d in m.documents:
            if d.path:
                assert list(ROOT.glob(d.path)), d.path


def test_manifest_rules():
    base = {"project": "XX", "downloads": {"a": {"url": "https://x/a.txt", "sha256": "0" * 64}}}
    Manifest.model_validate(base | {"documents": [DOC | {"id": "A", "download": "a"}]})
    bad = [
        [DOC | {"id": "A"}],  # neither download nor path
        [DOC | {"id": "A", "download": "a", "path": "x"}],  # both
        [DOC | {"id": "A", "download": "b"}],  # unknown download
        [DOC | {"id": "A", "download": "a", "role": "mixed"}],  # mixed without parts
        [DOC | {"id": "A", "download": "a"}, DOC | {"id": "A", "download": "a"}],  # duplicate
        [DOC | {"id": "A", "download": "a", "repo_text": "no", "snapshot": "s.txt"}],
    ]
    for docs in bad:
        with pytest.raises(ValidationError):
            Manifest.model_validate(base | {"documents": docs})
    with pytest.raises(ValidationError):  # unused download
        Manifest.model_validate(
            base
            | {
                "downloads": base["downloads"] | {"b": {"url": "https://x/b"}},
                "documents": [DOC | {"id": "A", "download": "a"}],
            }
        )
    with pytest.raises(ValidationError):  # live page without date
        Manifest.model_validate(
            {
                "project": "XX",
                "downloads": {"a": {"url": "https://x/", "stability": "live"}},
                "documents": [DOC | {"id": "A", "download": "a", "repo_text": "no"}],
            }
        )


def manifest_for(content: bytes, **dl) -> Manifest:
    return Manifest.model_validate(
        {
            "project": "XX",
            "downloads": {
                "s": {"url": "https://example.org/spec.zip", "sha256": sha(content)} | dl
            },
            "documents": [
                DOC | {"id": "S-1", "download": "s", "member": "spec/part1.txt"},
                DOC | {"id": "S-ALL", "download": "s", "member": "spec/*.txt", "role": "reference"},
            ],
        }
    )


def test_fetch_extracts_members_and_uses_cache(tmp_path):
    content = zip_bytes({"spec/part1.txt": b"one", "spec/part2.txt": b"two", "x.bin": b"\0"})
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return httpx.Response(200, content=content)

    m = manifest_for(content)
    with make_client(httpx.MockTransport(handler)) as c:
        results, index, notes = fetch_manifest(m, c, root=tmp_path)
        assert [r.status for r in results] == ["downloaded"] and not notes
        assert (tmp_path / "cache/xx/text/S-1.txt").read_text() == "one"
        assert [e["member"] for e in index["S-ALL"]["texts"]] == [
            "spec/part1.txt",
            "spec/part2.txt",
        ]
        assert index["S-ALL"]["role"] == "reference"
        results, _, _ = fetch_manifest(m, c, root=tmp_path)
    assert [r.status for r in results] == ["cached"] and len(calls) == 1
    assert verify_manifest(m, tmp_path) == {"s": "ok"}
    stored = json.loads((tmp_path / "cache/xx/index.json").read_text())
    assert set(stored) == {"S-1", "S-ALL"}
    # the answer key never reaches the writer's file list
    visible = (tmp_path / "cache/xx/writer_visible.txt").read_text().split()
    assert visible == ["text/S-1.txt"]


def test_hash_mismatch_fails_and_leaves_nothing(tmp_path):
    m = manifest_for(b"expected")
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"tampered"))
    with make_client(transport) as c, pytest.raises(HashMismatch):
        fetch_manifest(m, c, root=tmp_path)
    assert not list((tmp_path / "cache/xx/raw").iterdir())
    assert verify_manifest(m, tmp_path) == {"s": "missing"}


def test_unpinned_needs_permission(tmp_path):
    content = zip_bytes({"spec/part1.txt": b"one"})
    m = Manifest.model_validate(
        {
            "project": "XX",
            "downloads": {"s": {"url": "https://example.org/s.zip"}},
            "documents": [DOC | {"id": "S-1", "download": "s", "member": "spec/part1.txt"}],
        }
    )
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=content))
    with make_client(transport) as c:
        with pytest.raises(CorpusError):
            fetch_manifest(m, c, root=tmp_path)
        results, _, _ = fetch_manifest(m, c, root=tmp_path, allow_unpinned=True)
    assert results[0].status == "unpinned" and sha(content) in results[0].notes[0]


def test_live_page_drift_uses_snapshot(tmp_path):
    (tmp_path / "snap.txt").write_text("committed\n", encoding="utf-8")
    m = Manifest.model_validate(
        {
            "project": "XX",
            "downloads": {
                "p": {
                    "url": "https://example.org/page",
                    "sha256": "0" * 64,
                    "stability": "live",
                    "retrieved": "2026-11-20",
                }
            },
            "documents": [
                DOC
                | {
                    "id": "P",
                    "download": "p",
                    "extract": {"method": "html"},
                    "snapshot": "snap.txt",
                }
            ],
        }
    )
    page = b"<html><body><p>changed</p></body></html>"
    with make_client(httpx.MockTransport(lambda r: httpx.Response(200, content=page))) as c:
        results, _, notes = fetch_manifest(m, c, root=tmp_path, repo_root=tmp_path)
    assert results[0].status == "drift" and len(notes) == 2
    assert (tmp_path / "cache/xx/text/P.txt").read_text() == "committed\n"


def test_optional_downloads_skipped_by_default(tmp_path):
    m = manifest_for(b"x", optional=True)
    with make_client(httpx.MockTransport(lambda r: httpx.Response(500))) as c:
        results, index, _ = fetch_manifest(m, c, root=tmp_path)
    assert results == [] and index == {}


def test_unsafe_zip_members_rejected():
    assert safe_member("a/b.pdf") and not safe_member("../x") and not safe_member("/etc/x")
    assert not safe_member("C:\\x") and not safe_member("a\\..\\..\\x")
    with pytest.raises(CorpusError):
        zip_members(zip_bytes({"../evil.txt": b"x"}), "*")
    with pytest.raises(CorpusError):
        zip_members(zip_bytes({"a.txt": b"x"}), "b*")


def test_html_and_raw_extraction():
    html = (
        b"<html><head><title>T</title><style>p{}</style></head><body><nav>x</nav>"
        b"<h1>Rule</h1><p>Applicability &amp; expectation</p><script>bad()</script>"
        b"<table><tr><td>a</td><td>b</td></tr></table></body></html>"
    )
    text = html_to_text(html)
    assert "Applicability & expectation" in text and "bad()" not in text and "p{}" not in text
    assert "a b" in text or "a\tb" in text
    assert extract_text("\ufeffid,text\n".encode(), "raw") == "id,text\n"


def test_xlsx_extraction():
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    files = {
        "xl/workbook.xml": f'<workbook {ns} {rel}><sheets><sheet name="AC" sheetId="1" r:id="rId1"/></sheets></workbook>',  # noqa: E501
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',  # noqa: E501
        "xl/sharedStrings.xml": f"<sst {ns}><si><t>AC-07</t></si><si><t>Examine</t></si></sst>",
        "xl/worksheets/sheet1.xml": f'<worksheet {ns}><sheetData><row><c t="s"><v>0</v></c><c t="s"><v>1</v></c><c><v>3</v></c></row></sheetData></worksheet>',  # noqa: E501
    }
    data = zip_bytes({k: v.encode() for k, v in files.items()})
    assert xlsx_to_text(data) == "# sheet: AC\nAC-07\tExamine\t3\n"


def test_rate_limit_is_retried(tmp_path, monkeypatch):
    import eval.corpus.fetch as f

    waits = []
    monkeypatch.setattr(f, "SLEEP", waits.append)
    content = zip_bytes({"spec/part1.txt": b"one", "spec/part2.txt": b"two"})
    replies = iter([httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(503)])
    m = manifest_for(content)

    def handler(req):
        return next(replies, None) or httpx.Response(200, content=content)

    with make_client(httpx.MockTransport(handler)) as c:
        results, _, _ = fetch_manifest(m, c, root=tmp_path)
    assert results[0].status == "downloaded" and waits == [7.0, f.RETRY_WAIT_S[1]]


def test_path_glob_documents(tmp_path):
    d = tmp_path / "snap"
    d.mkdir()
    (d / "b.md").write_text("B")
    (d / "a.md").write_text("A")
    m = Manifest.model_validate(
        {
            "project": "XX",
            "documents": [
                DOC
                | {
                    "id": "R",
                    "path": "snap/*.md",
                    "role": "reference",
                    "origin": "https://example.org@abc",
                }
            ],
        }
    )
    with make_client(httpx.MockTransport(lambda r: httpx.Response(500))) as c:
        _, index, _ = fetch_manifest(m, c, root=tmp_path, repo_root=tmp_path)
    assert [e["member"] for e in index["R"]["texts"]] == ["snap/a.md", "snap/b.md"]
    assert (tmp_path / "cache/xx/text/R/a.txt").read_text() == "A"
    with pytest.raises(ValidationError):  # external copy without origin
        Manifest.model_validate({"project": "XX", "documents": [DOC | {"id": "R", "path": "x"}]})
