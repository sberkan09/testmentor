# Pilot kurulum el kitabı

Paket 10, 23 Kasım 2026. testmentor'ın kurumun kendi sunucusuna Docker Compose ile kurulması. Kurum verisi Runpod'a ve bu depoya girmez; pilot yalnızca kurumun sunucusunda çalışır.

## Ne kurulur

`infra/compose.yaml`, `config/` altından `make compose` ile üretilir; elle düzenlenmez. Dört servis:

| Servis | İmaj | Görev | Profil |
| --- | --- | --- | --- |
| `vllm` ya da `sglang` | model sunucusu | metin üretimi (GPU) | `vllm`, `sglang` |
| `embedding` | vLLM, BGE-M3 | vektörler (GPU) | `vllm`, `sglang` |
| `postgres` | `pgvector/pgvector:0.8.7-pg18` | proje durumu, olay günlüğü, bilgi havuzu indeksi | hepsi |
| `app` | `testmentor-app:local` (`infra/app.Dockerfile`) | API ve derlenmiş ön yüz (tek adres) | hepsi |

İki kurulum biçimi var:

- **Tek sunucu** (`PROFILE=vllm`, varsayılan): model, embedding, Postgres ve uygulama aynı GPU sunucusunda.
- **Ayrı GPU sunucusu** (`PROFILE=harici`): bu makinede yalnızca Postgres ve uygulama çalışır; model ve embedding kurumun başka bir sunucusundadır, adresleri `.env` içindedir.

Uygulama portu varsayılan olarak 8080'dir (`APP_PORT`; 8000 vLLM'indir). Kullanıcılar tarayıcıdan `http://<sunucu>:8080` adresine girer.

## Gereksinimler

- Linux, Docker Engine 24 ya da üstü, Docker Compose v2 (`docker compose version`).
- Tek sunucu biçiminde: NVIDIA sürücüsü ve NVIDIA Container Toolkit; GPU belleği seçilen modele yetmeli (`config/models.yaml`, `config/infra.yaml` → `gpu_memory`). Model ağırlıkları için disk (`config/models.yaml` → `approx_size_gb`).
- İmajı derlemek için npm ve PyPI erişimi (bir kez; derlenmiş imaj başka makineye `docker save` / `docker load` ile taşınabilir).
- Ayrı GPU sunucusu biçiminde: o sunucuda OpenAI uyumlu bir model uç noktası ve embedding uç noktası (aynı model ve embedding modeli; embedding boyutu `config/runtime.yaml` → `embedding.dim`, BGE-M3 için 1024).

## Kurulum

### 1. Depo ve `.env`

Depoyu sunucuya alın. Kökte `.env` dosyası oluşturun (depoya girmez):

```bash
# Zorunlu
POSTGRES_PASSWORD=...        # yalnızca harf ve rakam: openssl rand -hex 24
LLM_API_KEY=...              # model ve embedding sunucusunun API anahtarı
TESTMENTOR_AUTH_SECRET=...   # jeton imza anahtarı, en az 32 karakter: openssl rand -hex 32

# İsteğe bağlı
APP_PORT=8080                # uygulamanın dış portu
POSTGRES_PORT=5432           # Postgres'in dış portu (yedek araçları için; dışarı açmayın)
TESTMENTOR_DATA_DIR=../data  # users.yaml'ın durduğu klasör (infra/ klasörüne göre)
MODELS_DIR=./models          # model ağırlıkları (tek sunucu biçiminde; infra/ klasörüne göre)

# Yalnızca PROFILE=harici
LLM_BASE_URL=http://gpu-sunucu.kurum:8000/v1
EMBEDDING_BASE_URL=http://gpu-sunucu.kurum:8001/v1
LLM_ENGINE=vllm              # uzak sunucunun motoru (istek alanları buna göre): vllm | sglang
LLM_MODEL=qwen3.8-27b        # config/models.yaml anahtarı; uzak sunucu aynı adla sunmalı
```

`POSTGRES_PASSWORD` bağlantı adresine (`postgresql://...`) yazılır; `@`, `/`, `:` gibi karakterler adresi bozar, bu yüzden onaltılık değer kullanın.

### 2. Uygulama imajı

