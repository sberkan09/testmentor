"""What the offline bundle carries (paket 12), as shell assignments for infra/offline/build.sh.

    python scripts/offline_manifest.py [--engine vllm] [--model qwen3.8-27b]

Images: the engine (default from config/runtime.yaml), the embedding server and Postgres; models:
the served model and the embedding model, each `repo@revision` (a pinned commit is required) with
the files the download skips. Runs inside the app image on the build machine, so the machine needs
only Docker.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.infra_render import load_embedding_server, load_infra  # noqa: E402
from services.settings import load_engines, load_models, load_runtime  # noqa: E402


def manifest(engine_key: str | None = None, model_key: str | None = None) -> dict[str, str]:
    runtime = load_runtime()["llm"]
    engine_key = engine_key or runtime["engine"]
    model_key = model_key or runtime["model"]
    engine = load_engines()[engine_key]
    model = load_models()[model_key]
    emb = load_embedding_server()
    infra = load_infra()
    if not model.revision or not emb.get("revision"):
        raise SystemExit("config: model ve embedding için revision (commit) sabitlenmeli")
    images = sorted({engine.image, emb["image"], infra["postgres"]["image"]})
    return {
        "ENGINE": engine_key,
        "MODEL": model_key,
        "IMAGES": " ".join(images),
        # repo@revision@ignore-patterns (comma separated), one per model
        "MODELS": " ".join(
            [
                f"{model.repo_id}@{model.revision}@{','.join(model.download_ignore)}",
                f"{emb['model']}@{emb['revision']}@{','.join(emb.get('download_ignore', []))}",
            ]
        ),
        "MODEL_GB": str(int(model.approx_size_gb or 0)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine")
    ap.add_argument("--model")
    args = ap.parse_args()
    for key, value in manifest(args.engine, args.model).items():
        print(f"{key}={shlex.quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
