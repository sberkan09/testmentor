#!/usr/bin/env bash
# İnternetsiz kurulum (paket 12). Paket dizininde çalışır; hiçbir şey indirmez.
#   bash install.sh          sağlama → imajları yükle → .env → ön denetim → 1. aşama (uygulama,
#                            sahte modelle, ayrı ve geçici) → 2. aşama (model sunucusu ve uygulama)
#   STAGE=1 bash install.sh  yalnızca 1. aşamaya kadar (GPU servisleri açılmaz)
set -euo pipefail
cd "$(dirname "$0")"
. ./manifest.env
COMPOSE=(docker compose -f compose.yaml --env-file .env)

echo "== 1/6 sağlama toplamları"
if command -v sha256sum >/dev/null; then sha256sum -c --quiet SHA256SUMS
else shasum -a 256 -c --quiet SHA256SUMS; fi
echo "   tamam"
for first in $(find . -name '*.part-000' | sort); do  # SPLIT_GB ile parçalanmış dosyalar
  base=${first%.part-000}
  cat "$base".part-* > "$base" && rm "$base".part-*
  echo "   birleştirildi: $base"
done

if [ -f models.tar ] && [ ! -d models/hf ]; then
  echo "   model ağırlıkları açılıyor (models.tar)"
  mkdir -p models && tar -C models -xf models.tar
fi

echo "== 2/6 imajlar"
for f in images/*.tar; do docker load -i "$f" | sed 's/^/   /'; done

echo "== 3/6 .env"
if [ ! -f .env ]; then
  rnd() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
  sed -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(rnd)/" \
      -e "s/^LLM_API_KEY=.*/LLM_API_KEY=$(rnd)/" \
      -e "s/^TESTMENTOR_AUTH_SECRET=.*/TESTMENTOR_AUTH_SECRET=$(rnd)$(rnd)/" .env.example > .env
  chmod 600 .env
  echo "   .env üretildi (rastgele anahtarlarla); yedeklenmeli, depoya ya da e-postaya konmamalı"
else
  echo "   mevcut .env kullanılıyor"
fi

echo "== 4/6 ön denetim"
if [ "${STAGE:-2}" = 1 ]; then SKIP_GPU_CHECK=1 bash preflight.sh; else bash preflight.sh; fi

echo "== 5/6 1. aşama: uygulama ve Postgres, sahte modelle (geçici, ayrı proje adı)"
CHECK=(docker compose -p testmentor-dogrulama -f compose.yaml --env-file .env)
export_check() { TESTMENTOR_FAKE_LLM=1 TESTMENTOR_AUTH_MODE=header APP_PORT=18080 POSTGRES_PORT=15432 \
  TESTMENTOR_DATA_DIR=./data-dogrulama "$@"; }
mkdir -p data-dogrulama
export_check "${CHECK[@]}" --profile harici up -d --wait
if export_check bash verify.sh app testmentor-dogrulama; then
  echo "   1. aşama tamam"
else
  echo "   1. aşama BAŞARISIZ; günlük: docker compose -p testmentor-dogrulama logs app"; exit 1
fi
export_check "${CHECK[@]}" --profile harici down -v >/dev/null 2>&1
rm -rf data-dogrulama
if [ "${STAGE:-2}" = 1 ]; then echo "STAGE=1: GPU servisleri açılmadı."; exit 0; fi

echo "== 6/6 2. aşama: model sunucusu ($ENGINE), embedding, Postgres, uygulama"
echo "   model yüklemesi 5-15 dakika sürebilir"
"${COMPOSE[@]}" --profile "$ENGINE" up -d --wait --wait-timeout 1800
bash verify.sh full testmentor
echo
echo "Kurulum tamam. İlk kullanıcı:  docker compose -f compose.yaml --env-file .env exec app python -m api.users add AD"
echo "Adres: http://<sunucu>:${APP_PORT:-8080}"
