"""Demo videosu: ekran akışı karelerinden (CDP screencast) MP4, uzun beklemeler hızlandırılmış.

    python demo/make_video.py KARE_DİZİNİ İŞARETLER.json ÇIKTI.mp4 [--speed-to 6]

KARE_DİZİNİ web/e2e/demo.spec.ts'in `DEMO_FRAMES` dizinidir (`frames.json`: kare dosyası ve zaman
damgası). İŞARETLER.json `DEMO_MARKS` dosyasıdır (`t0`, `t1`: bekleme aralığının mutlak zamanı).
Her kare bir sonrakine kadar ekranda kalır; işaretli aralıktaki kareler en çok `--speed-to`
saniyeye sığacak oranda kısaltılır ("hızlandırıldı" etiketi kayıt sırasında sayfaya çizilir).
ffmpeg gerekir.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def durations(frames: list[dict], end: float, marks: list[dict], speed_to: float) -> list[float]:
    times = [f["t"] for f in frames] + [end]
    spans = []
    for m in marks:
        t0, t1 = m.get("t0"), m.get("t1")
        if t0 is not None and t1 is not None and t1 - t0 > 2 * speed_to:
            spans.append((t0, t1, (t1 - t0) / speed_to))
    out = []
    for i in range(len(frames)):
        a, b = times[i], times[i + 1]
        d = max(b - a, 0.0)
        for t0, t1, speed in spans:  # compress the part of [a, b] that lies inside a span
            inside = max(0.0, min(b, t1) - max(a, t0))
            d -= inside - inside / speed
        out.append(d)
    return out


def thin(
    frames: list[dict], ds: list[float], min_d: float = 1 / 30
) -> tuple[list[dict], list[float]]:
    """Drop frames shorter than one output frame, giving their time to the previous kept frame
    (a sped-up span has many frames of a few milliseconds each)."""
    kept: list[dict] = [frames[0]]
    out: list[float] = [ds[0]]
    for f, d in zip(frames[1:], ds[1:], strict=True):
        if out[-1] < min_d:
            out[-1] += d
        else:
            kept.append(f)
            out.append(d)
    return kept, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("frames", type=Path)
    ap.add_argument("marks", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--speed-to", type=float, default=6.0)
    ap.add_argument("--tail", type=float, default=2.0, help="last frame stays this long")
    args = ap.parse_args()
    meta = json.loads((args.frames / "frames.json").read_text(encoding="utf-8"))
    frames, end = meta["frames"], meta["end"]
    marks = json.loads(args.marks.read_text(encoding="utf-8"))["marks"]
    frames, ds = thin(frames, durations(frames, end, marks, args.speed_to))
    ds[-1] = max(ds[-1], args.tail)
    lines = ["ffconcat version 1.0"]
    for f, d in zip(frames, ds, strict=True):
        lines += [f"file '{(args.frames / f['file']).resolve()}'", f"duration {d:.4f}"]
    lines.append(f"file '{(args.frames / frames[-1]['file']).resolve()}'")  # concat demuxer quirk
    listing = args.frames / "list.ffconcat"
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(listing),
        "-vf",
        "scale=1440:900:force_original_aspect_ratio=decrease,pad=1440:900:(ow-iw)/2:(oh-ih)/2,"
        "fps=30,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-movflags",
        "+faststart",
        str(args.out),
    ]
    subprocess.run(cmd, check=True)
    print(f"{args.out}: {sum(ds):.1f} sn, {len(frames)} kare")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
