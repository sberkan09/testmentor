# Paket 10 planı: pilot hazırlığı

23 Kasım 2026. Model: Opus. Kullanıcı talimatı: PoC sonrası pilot hazırlığı, D10/reranker ve paket 9 birlikte. Tasarım: `docs/tasarim.md` (İndeks, API Kurallar, Bileşenler, paket tablosu satır 10).

## Neden

Kurum verisi Runpod'a giremez; pilot kurumun kendi GPU sunucusunda, Compose ile kurulur. PoC'de üç eksik vardı:

1. Sunucu (`api/main.py`) bilgi havuzunu hiç bağlamıyordu: `OrchestratorService.from_config` `tools=` almadan kuruluyor, arayüzden belge yüklenemiyor. Demo dahil sunucuda parça getirme kapalıydı (D9'un +0,073'ü üründe yoktu).
2. Kullanıcı girişi yok (`X-User` başlığı).
3. Compose'ta uygulama servisi yok (yalnızca model sunucusu, embedding, Postgres); `PgIndex` pgvector'le hiç koşmadı.

## Kapsam (bu sırayla; hepsi `api/app.py`, `api/schema.json` ve web istemcisine dokunduğu için tek kol, sıralı)

### 1. Sunucuda bilgi havuzu

- `api/main.build_service`: proje başına indeks, depo türüne göre: Postgres deposunda `services/kb_index_pg.PgIndex` (aynı DSN, `ensure_schema`), bellek içi depoda `InMemoryIndex`. `tools=lambda pid: ProjectTools(...)` `services.kb_retrieve` ile (`build_retrieval`, `make_select_examples`, `make_example_source`). Örnek havuzu bağlanır ama `kb.examples: 0` olduğu sürece prompt değişmez.
- `POST /projects/{id}/kb/documents` (multipart dosya): düz metin, Markdown, metin katmanlı PDF (`pypdf`, yeni bağımlılık). Parçalama `core/kb/chunking.py`, embed `deps.embed`, indekse yaz, `service.kb_document_added(...)`. `GET /projects/{id}/kb/documents`: belge kimliği, adı, parça sayısı. `DELETE` isteğe bağlı.
- Sözleşme (`worker/contracts.py`, `Snapshot`) dondurulmuştur: belge listesi snapshot'a girmez, ayrı uç noktadır. `api/schema.json` yeniden üretilir.
- Ön yüz: proje içinde "Belgeler" paneli (liste ve yükleme). Yükleme sonrası etkilenen setler olay akışıyla bayatlar ve yeniden üretilir.
- `services/kb_examples.py` ve `eval/` paket 11'indir; bu kol onları değiştirmez, yalnızca çağırır.

### 2. Kullanıcı girişi

- `config/runtime.yaml` `auth:` bloğu: `mode: header | password` (varsayılan `header`; 475 test geçerli kalır), `users_file` (varsayılan `data/users.yaml`, git dışı), `token_hours`.
- `python -m api.users add AD` (parola stdin ya da getpass ile; scrypt, `hashlib`). Gizli anahtar `.env` içinde `TESTMENTOR_AUTH_SECRET`; jeton HMAC-SHA256 imzalı, süreli.
- `GET /auth/config` → `{mode}`; `POST /auth/login` → `{token, user}`. `password` kipinde `/projects*` jeton ister (REST `Authorization: Bearer`, WebSocket `?token=`); komutun sahibi jetondaki kullanıcıdır, `X-User` yok sayılır.
- Ön yüz: giriş formu kip `password` ise parola alanı gösterir; jeton `sessionStorage`'da; 401'de giriş ekranına döner.

### 3. Dağıtım

- `infra/app.Dockerfile`: çok aşamalı (Node ile `web/dist`, sonra Python + `uv sync --frozen --no-dev`), `uvicorn api.main:app`.
- `scripts/infra_render.py` + `config/infra.yaml`: compose'a `app` servisi (Postgres'e `TESTMENTOR_PG_DSN`, model ve embedding adresleri varsayılan olarak compose içindeki servisler). Yeni profil `harici`: yalnızca Postgres ve uygulama; model ve embedding adresi `.env`'den (kurumun ayrı GPU sunucusu ya da test için Runpod pod'u). `make compose` ile üretilir, elle düzenlenmez.
- `TESTMENTOR_FAKE_LLM=1` Postgres deposunu zorla kapatmasın: DSN varsa sahte model + Postgres (Compose doğrulaması için).
- `docs/pilot.md`: kurulum el kitabı (gereksinimler, `.env`, kullanıcı ekleme, `make local-up`, yedekleme, sorun giderme).