```bash
make app-image                       # docker build -f infra/app.Dockerfile -t testmentor-app:local .
make app-image EXTRA_CA=/yol/kurum-ca.pem   # kurum ağı TLS'i yeniden imzalıyorsa
```

Kurum vekilinin kök sertifikası derlemeye gizli olarak verilir (`--secret`), imaja girmez. İmaj yoksa `make local-up` da derler, ama vekil sertifikası gerekiyorsa önce `make app-image` çalıştırın.

### 3. Model ağırlıkları (yalnızca tek sunucu biçimi)

Ağırlıklar `MODELS_DIR/hf` altında Hugging Face önbelleği olarak durur ve servisler çevrimdışı açılır (`HF_HUB_OFFLINE=1`). Ağırlıkları yalnızca modelin resmî kuruluş hesabından indirin (`config/models.yaml` → `repo_id`); benzer adlı depolar vardır. İlk açılışta indirmeye izin vermek için bir kez `HF_HUB_OFFLINE=0 make local-up` çalıştırılabilir; kapalı ağda ağırlıkları başka makinede indirip klasörü kopyalayın.

### 4. Başlatma

```bash
make local-up                  # tek sunucu, vLLM (PROFILE=vllm)
make local-up PROFILE=sglang   # tek sunucu, SGLang
make local-up PROFILE=harici   # yalnızca Postgres ve uygulama
docker compose -f infra/compose.yaml --env-file .env --profile harici ps
```

`--wait` servisler sağlıklı olana kadar bekler. Model sunucusunun ilk açılışı (ağırlık yükleme) 10 dakikayı bulabilir; uygulama ondan önce açılır. Model hazır olmadan başlayan üretim işleri başarısız olabilir; denetçideki "Yeniden dene" ile yeniden başlatılır.

Kontrol: `curl http://localhost:8080/auth/config` → `{"mode":"password"}`.

### 5. Kullanıcı ekleme

Pilotta giriş parolalıdır (`TESTMENTOR_AUTH_MODE=password`, Compose varsayılanı). Kullanıcılar `TESTMENTOR_DATA_DIR/users.yaml` dosyasında scrypt özetiyle durur; parolanın kendisi hiçbir yere yazılmaz.

```bash
make users-add NAME=ayse PROFILE=harici      # parolayı iki kez sorar (en az 8 karakter)
docker compose -f infra/compose.yaml --env-file .env --profile harici exec app python -m api.users list
docker compose -f infra/compose.yaml --env-file .env --profile harici exec app python -m api.users remove ayse
```

Aynı adla yeniden eklemek parolayı değiştirir. Dosya her girişte yeniden okunur; uygulamayı yeniden başlatmak gerekmez. Proje bazlı yetki yoktur: giriş yapan her kullanıcı tüm projeleri görür. Jeton 12 saat geçerlidir (`config/runtime.yaml` → `auth.token_hours`); `TESTMENTOR_AUTH_SECRET` değişirse herkes yeniden giriş yapar.

### 6. İlk kullanım

1. Tarayıcıdan giriş yapın, "Gereksinim seti yükle" ile csv ya da xlsx yükleyin.
2. Proje içinde **Belgeler** sekmesinden şartname, mevzuat ya da standart metnini yükleyin (.txt, .md ya da metin katmanlı .pdf; taranmış PDF reddedilir). Belge parçalanır ve embed edilir; her öbeğin arama düğümü yeniden denetlenir, bulunan parçalar öbek denetçisinde "Bilgi havuzundan parçalar" altında görünür ve test setleri bu parçalarla yeniden üretilir.
3. Aynı adlı dosyayı yeniden yüklemek belgeyi değiştirir; metin aynıysa test setleri bayatlamaz.

## Yedekleme ve geri yükleme

Durumun tamamı Postgres'tedir (projeler, düğümler, olay günlüğü, bilgi havuzu); ayrıca `users.yaml` yedeklenir.

```bash
C="docker compose -f infra/compose.yaml --env-file .env --profile harici"
$C exec -T postgres pg_dump -U testmentor -d testmentor -Fc > yedek-$(date +%F).dump
cp data/users.yaml yedek-users-$(date +%F).yaml

# Geri yükleme (uygulama durdurulur, veritabanı boş olmalı)
$C stop app
$C exec -T postgres pg_restore -U testmentor -d testmentor --clean --if-exists < yedek-2026-11-23.dump
$C start app
```

