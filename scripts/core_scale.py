"""Ölçek kontrolü (paket 2): sahte üreticilerle N gereksinimlik projede çekirdeğin süresi.

    uv run python scripts/core_scale.py 2000

Model çağrısı yok. Baştan üretimi iki biçimde ölçer: sonuçlar tek tek (`settle`) ve dalga dalga
toplu (`settle_many`); ardından tek olayların (`apply`) süresini yazar.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.events import KbDocumentAdded, RequirementMoved, RequirementTextChanged  # noqa: E402
from core.graph import new_project  # noqa: E402
from core.invalidation import analyze, apply, settle, settle_many  # noqa: E402
from core.nodes import RequirementContent  # noqa: E402
from tests.core.helpers import CONFIGS, fake_result  # noqa: E402

CLUSTER_SIZE = 20


def build(n: int):
    reqs = [RequirementContent(id=f"R{i:04d}", text=f"Gereksinim {i} metni.") for i in range(n)]
    clusters = {
        f"C{c:03d}": [r.id for r in reqs[c * CLUSTER_SIZE : (c + 1) * CLUSTER_SIZE]]
        for c in range(n // CLUSTER_SIZE)
    }
    return new_project(
        "S", requirements=reqs, clusters=clusters, card="Kart", index_version="v1",
        stage_configs=CONFIGS,
    )  # fmt: skip


def main(n: int) -> None:
    state = build(n)
    print(f"{n} gereksinim, içe almadan sonra {len(state.nodes)} düğüm")

    t = time.perf_counter()
    batched, waves = state, 0
    while ready := analyze(batched).ready:
        batched = settle_many(batched, [(r, fake_result(batched, r)) for r in ready]).state
        waves += 1
    print(f"toplu üretim: {waves} dalga, {time.perf_counter() - t:.1f} sn")

    t, count = time.perf_counter(), 0
    while ready := analyze(state).ready:
        for r in ready:
            state = settle(state, r, fake_result(state, r)).state
            count += 1
    total = time.perf_counter() - t
    per = 1000 * total / count
    print(f"tek tek üretim: {count} settle, {total:.1f} sn, settle başına {per:.1f} ms")

    for label, event in [
        ("taşıma", RequirementMoved(requirement="R0001", to_cluster="C001")),
        ("metin değişikliği", RequirementTextChanged(requirement="R0005", text="Yeni metin")),
        ("belge ekleme", KbDocumentAdded(document_id="d2", index_version="v2")),
    ]:
        t = time.perf_counter()
        _, inv = apply(state, event)  # each event on the same fully produced state
        ms = 1000 * (time.perf_counter() - t)
        print(f"{label}: {ms:.0f} ms, bayat {len(inv.stale)}, model çağrısı {inv.llm_calls}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