## Bitti ölçütü

- `PgIndex` ve depo testleri pgvector'lü Postgres'e karşı geçiyor (`pgvector/pgvector:0.8.7-pg18` kapsayıcısı, `TESTMENTOR_PG_DSN`). Yalıtım testi pgvector'le de geçiyor.
- Compose ile (`harici` profili, sahte model, Postgres) kurulan uygulamaya karşı Playwright testleri geçiyor: mevcut e2e, belge yükleme (yüklemeden sonra arama düğümünde parça kimliği) ve parolalı giriş.
- `make test`, `make lint`, web `tsc`/lint/vitest temiz.

## Kurallar

- Ücretli kaynak, Runpod ve hakem yok. `vllm`, `sglang`, `embedding` imajları yerelde çekilmez ve başlatılmaz (GPU yok, imajlar çok büyük). Compose'un GPU servisleri burada doğrulanamaz; raporda açıkça yazılır.
- Docker daemon kapalıysa `dockerd` arka planda başlatılır. Portlar: uygulama 18000, Postgres 55433 (paket 9 kolu Vite için 5180 civarını kullanır).

## Uygulamada netleşenler

Kol G, 23 Kasım 2026. Tasarımdan sapma yok; aşağıdakiler tasarımın açık bıraktığı ayrıntılar.

### Bilgi havuzu

- `api/main.build_server()` sunucunun tek kurulum yeridir: depo, indeks, örnek havuzu, `tools=` ve yükleme işleyicisi (`services/kb_documents.KbDocuments`). `build_service()` geriye uyumluluk için kaldı (`build_server().service`).
- `PgIndex` deponun bağlantısını paylaşmaz, aynı DSN'e kendi autocommit bağlantısını açar. Vektör boyutu ayardadır (`config/runtime.yaml` → `embedding.dim: 1024`; sahte modelde `FakeEmbed().dim` = 48). `ensure_schema` mevcut tablonun boyutunu denetler ve farklıysa açık bir hatayla durur (aynı veritabanı önce sahte modelle kurulduysa).
- `KbIndex` arayüzüne `documents(project_id)` (belge → parça sayısı) eklendi; belge listesi indeksten gelir, böylece Postgres'te yeniden başlatmadan sonra da doğrudur. Özgün dosya adı, ekleyen ve zaman ayrı küçük bir kayıtta (`kb_documents` tablosu ya da bellek içi sözlük).
- Belge kimliği dosya adının güvenli halidir (`[\w.-]`, `#` ve `@` yok). Aynı dosya yeniden yüklenince belge değişir, metin aynıysa parça kimlikleri aynı kalır ve test setleri bayatlamaz.
- Metinsiz dosya (taranmış PDF, boş metin) 422 ile reddedilir; desteklenmeyen tür ve boyut sınırı `config/runtime.yaml` → `kb_upload` (`KbSettings`'e girmedi: o ayarlar arama aşamasının hash'ine girer, yükleme sınırı girmemeli). PDF okuma iş parçacığında, indeks ve orkestratör çağrıları olay döngüsünde.
- `DELETE /projects/{id}/kb/documents/{belge}` de yazıldı. Kaldırma da `KbDocumentAdded` olayıyla bildirilir (olayın adı "eklendi" ama anlamı "indeks sürümü değişti"; arama düğümleri yeniden denetlenir); sözleşme dondurulduğu için yeni olay türü eklenmedi.
- Ön yüz: "Belgeler" sekmesi; liste `kb_index` düğümünün sürümü değişince yeniden okunur (başka kullanıcının yüklemesi de görünür). Öbek denetçisinde "Bilgi havuzundan parçalar" bölümü arama düğümünün parça kimliklerini gösterir (`<belge>#<sıra>`).
- Sahte modelin test seti cevabı parçalara bakmaz, ama parça kimlikleri test setinin girdi hash'ine girdiği için yüklemeden sonra her test seti yeniden üretilir (sürüm artar); uçtan uca testler bunu denetler.

