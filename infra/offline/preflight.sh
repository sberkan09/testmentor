#!/usr/bin/env bash
# Ön denetim (paket 12): kurum makinesi paketi çalıştırabilir mi? Hiçbir şey değiştirmez.
#   bash preflight.sh            (imajlar yüklendikten sonra GPU'yu kapsayıcı içinden de dener)
set -uo pipefail
cd "$(dirname "$0")"
. ./manifest.env
FAIL=0
ok() { echo "  [tamam] $*"; }
bad() { echo "  [EKSİK] $*"; FAIL=1; }
warn() { echo "  [uyarı] $*"; }

echo "== Docker"
if docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
  ok "Docker sunucusu $(docker version --format '{{.Server.Version}}')"
else
  bad "Docker çalışmıyor ya da bu kullanıcının yetkisi yok (docker version)"
fi
if docker compose version >/dev/null 2>&1; then ok "$(docker compose version | head -1)"
else bad "Docker Compose eklentisi yok (docker compose version)"; fi
case "$(uname -m)" in
  x86_64|amd64) ok "işlemci mimarisi $(uname -m)" ;;
  *) bad "işlemci mimarisi $(uname -m): paket linux/amd64 içindir" ;;
esac

echo "== GPU"
if [ -n "${SKIP_GPU_CHECK:-}" ]; then
  warn "GPU denetimi atlandı (SKIP_GPU_CHECK)"
elif command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | while read -r l; do ok "GPU: $l"; done
  ok "sürücünün desteklediği CUDA: $(nvidia-smi | grep -o 'CUDA Version: [0-9.]*' | head -1)"
  MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | tr -dc 0-9)
  NEED=$(( (MODEL_GB + 20) * 1024 ))
  if [ "${MEM:-0}" -lt "$NEED" ]; then
    warn "GPU belleği ${MEM} MiB; ${MODEL} için önerilen en az ~$((NEED / 1024)) GB (ağırlık + önbellek)."
    warn ".env içinde LLM_MAX_MODEL_LEN ve LLM_MAX_NUM_SEQS küçültülebilir (KURULUM.md)."
  fi
  ENGINE_IMAGE=$(for i in $IMAGES; do case "$i" in *pgvector*) ;; *) echo "$i";; esac; done | head -1)
  if docker image inspect "$ENGINE_IMAGE" >/dev/null 2>&1; then
    if docker run --rm --gpus all --entrypoint nvidia-smi "$ENGINE_IMAGE" -L >/dev/null 2>&1; then
      ok "kapsayıcı GPU'yu görüyor ($ENGINE_IMAGE, --gpus all)"
    else
      bad "kapsayıcı GPU'yu göremiyor: NVIDIA Container Toolkit kurulu ve Docker'a tanıtılmış mı? (nvidia-ctk runtime configure)"
    fi
  else
    warn "model sunucusu imajı henüz yüklenmemiş; kapsayıcı denetimi kurulumdan sonra (install.sh tekrar çağırır)"
  fi
else
  bad "nvidia-smi yok: NVIDIA sürücüsü kurulu değil"
fi

echo "== Disk ve portlar"
AVAIL=$(df -Pk . | awk 'NR==2 {print int($4/1024/1024)}')
ok "bu dizinde boş alan ${AVAIL} GB (imajlar yüklenince Docker'ın veri dizininde de yer gerekir)"
for p in "${APP_PORT:-8080}" "${POSTGRES_PORT:-5432}"; do
  if (exec 3<>/dev/tcp/127.0.0.1/"$p") 2>/dev/null; then
    warn "port $p kullanımda: .env içinde APP_PORT / POSTGRES_PORT değiştir"
  else ok "port $p boş"; fi
done

if [ "$FAIL" -ne 0 ]; then echo "Ön denetim: EKSİK var (yukarıda)."; exit 1; fi
echo "Ön denetim: tamam."
