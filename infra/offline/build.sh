#!/usr/bin/env bash
# İnternetsiz kurulum paketi (paket 12). İNTERNETE BAĞLI bir makinede, deponun kökünde çalışır;
# yalnızca Docker gerekir (Linux ya da macOS, x86_64 ya da arm64; paket her durumda linux/amd64).
#
#   bash infra/offline/build.sh ÇIKTI_DİZİNİ
#
# Ortam (isteğe bağlı):
#   SKIP_GPU=1        model sunucusu imajını ve büyük modeli atla (yalnızca deneme; kurulamaz)
#   ONLY_MODELS="BAAI/bge-m3"   yalnızca bu modelleri indir (deneme)
#   SPLIT_GB=4        4 GB'tan büyük dosyaları parçala (boyut sınırlı ortamlar için)
#   EXTRA_CA=/yol/ca.pem   kurum vekili TLS'i yeniden imzalıyorsa kök sertifika
#   HF_TOKEN          gerekmez (modeller herkese açık); hız sınırı için verilebilir
#
# Çıktı: images/*.tar, models/hf (Hugging Face önbelleği, sürümü sabit), compose.yaml, config/,
# initdb/, *.sh, KURULUM.md, .env.example, SHA256SUMS. Gizli bilgi içermez.
set -euo pipefail
OUT=${1:?çıktı dizini}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PLATFORM=linux/amd64
HF_HUB_VERSION=0.36.0
cd "$ROOT"
mkdir -p "$OUT/images" "$OUT/models"
OUT=$(cd "$OUT" && pwd)
command -v docker >/dev/null || { echo "docker yok"; exit 1; }

TAG=$(git rev-parse --short=12 HEAD 2>/dev/null || date +%Y%m%d%H%M)
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then TAG="$TAG-yerel"; fi
APP_IMAGE="testmentor-app:$TAG"

echo "== 1/6 uygulama imajı: $APP_IMAGE"
docker build --platform "$PLATFORM" \
  $( [ -n "${EXTRA_CA:-}" ] && echo "--secret id=extra_ca,src=$EXTRA_CA" ) \
  -f infra/app.Dockerfile -t "$APP_IMAGE" .

in_app() {  # uygulama imajının Python'u ve bağımlılıklarıyla, depo bağlı
  docker run --rm --platform "$PLATFORM" -v "$ROOT:/src:ro" -v "$OUT:/out" -w /src \
    -e PYTHONPATH=/src "$APP_IMAGE" python "$@"
}

echo "== 2/6 bildirim"
in_app scripts/offline_manifest.py > "$OUT/manifest.env"
# shellcheck disable=SC1091
. "$OUT/manifest.env"
cat "$OUT/manifest.env"

echo "== 3/6 imajlar"
save() {  # $1 imaj, $2 dosya
  docker image inspect "$1" >/dev/null 2>&1 || docker pull --platform "$PLATFORM" "$1"
  docker save "$1" -o "$OUT/images/$2.tar"
  echo "   $1 -> images/$2.tar ($(du -h "$OUT/images/$2.tar" | cut -f1))"
}
save "$APP_IMAGE" app
for img in $IMAGES; do
  case "$img" in
    *pgvector*) save "$img" postgres ;;
    *)
      if [ -n "${SKIP_GPU:-}" ]; then echo "   atlandı (SKIP_GPU): $img"; continue; fi
      save "$img" "$(echo "$img" | tr '/:' '__')"
      ;;
  esac
done

echo "== 4/6 model ağırlıkları (resmî hesaplar, sabit sürüm)"
SELECTED=""
for m in $MODELS; do
  repo=${m%%@*}
  if [ -n "${ONLY_MODELS:-}" ] && ! echo " $ONLY_MODELS " | grep -q " $repo "; then continue; fi
  if [ -n "${SKIP_GPU:-}" ] && [ -z "${ONLY_MODELS:-}" ]; then continue; fi
  SELECTED="$SELECTED $m"
done
if [ -n "$SELECTED" ]; then
  docker run --rm -i --platform "$PLATFORM" -v "$OUT/models:/models" -e HF_HOME=/models/hf \
    -e HF_TOKEN="${HF_TOKEN:-}" -e SELECTED="$SELECTED" \
    $( [ -n "${EXTRA_CA:-}" ] && echo "-v $EXTRA_CA:/ca.pem:ro -e SSL_CERT_FILE=/ca.pem -e PIP_CERT=/ca.pem -e REQUESTS_CA_BUNDLE=/ca.pem -e CURL_CA_BUNDLE=/ca.pem" ) \
    python:3.12-slim sh -c "pip install -q --root-user-action=ignore huggingface_hub==$HF_HUB_VERSION && python -" <<'PY'
import os, pathlib
from huggingface_hub import snapshot_download

for item in os.environ["SELECTED"].split():
    repo, rev, patterns = item.split("@", 2)
    ignore = [p for p in patterns.split(",") if p] or None
    path = snapshot_download(repo, revision=rev, ignore_patterns=ignore,
                             token=os.environ.get("HF_TOKEN") or None)
    # Offline serving resolves the default branch through refs/main: point it at this commit.
    refs = pathlib.Path(os.environ["HF_HOME"]) / "hub" / f"models--{repo.replace('/', '--')}" / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "main").write_text(rev)
    print(f"   {repo}@{rev[:12]} -> {path}", flush=True)
PY
fi
rm -rf "$OUT/models/hf/xet" 2>/dev/null || true
# The HF cache is symlinks (snapshots -> blobs); FAT/exFAT disks cannot carry them: one tar file.
if [ -d "$OUT/models/hf" ]; then
  tar -C "$OUT/models" -cf "$OUT/models.tar" hf && rm -rf "$OUT/models"
  echo "   models.tar ($(du -h "$OUT/models.tar" | cut -f1))"
fi

echo "== 5/6 Compose, ayarlar, betikler"
in_app scripts/infra_render.py compose-bundle --app-image "$APP_IMAGE" --out /out/compose.yaml
rm -rf "$OUT/config" "$OUT/initdb" && cp -r config "$OUT/config" && cp -r infra/initdb "$OUT/initdb"
cp infra/offline/preflight.sh infra/offline/install.sh infra/offline/verify.sh "$OUT/"
cp infra/offline/KURULUM.md infra/offline/env.example "$OUT/"
mv "$OUT/env.example" "$OUT/.env.example"
mkdir -p "$OUT/data"
echo "APP_IMAGE=$APP_IMAGE" >> "$OUT/manifest.env"
echo "BUILT_AT=$(date -u +%FT%TZ)" >> "$OUT/manifest.env"

echo "== 6/6 sağlama toplamları"
if [ -n "${SPLIT_GB:-}" ]; then
  find "$OUT" -type f -size +"${SPLIT_GB}"G | while read -r f; do
    split -b "${SPLIT_GB}G" -d -a 3 "$f" "$f.part-" && rm "$f"
    echo "   parçalandı: ${f#"$OUT"/}"
  done
fi
(cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | sort -z |
  xargs -0 sh -c 'if command -v sha256sum >/dev/null; then sha256sum "$@"; else shasum -a 256 "$@"; fi' _ \
  > SHA256SUMS)
du -sh "$OUT"
echo "Paket hazır: $OUT  (kurulum: KURULUM.md)"
