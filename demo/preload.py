"""Canlı demo için hazır proje: altın set v1 KDH "Vatandaş Başvuru Portalı" (120 gereksinim) ve
sistemin iki belgesi (Kavramsal İşletim, Yazılım Tasarım; altın set için yazılmış kurgusal belgeler)
yüklenir, üretim bitene kadar beklenir.

    python demo/preload.py http://127.0.0.1:8080 ayse PAROLA
"""

from __future__ import annotations

import csv
import io
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
KEY = "VBP"
DOCS = ("kavramsal-isletim.md", "tasarim.md")


def kdh_csv() -> bytes:
    data = json.loads((ROOT / "eval" / "golden" / "v1" / "kdh.json").read_text(encoding="utf-8"))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "language", "text"])
    for r in data["requirements"]:
        w.writerow([r["id"], r["language"], r["text"]])
    return buf.getvalue().encode("utf-8")


def wait_idle(c: httpx.Client, timeout_s: float = 1800) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        snap = c.get(f"/projects/{KEY}/snapshot").json()
        busy = any(s["stale"] + s["running"] for s in snap["stages"]) or snap["jobs"]
        if not busy:
            return snap
        if time.monotonic() > deadline:
            raise SystemExit("üretim süresinde bitmedi")
        time.sleep(3)


def main() -> int:
    base, user, password = sys.argv[1], sys.argv[2], sys.argv[3]
    c = httpx.Client(base_url=base, timeout=120)
    r = c.post("/auth/login", json={"user": user, "password": password})
    r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    if KEY not in {p["id"] for p in c.get("/projects").json()}:
        meta = {
            "name": "Vatandaş Başvuru Portalı",
            "key": KEY,
            "mapping": {"text": "text", "id": "id", "language": "language"},
        }
        c.post(
            "/projects",
            data={"meta": json.dumps(meta)},
            files={"file": ("vatandas-basvuru-portali.csv", kdh_csv(), "text/csv")},
        ).raise_for_status()
        for name in DOCS:
            path = ROOT / "eval" / "corpus" / "kdh" / "system" / name
            c.post(
                f"/projects/{KEY}/kb/documents",
                files={"file": (name, path.read_bytes(), "text/markdown")},
            ).raise_for_status()
    t = time.monotonic()
    print("üretim bekleniyor…", flush=True)
    snap = wait_idle(c)
    cases = sum(1 for n in snap["nodes"] if n["ref"]["kind"] == "test_case")
    failed = [n["ref"] for n in snap["nodes"] if n["status"] == "failed"]
    print(f"hazır: {cases} test durumu, başarısız {len(failed)}, {time.monotonic() - t:.0f} sn")
    return 1 if failed or not cases else 0


if __name__ == "__main__":
    raise SystemExit(main())
