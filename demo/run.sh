#!/usr/bin/env bash
# Demo: Runpod pod'unda gerçek model, bu makinede uygulama (API + derlenmiş ön yüz, bellek içi
# depo, parolalı giriş). Pod `make up` ile bekçili açılır; betik nasıl biterse bitsin (Ctrl-C,
# hata) `make down` çalışır; bekçi ayrıca HOURS dolunca pod'u siler.
#
#   bash demo/run.sh live   [ÇIKTI_DİZİNİ]   canlı demo: proje ve belgeler hazır yüklenir,
#                                            adres ve parola yazılır, Ctrl-C ile biter
#   bash demo/run.sh record  ÇIKTI_DİZİNİ    demo videosu: Playwright senaryosu ekran akışı kaydeder,
#                                            sonra demo/make_video.py MP4 üretir
#
# Ortam: HOURS (bekçinin en uzun ömrü, varsayılan live 2, record 1), PORT (varsayılan 8080),
# DEMO_PASSWORD (yoksa rastgele üretilir). `.env` içinde Runpod ve model anahtarları olmalı.
set -euo pipefail
MODE=${1:?"kip: live | record"}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${2:-$(mktemp -d)}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
PORT=${PORT:-8080}
case "$MODE" in
  live) HOURS=${HOURS:-2} ;;
  record) HOURS=${HOURS:-1} ;;
  *) echo "kip: live | record"; exit 2 ;;
esac
cd "$ROOT"

API_PID=""
cleanup() {
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null || true
  make -C "$ROOT" down
}
trap cleanup EXIT
trap 'exit 130' INT TERM

if [ ! -f web/dist/index.html ]; then
  (cd web && npm ci --no-audit --no-fund && npm run build)
fi

make -C "$ROOT" up MAX_HOURS="$HOURS"
set -a; [ -f .env ] && . ./.env; set +a
eval "$(uv run python demo/pod_env.py)"

export TESTMENTOR_STORE=memory TESTMENTOR_AUTH_MODE=password
export TESTMENTOR_USERS_FILE="$OUT/users.yaml"
export TESTMENTOR_AUTH_SECRET=${TESTMENTOR_AUTH_SECRET:-$(uv run python -c "import secrets; print(secrets.token_hex(32))")}
DEMO_PASSWORD=${DEMO_PASSWORD:-$(uv run python -c "import secrets; print(secrets.token_urlsafe(9))")}
printf '%s\n' "$DEMO_PASSWORD" | uv run python -m api.users add ayse >/dev/null

uv run uvicorn api.main:app --host 127.0.0.1 --port "$PORT" >"$OUT/api.log" 2>&1 &
API_PID=$!
for _ in $(seq 1 60); do curl -sf "http://127.0.0.1:$PORT/auth/config" >/dev/null && break; sleep 2; done
curl -sf "http://127.0.0.1:$PORT/auth/config" >/dev/null || { echo "API açılmadı"; tail -30 "$OUT/api.log"; exit 1; }

if [ "$MODE" = live ]; then
  uv run python demo/preload.py "http://127.0.0.1:$PORT" ayse "$DEMO_PASSWORD"
  echo
  echo "Demo hazır: http://127.0.0.1:$PORT  kullanıcı: ayse  parola: $DEMO_PASSWORD"
  echo "Pod en geç $HOURS saat içinde kendini siler; bitirmek için Ctrl-C (pod silinir)."
  echo "Süre yetmezse başka bir terminalde: make extend HOURS=1"
  wait "$API_PID"
else
  (cd web && E2E_BASE_URL="http://127.0.0.1:$PORT" E2E_PASSWORD="$DEMO_PASSWORD" DEMO=1 \
    DEMO_FRAMES="$OUT/frames" DEMO_MARKS="$OUT/marks.json" \
    npx playwright test e2e/demo.spec.ts --trace off 2>&1 | tee "$OUT/demo.log")
  uv run python demo/make_video.py "$OUT/frames" "$OUT/marks.json" "$OUT/demo.mp4"
fi
