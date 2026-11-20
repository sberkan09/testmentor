"""Download, verify and extract the documents of a corpus manifest.

Layout under `eval/corpus/cache/<project>/` (not in git):
    raw/<download key><ext>       downloaded bytes, checked against the manifest SHA-256
    text/<doc id>.txt             extracted text of a single-file document
    text/<doc id>/<member>.txt    one file per zip member for member globs
    index.json                    doc id → role, text files, their SHA-256 and length
    writer_visible.txt            the only text files a test writer may be given (see below)
"""

from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import re
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

import httpx

from eval.corpus.manifest import CORPUS_DIR, Document, Download, Manifest

REPO_ROOT = CORPUS_DIR.parent.parent
USER_AGENT = "corpus-fetch/1.0"
RETRY_WAIT_S = (10.0, 30.0, 90.0, 180.0)
SLEEP = time.sleep  # replaced in tests


class CorpusError(RuntimeError):
    pass


class HashMismatch(CorpusError):
    pass


@dataclass
class FetchResult:
    key: str
    path: Path
    sha256: str
    bytes: int
    status: str  # cached | downloaded | drift | unpinned
    notes: list[str] = field(default_factory=list)


def cache_dir(project: str, root: Path = CORPUS_DIR) -> Path:
    return root / "cache" / project.lower()


def raw_path(raw_dir: Path, key: str, dl: Download) -> Path:
    suffix = PurePosixPath(unquote(urlparse(dl.url).path)).suffix.lower()
    return raw_dir / f"{key}{suffix if re.fullmatch(r'\.[a-z0-9]{1,5}', suffix) else ''}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# Download ----------------------------------------------------------------------------------------


def fetch_download(
    client: httpx.Client, key: str, dl: Download, raw_dir: Path, allow_unpinned: bool = False
) -> FetchResult:
    path = raw_path(raw_dir, key, dl)
    if path.exists() and dl.sha256 and sha256_file(path) == dl.sha256:
        return FetchResult(key, path, dl.sha256, path.stat().st_size, "cached")
    if dl.sha256 is None and not allow_unpinned:
        raise CorpusError(f"{key}: no sha256 in the manifest (pin it, or pass --allow-unpinned)")
    raw_dir.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    for attempt in range(len(RETRY_WAIT_S) + 1):
        h, n = hashlib.sha256(), 0
        with client.stream("GET", dl.url, follow_redirects=True) as resp:
            if resp.status_code in (429, 502, 503, 504) and attempt < len(RETRY_WAIT_S):
                # Publishers rate-limit bursts (ERA answers 429); wait and try again.
                after = resp.headers.get("retry-after", "")
                SLEEP(min(float(after), 300.0) if after.isdigit() else RETRY_WAIT_S[attempt])
                continue
            if resp.status_code != 200:
                raise CorpusError(f"{key}: HTTP {resp.status_code} for {dl.url}")
            with part.open("wb") as f:
                for chunk in resp.iter_bytes():
                    h.update(chunk)
                    n += len(chunk)
                    f.write(chunk)
            break
    digest = h.hexdigest()
    status, notes = "downloaded", []
    if dl.sha256 is None:
        status = "unpinned"
        notes.append(f"sha256: {digest}  bytes: {n}")
    elif digest != dl.sha256:
        if dl.stability == "immutable":
            part.unlink()
            raise HashMismatch(f"{key}: expected {dl.sha256}, got {digest} ({dl.url})")
        status = "drift"
        notes.append(f"live page changed since {dl.retrieved}: sha256 {digest}")
    part.replace(path)
    return FetchResult(key, path, digest, n, status, notes)


# Extraction --------------------------------------------------------------------------------------


def safe_member(name: str) -> bool:
    p = PurePosixPath(name.replace("\\", "/"))
    return not (p.is_absolute() or ".." in p.parts or re.match(r"^[A-Za-z]:", name))


def zip_members(data: bytes, pattern: str) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [i.filename for i in z.infolist() if not i.is_dir()]
        unsafe = [n for n in names if not safe_member(n)]
        if unsafe:
            raise CorpusError(f"unsafe zip member names: {unsafe[:3]}")
        chosen = sorted(n for n in names if fnmatch.fnmatchcase(n, pattern))
        if not chosen:
            raise CorpusError(f"no zip member matches {pattern!r}")
        return [(n, z.read(n)) for n in chosen]