Veri `pgdata` adlı Docker biriminde durur. `make local-down` birimi silmez; `docker compose ... down -v` siler, kullanmayın.

## Güncelleme

```bash
git pull
make app-image
make local-up PROFILE=...      # yalnızca değişen servisler yeniden başlar
```

Ayar değişikliği (`config/`) imaja girer; ayar değişince `make compose`, `make app-image` ve `make local-up` sırasıyla çalıştırılır. Aşama ayarları değişen projelerde değişiklik onay ister (aşama çubuğu).

## Sorun giderme

| Belirti | Neden ve çözüm |
| --- | --- |
| `app` sağlıklı olmuyor, günlükte `TESTMENTOR_AUTH_SECRET is missing or shorter than 32 characters` | `.env` içinde anahtar yok ya da kısa; `openssl rand -hex 32` |
| Günlükte `kb_chunks.embedding has dimension 48, the embedding model gives 1024` | Veritabanı önce başka bir embedding modeliyle (örneğin sahte modelle deneme) kurulmuş. Bilgi havuzu yeni boyutla yeniden kurulmalı: deneme veritabanıysa birimi silip yeniden başlatın; değilse `kb_chunks`, `kb_documents`, `kb_versions` tablolarını silip belgeleri yeniden yükleyin. |
| Giriş ekranında "Kullanıcı adı ya da parola yanlış" | Kullanıcı yok ya da parola yanlış: `api.users list`, gerekirse `api.users add` ile parolayı yenileyin |
| Her istekte giriş ekranına dönüyor | Jeton süresi doldu ya da `TESTMENTOR_AUTH_SECRET` değişti; yeniden giriş yapın |
| Test durumları "Üretim başarısız" | Model sunucusuna ulaşılamıyor: `docker compose ... logs app` ve model sunucusunun `/health` adresi; `harici` biçiminde `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_ENGINE`, `LLM_MODEL` |
| Belge yüklemesi "dosyada metin yok" | Taranmış PDF; metin katmanlı PDF ya da .txt/.md yükleyin |
| İmaj derlemesinde `self-signed certificate in certificate chain` | Kurum vekili TLS'i yeniden imzalıyor: `make app-image EXTRA_CA=/yol/kurum-ca.pem` |
| Port çakışması | `APP_PORT`, `POSTGRES_PORT` ile değiştirin |

Günlükler: `docker compose -f infra/compose.yaml --env-file .env --profile <profil> logs -f app`.

## Güvenlik notları

- Uygulama şirket içi ağa açılır. HTTPS gerekiyorsa önüne kurumun ters vekili (nginx, Caddy) konur; uygulama `--proxy-headers` ile çalışır.
- Postgres portunu dışarı açmayın; yedek için `docker compose exec` yeterlidir.
- `.env` ve `data/users.yaml` depoya girmez (`.gitignore`, `.dockerignore`).
- Uygulama kapsayıcısı root kullanıcısıyla çalışır (bağlanan `data/` klasörüne kullanıcı ekleme aracının yazabilmesi için); kurum politikası gerektirirse `user:` ile değiştirilip klasör sahipliği ayarlanır.
- `harici` profili bir Runpod pod'una da bağlanabilir, ama yalnızca sentetik veri ve altın setle test için: kurum verisi Runpod'a girmez.

## Doğrulama durumu (23 Kasım 2026)

Bu depoda (GPU'suz geliştirme ortamı) doğrulanan: `harici` profili sahte modelle (`TESTMENTOR_FAKE_LLM=1`) ve pgvector'lü Postgres'le kuruldu; Playwright testleri (yükleme, öbekler, düzenleme, matris ve xlsx, iki kullanıcı ve kilit, belge yükleme ve arama düğümü, parolalı giriş) derlenmiş uygulamaya karşı geçti; uygulama yeniden başlatıldıktan sonra projeler ve belge listesi Postgres'ten geldi. Doğrulanamayan: `vllm`, `sglang` ve `embedding` servisleri (GPU yok, imajlar çok büyük); tek sunucu biçimi ve gerçek modelle `harici` biçimi pilot sunucusunda ilk kurulumda denenmelidir: `make local-up`, `make users-add`, küçük bir gereksinim seti ve bir belge.
