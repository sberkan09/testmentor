"""Run a batch of experiments on one pod and always delete the pod at the end.

    python -m eval.batch config/batches/<name>.yaml

Batch file: `max_hours` (watchdog deadline), `steps: [{experiment, engine?, model?, overrides?}]`.
The first step opens the pod (or reuses a recorded one), later steps reconfigure it in place.
`make down` runs in a `finally` block and on SIGTERM/SIGHUP, so a failing step or a stopped
session does not leave the pod running; the pod's own watchdog is the second line of defence.
"""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
PY = [sys.executable]


def sh(args: list[str]) -> int:
    print("$", " ".join(args), flush=True)
    return subprocess.call(args, cwd=ROOT)


def overrides_args(step: dict[str, Any]) -> list[str]:
    out = []
    for k, v in (step.get("overrides") or {}).items():
        out += ["--override", f"{k}={v}"]
    for key in ("engine", "model"):
        if step.get(key):
            out += [f"--{key}", str(step[key])]
    return out


def run_batch(batch: dict[str, Any], runner=sh) -> dict[str, str]:
    results: dict[str, str] = {}
    state = ROOT / "infra" / ".runpod-state.json"
    try:
        for i, step in enumerate(batch["steps"]):
            exp = step["experiment"]
            if i == 0 and not (state.exists() and '"pod"' in state.read_text()):
                cmd = PY + [
                    "scripts/runpod.py",
                    "up",
                    "--max-hours",
                    str(batch.get("max_hours", 4)),
                ]
            else:
                cmd = PY + ["scripts/runpod.py", "reconfigure"]
            if runner(cmd + overrides_args(step)) != 0:
                results[exp] = "pod açılamadı/yapılandırılamadı"
                continue
            if runner(PY + ["scripts/runpod.py", "wait", "--timeout", "900"]) != 0:
                results[exp] = "sunucu hazır olmadı"
                continue
            code = runner(PY + ["-m", "eval.run", "--config", f"config/experiments/{exp}.yaml"])
            results[exp] = "tamam" if code == 0 else f"hata (çıkış {code})"
    finally:
        down = runner(PY + ["scripts/runpod.py", "down"])
        results["_down"] = "pod silindi" if down == 0 else "SİLME DOĞRULANAMADI — elle kontrol et"
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("batch")
    args = ap.parse_args()
    batch = yaml.safe_load(Path(args.batch).read_text(encoding="utf-8"))

    def stop(signum, _frame):
        raise KeyboardInterrupt(f"sinyal {signum}")

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)
    results = run_batch(batch)
    for k, v in results.items():
        print(f"{k}: {v}")
    return 0 if results.get("_down") == "pod silindi" else 1


if __name__ == "__main__":
    raise SystemExit(main())