class _TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg", "head"}
    BLOCK = {
        "p",
        "div",
        "li",
        "tr",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "table",
        "pre",
        "dt",
        "dd",
        "blockquote",
        "header",
        "footer",
        "main",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append("\t")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.out.append(data)


def html_to_text(data: bytes) -> str:
    p = _TextParser()
    p.feed(data.decode("utf-8", errors="replace"))
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in "".join(p.out).split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def xlsx_to_text(data: bytes) -> str:
    """Cell values as TSV, one block per sheet (stdlib only; no formulas, no styles)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")) for si in root]
        wb = ElementTree.fromstring(z.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = {r.get("Id"): r.get("Target") for r in rels}
        blocks = []
        sheets = wb.find("m:sheets", _NS)
        for sheet in sheets if sheets is not None else []:
            t = target[sheet.get(_REL)].lstrip("/")
            sheet_xml = z.read(t if t.startswith("xl/") else f"xl/{t}")
            rows = []
            for row in ElementTree.fromstring(sheet_xml).iter(f"{{{_NS['m']}}}row"):
                cells = []
                for c in row.findall("m:c", _NS):
                    v = c.find("m:v", _NS)
                    if c.get("t") == "s" and v is not None:
                        val = shared[int(v.text or 0)]
                    elif c.get("t") == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{{{_NS['m']}}}t"))
                    else:
                        val = v.text if v is not None and v.text else ""
                    cells.append(re.sub(r"\s+", " ", val).strip())
                if any(cells):
                    rows.append("\t".join(cells))
            blocks.append(f"# sheet: {sheet.get('name')}\n" + "\n".join(rows))
        return "\n\n".join(blocks) + "\n"


def pdf_to_text(data: bytes, args: tuple[str, ...]) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.pdf"
        src.write_bytes(data)
        out = subprocess.run(
            ["pdftotext", *args, str(src), "-"], capture_output=True, check=False, timeout=600
        )
    if out.returncode != 0:
        raise CorpusError(f"pdftotext failed: {out.stderr.decode(errors='replace')[:300]}")
    return out.stdout.decode("utf-8", errors="replace")


def extract_text(data: bytes, method: str, args: tuple[str, ...] = ()) -> str:
    if method == "pdftotext":
        return pdf_to_text(data, args)
    if method == "html":
        return html_to_text(data)
    if method == "xlsx":
        return xlsx_to_text(data)
    if method == "raw":
        return data.decode("utf-8-sig", errors="replace")
    raise CorpusError(f"unknown extraction method {method}")


# Documents ---------------------------------------------------------------------------------------


def _member_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", PurePosixPath(name).stem)


def build_document(
    doc: Document, raw: Path | None, text_dir: Path, repo_root: Path = REPO_ROOT
) -> tuple[list[dict], list[str]]:
    """Write the extracted text of one document; returns index entries and drift notes."""
    notes: list[str] = []
    pattern = doc.member or doc.path or ""
    single = not any(ch in pattern for ch in "*?[")
    if doc.path is not None:
        files = sorted(repo_root.glob(doc.path)) if not single else [repo_root / doc.path]
        if not files:
            raise CorpusError(f"{doc.id}: no file matches {doc.path}")
        sources = [(str(f.relative_to(repo_root)), f.read_bytes()) for f in files]
    else:
        assert raw is not None
        data = raw.read_bytes()
        sources = zip_members(data, doc.member) if doc.member else [(raw.name, data)]
    entries = []
    for name, data in sources:
        text = extract_text(data, doc.extract.method, doc.extract.args)
        if doc.snapshot:
            committed = (repo_root / doc.snapshot).read_text(encoding="utf-8")
            if committed != text:
                notes.append(f"{doc.id}: extracted text differs from snapshot {doc.snapshot}")
            text = committed  # the snapshot is authoritative for live pages
        out = (
            text_dir / f"{doc.id}.txt"
            if single
            else text_dir / doc.id / f"{_member_stem(name)}.txt"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        entries.append(
            {
                "file": str(out.relative_to(text_dir.parent)),
                "member": name if not single else None,
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "chars": len(text),
            }
        )
    return entries, notes


def select(manifest: Manifest, docs: list[str] | None, include_optional: bool) -> list[Document]:
    chosen = [manifest.document(d) for d in docs] if docs else list(manifest.documents)
    if docs or include_optional:
        return chosen
    return [d for d in chosen if d.download is None or not manifest.downloads[d.download].optional]


def fetch_manifest(
    manifest: Manifest,
    client: httpx.Client,
    root: Path = CORPUS_DIR,
    docs: list[str] | None = None,
    include_optional: bool = False,
    allow_unpinned: bool = False,
    repo_root: Path = REPO_ROOT,
) -> tuple[list[FetchResult], dict[str, dict], list[str]]:
    base = cache_dir(manifest.project, root)
    chosen = select(manifest, docs, include_optional)
    results: dict[str, FetchResult] = {}
    for key in dict.fromkeys(d.download for d in chosen if d.download):
        results[key] = fetch_download(
            client, key, manifest.downloads[key], base / "raw", allow_unpinned
        )
    index_path = base / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    notes = [n for r in results.values() for n in r.notes]
    for d in chosen:
        raw = results[d.download].path if d.download else None
        entries, drift = build_document(d, raw, base / "text", repo_root)
        notes += drift
        index[d.id] = {"role": d.role.value, "language": d.language, "texts": entries}
    base.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True))
    (base / "writer_visible.txt").write_text("".join(f + "\n" for f in writer_visible(index)))
    return list(results.values()), index, notes


def writer_visible(index: dict[str, dict]) -> list[str]:
    """Text files the test writer may see: `corpus` documents only. `reference` documents are the
    answer key and never visible; `mixed` documents are withheld whole until paket 7 strips their
    reference parts (a marker finds where an answer-key table starts, not where it ends)."""
    return sorted(e["file"] for v in index.values() if v["role"] == "corpus" for e in v["texts"])


def verify_manifest(manifest: Manifest, root: Path = CORPUS_DIR) -> dict[str, str]:
    """Hash check of cached raw files: ok | missing | mismatch | unpinned | drift (live)."""
    base = cache_dir(manifest.project, root) / "raw"
    out = {}
    for key, dl in manifest.downloads.items():
        p = raw_path(base, key, dl)
        if not p.exists():
            out[key] = "missing"
        elif dl.sha256 is None:
            out[key] = "unpinned"
        elif sha256_file(p) == dl.sha256:
            out[key] = "ok"
        else:
            out[key] = "drift" if dl.stability == "live" else "mismatch"
    return out


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        transport=transport,
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(60.0, read=300.0),
    )
