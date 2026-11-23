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

(kol doldurur)
