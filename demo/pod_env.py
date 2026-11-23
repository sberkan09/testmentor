"""Prints `export` lines pointing the API at the recorded Runpod pod (LLM and embedding URLs)."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.runpod_state import base_urls_from_state  # noqa: E402

urls = base_urls_from_state()
if not urls:
    raise SystemExit("kayıtlı pod yok: önce make up")
print(f"export LLM_BASE_URL={shlex.quote(urls['llm'])}")
print(f"export EMBEDDING_BASE_URL={shlex.quote(urls['embedding'])}")
