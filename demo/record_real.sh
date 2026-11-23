#!/usr/bin/env bash
# Demo videosunu gerçek modelle kaydeder: pod aç → API (pod'a bağlı, bellek içi depo) → duman testi
# → Playwright demo senaryosu (ekran akışı kareleri) → pod sil. `make down` her durumda çalışır
# (trap); pod'un bekçisi ayrıca MAX_HOURS dolunca kendini siler.
#
#   bash demo/record_real.sh ÇIKTI_DİZİNİ
set -euo pipefail
OUT=${1:?çıktı dizini}
mkdir -p "$OUT"
cd "$(dirname "$0")/.."
API_PID=""
cleanup() {
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null || true
  pkill -f "vite preview" 2>/dev/null || true
  make down
}
trap cleanup EXIT

make up MAX_HOURS=1
set -a; [ -f .env ] && . ./.env; set +a
eval "$(uv run python demo/pod_env.py)"

TESTMENTOR_STORE=memory uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 >"$OUT/api.log" 2>&1 &
API_PID=$!
for _ in $(seq 1 60); do curl -sf http://127.0.0.1:8000/projects >/dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:8000/projects >/dev/null || { echo "API açılmadı"; tail -30 "$OUT/api.log"; exit 1; }

# Duman testi: 8 gereksinimlik küçük set, üretim bitene kadar.
uv run python - "$OUT" <<'PY'
import csv, io, json, sys, time
import httpx
from eval.golden import load_golden
p = load_golden().projects[0]
buf = io.StringIO(); w = csv.writer(buf); w.writerow(["id", "language", "text"])
for r in p.requirements: w.writerow([r.id, r.language, r.text])
meta = {"name": "Duman", "key": "SMOKE", "mapping": {"text": "text", "id": "id", "language": "language"}}
c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=120)
r = c.post("/projects", data={"meta": json.dumps(meta)}, files={"file": ("s.csv", buf.getvalue().encode(), "text/csv")}, headers={"X-User": "duman"})
r.raise_for_status()
for _ in range(180):
    s = c.get("/projects/SMOKE/snapshot").json()
    busy = any(g["stale"] + g["running"] for g in s["stages"]) or s["jobs"]
    if not busy: break
    time.sleep(2)
cases = [n for n in s["nodes"] if n["ref"]["kind"] == "test_case"]
failed = [n["ref"] for n in s["nodes"] if n["status"] == "failed"]
print(f"duman: {len(cases)} test durumu, başarısız {failed}")
if busy or not cases or failed: sys.exit("duman testi geçmedi")
PY

cd web
DEMO=1 DEMO_FRAMES="$OUT/frames" DEMO_MARKS="$OUT/marks.json" \
  npx playwright test e2e/demo.spec.ts --trace off 2>&1 | tee "$OUT/demo.log"