### Kullanıcı girişi

- `api/auth.py`: scrypt (n=2^14, r=8, p=1), jeton `base64url(json{u, exp}).base64url(HMAC-SHA256)`. Gizli anahtar en az 32 karakter, yoksa parolalı kipte sunucu açılmaz. Bilinmeyen kullanıcıda da sahte bir özet denetlenir (süre farkı kullanıcı varlığını sızdırmasın); scrypt `asyncio.to_thread` ile.
- Jeton sorgu parametresiyle yalnızca WebSocket'te ve `matrix.xlsx` bağlantısında kabul edilir (düz bağlantı başlık gönderemez); diğer REST istekleri `Authorization: Bearer` ister. WebSocket geçersiz jetonda 4401 ile kapanır, istemci yeniden bağlanmayı bırakıp giriş ekranına döner.
- `TESTMENTOR_AUTH_MODE` ve `TESTMENTOR_USERS_FILE` ortam değişkenleri ayarı ezer: depo varsayılanı `header` (testler), Compose'un varsayılanı `password` (pilot).
- Giriş denemesi sınırlaması yok (şirket içi ağ, scrypt yavaş); gerekirse ters vekilde.

### Dağıtım

- Compose: `embedding` artık yalnızca motor profillerinde (`vllm`, `sglang`); profilsiz olsaydı `harici` profili de onu, yani vLLM imajını başlatırdı. `harici` profilinde yalnızca `postgres` ve `app` kalır (`docker compose --profile harici config --services`; test: `tests/test_infra_render.py`).
- Uygulamanın model adresi: motor servislerine ağ takma adı `llm` verildi ve `llm.base_url` şablonu `http://{host}:{port}/v1` oldu (`LLM_HOST`, varsayılan `localhost`). `harici` profilinde `.env` içindeki `LLM_BASE_URL` önceliklidir. `LLM_ENGINE` ve `LLM_MODEL` Compose'ta ortamdan gelir (`make local-up PROFILE=sglang` motoru da geçirir).
- Portlar ortamdan değişir: `APP_PORT` (varsayılan 8080; 8000 vLLM'in), `POSTGRES_PORT`.
- İmaj kökü `python:3.12-slim`, uv `ghcr.io/astral-sh/uv:0.11.32` (yerel uv ile aynı kilit biçimi), ön yüz `node:22-slim` ile derlenir; imaj 1,1 GB. Kurum vekili TLS'i yeniden imzalıyorsa kök sertifika BuildKit gizlisi olarak verilir (`make app-image EXTRA_CA=...`), imaja girmez. Bu ortamda da aynı yol kullanıldı (kapsayıcı trafiği yeniden imzalanıyor); Docker Hub hız sınırı nedeniyle temel imajlar `mirror.gcr.io`'dan çekilip yerelde etiketlendi.
- Kapsayıcı root ile çalışır: bağlanan `data/` klasörüne `python -m api.users add` yazabilsin diye (pilot.md güvenlik notu).

### Doğrulama

- `PgIndex` ve depo testleri `pgvector/pgvector:0.8.7-pg18` kapsayıcısına karşı geçti; yalıtım testi atlanmadan koştu. Yeni `tests/kb/test_index_pg.py`: bellek içi indeksle aynı parçalar ve en iyi sonuç, yalıtım, sürüm, boyut denetimi, belge kaydı, Postgres'li sunucuda yüklemeden arama düğümüne.
- Compose (`harici`, sahte model, Postgres, parolalı kip) ile kurulan uygulamaya karşı Playwright: `flow.spec.ts`, `documents.spec.ts`, `auth.spec.ts` geçti; uygulama yeniden başlatılınca projeler ve belge listesi Postgres'ten geldi; `pg_dump` yedeği alındı.
- Doğrulanamayan: `vllm`, `sglang`, `embedding` servisleri (GPU yok, imajlar çalıştırılmadı); gerçek modelle `harici`.
