# testmentor: internetsiz kurulum

Bu paket internete bağlı bir makinede üretildi (`infra/offline/build.sh`). Kurum sunucusunda hiçbir şey indirilmez; her şey bu dizindedir:

- `images/`: Docker imajları (`docker save`, `linux/amd64`).
- `models/hf`: model ağırlıkları, Hugging Face önbelleği biçiminde ve sürümü sabit (`manifest.env`).
- `compose.yaml`: servisler. Hiçbir imaj çekilmez (`pull_policy: never`).
- `config/`: uygulama ayarları; kapsayıcıya salt okunur bağlanır.
- `preflight.sh`, `install.sh`, `verify.sh`, `SHA256SUMS`.

Paket gizli bilgi içermez. Anahtarlar kurulumda üretilir ve `.env` dosyasına yazılır.

## Sunucuda önceden kurulu olması gerekenler

Bunlar paketin dışındadır ve kurumun BT ekibince kurulur:

1. x86_64 Linux.
2. Docker Engine ve Docker Compose eklentisi (`docker compose version`).
3. NVIDIA sürücüsü (`nvidia-smi` çalışmalı). Model sunucusu imajının istediği CUDA sürümünü desteklemelidir; `preflight.sh` imajın içinden `nvidia-smi` çalıştırarak bunu dener.
4. NVIDIA Container Toolkit, Docker'a tanıtılmış olarak (`nvidia-ctk runtime configure --runtime=docker`, ardından Docker'ı yeniden başlatma).
5. Boş alan: paketin kendisi ve Docker'ın veri dizininde bir o kadar daha.

GPU belleği: varsayılan model (Qwen3.8-27B, FP8) ve embedding modeli birlikte tek GPU'da, 96 GB'lık RTX PRO 6000 Blackwell üzerinde ölçüldü. Daha az bellekte `.env` içinde `LLM_MAX_MODEL_LEN` (bağlam uzunluğu) ve `LLM_MAX_NUM_SEQS` (eşzamanlı istek) küçültülür. 48 GB altında bu model önerilmez.

## Kurulum

```bash
# paketi sunucuda bir dizine kopyala, sonra:
cd testmentor-offline
bash preflight.sh      # isteğe bağlı: eksikleri listeler, hiçbir şeyi değiştirmez
bash install.sh
```

`install.sh` sırasıyla şunları yapar ve bir adım başarısız olursa açık bir hatayla durur:

1. **Sağlama toplamları:** bozuk ya da eksik dosya varsa durur. Parçalanmış dosyaları birleştirir.
2. **İmajlar:** `docker load`.
3. **`.env`:** yoksa rastgele anahtarlarla üretir.
4. **Ön denetim:** Docker, Compose, mimari, GPU, kapsayıcı içinden GPU, portlar.
5. **1. aşama:** uygulama ve Postgres sahte modelle, geçici ve ayrı bir proje adıyla açılır (portlar 18080 ve 15432). Küçük bir proje uçtan uca üretilir, ardından bu geçici kurulum silinir. GPU gerekmez.
6. **2. aşama:** model sunucusu, embedding, Postgres ve uygulama açılır (model yüklemesi 5–15 dakika). `verify.sh` model listesini, bir sohbet isteğini ve bir embedding isteğini dener.

GPU henüz hazır değilse yalnızca uygulama doğrulanabilir: `STAGE=1 bash install.sh`.

İlk kullanıcı:

```bash
docker compose -f compose.yaml --env-file .env exec app python -m api.users add ayse
```

Adres: `http://<sunucu>:8080` (`APP_PORT`).

## Günlük işletim

- **Durum:** `docker compose -f compose.yaml --env-file .env ps`.
- **Günlükler:** `... logs -f app` (ya da `vllm`, `embedding`, `postgres`).
- **Doğrulama:** `bash verify.sh full`.
- **Ağ denetimi:** `bash verify.sh egress` kapsayıcıdan dışarıya erişim olmadığını gösterir.
- **Durdurma / başlatma:** `docker compose -f compose.yaml --env-file .env --profile vllm down` / `up -d`. Veriler `pgdata` biriminde ve `data/` dizininde kalır.
- **Yedek:** `docker compose ... exec postgres pg_dump -U testmentor -Fc testmentor > yedek.dump`. Bunun yanında `data/` (kullanıcı dosyası) ve `.env` de yedeklenir.
- **Ayar değişikliği:** `config/` altındaki dosyalar düzenlenir, ardından `docker compose ... restart app`.

## Güncelleme

Yeni bir paket yalnızca değişen bileşeni taşıyabilir, çoğunlukla `images/app.tar`, `compose.yaml` ve `config/`. Sırasıyla:

1. `docker load -i images/app.tar`.
2. `manifest.env` içindeki `APP_IMAGE` ile `compose.yaml` güncellenir.
3. `docker compose ... up -d app`.

`.env` ve `data/` korunur.

## Sorun giderme

| Belirti | Neden ve çözüm |
| --- | --- |
| `install.sh` sağlamada duruyor | Kopyalama eksik ya da bozuk; ilgili dosyayı yeniden taşı |
| ön denetim: "kapsayıcı GPU'yu göremiyor" | NVIDIA Container Toolkit kurulu değil ya da Docker'a tanıtılmamış |
| model sunucusu "out of memory" ile duruyor | GPU belleği yetmiyor: `.env` içinde `LLM_MAX_MODEL_LEN` ve `LLM_MAX_NUM_SEQS` küçült, `LLM_GPU_MEMORY_UTILIZATION` ayarla |
| model sunucusu dosya bulamıyor | `models/hf` eksik kopyalanmış; sağlama toplamlarını yeniden çalıştır |
| uygulama açılıyor, üretim başlamıyor | `bash verify.sh full`; model sunucusu günlüğü: `logs vllm` |
