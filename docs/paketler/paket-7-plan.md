# Paket 7 planı: bilgi havuzu

23 Kasım 2026. Model: Sonnet (kod); D9/D10 ölçümü ve kart çıkarımı prompt'unun gözden geçirmesi bu oturumda (Opus). Bitti ölçütü (tasarım): yalıtım testi geçiyor, altın sette kalite düşmüyor.

Okunacaklar: `docs/tasarim.md` (Proje bilgi havuzu, Prompt düzeni), `core/stages/retrieval.py`, `core/stages/base.py` (`Retrieve`, `PassageSource`), `core/prompts.py` (katman 4), `eval/pipeline.py` (`passages: none | gold`), `eval/corpus/` (v1 derlemleri), `eval/golden_v1.py`.

## Kapsam

- `core/kb/chunking.py` (saf): belge metni (markdown ya da düz metin; başlıklar `#` ya da numaralı bölüm satırları) → başlık yolu korunarak parçalar (`Chunk(id, document_id, heading_path, text, start)`), hedef `kb.chunk_tokens`, örtüşme `kb.chunk_overlap_tokens`; token ≈ karakter / 4 (ayar). Kimlik `<document_id>#<sıra>`; deterministik.
- `services/kb_index.py`: `KbIndex` protokolü (`add(project_id, chunks, vectors)`, `search(project_id, query_texts, k) -> list[str]`, `texts(project_id, ids)`). `InMemoryIndex`: yoğun (kosinüs, `Embed` ile sorgu vektörü = üye metinlerinin ortalaması) ve anahtar kelime (BM25, Türkçe ve İngilizce küçük harf ve noktalama temizliği) sonuçları RRF ile (`kb.rrf_k`) birleşir, ilk `kb.top_k`. `PgIndex`: pgvector + `tsvector`; uzantı yoksa entegrasyon testi atlanır. Her sorgu `project_id` filtresi taşır.
- Getirme bağlantısı: `services/kb_retrieve.py`: `make_retrieve(index, project_id, embed, k)` → `core.stages.base.Retrieve`; `make_passages(index, project_id)` → `PassageSource`. Parça metni prompt'a `[<belge> §<başlık yolu>] <metin>` biçiminde girer (paket 1'in altın parça biçimiyle aynı).
- Reranker (D9 kolu): `services/kb_rerank.py`, `kb.reranker` bir model adıysa çapraz kodlayıcıyla (sentence-transformers, CPU, `uv` grubu `d6`) ilk 3×k aday yeniden sıralanır; `none` ise yok.
- Proje kartı taslağı: `services/card_draft.py`: belgelerden kart taslağı (metin ≤ 1.500 token ve yöntem listesi) çıkaran model çağrısı; prompt `core/prompts.py` içinde, ortak sistem talimatıyla (prompt kuralları), kendi aşama sürümüyle (`STAGE_VERSIONS` değil, ayrı sabit `CARD_DRAFT_VERSION`); çıktı şeması pydantic.
- Örnek havuzu (D10 için, varsayılan kapalı `kb.examples: 0`): kullanıcının düzenlediği ya da sabitlediği test durumları; öbek üye metinlerine en benzer `kb.examples` örnek seçilir ve `RetrievalContent`'e `example_keys` olarak yazılır (test seti arama sonucuna zaten bağlı); prompt'ta katman 4'te parçalardan sonra `# Project examples` bölümü. Havuz değişince indeks sürümü artar (arama yeniden koşar, erken kesme seçilenler aynıysa test setini bayatlatmaz). Bu bir çekirdek değişikliğidir: önce `docs/tasarim.md` (ayrı commit), sonra kod; test seti şablon sürümü artar.
- Ölçüm bağlantısı: `eval/pipeline.py` `passages: index` kipi (v1 derlemi `InMemoryIndex`'e yüklenir, gerçek arama); `kb:` ayarları deney dosyasından ezilebilir. Deney dosyaları: `config/experiments/d9-*.yaml`, `d10-*.yaml` ve `config/batches/paket7.yaml` (koşmak bu oturumun işi).

## Testler

- **Bitti testi (yalıtım)** `tests/test_kb_isolation.py`: iki projeye benzer belgeler yüklenir; her projenin bütün öbek aramaları ve prompt'ları yalnızca kendi parça kimliklerini içerir (`InMemoryIndex` ve, uzantı varsa, `PgIndex`).
- Parçalama (başlık yolu, boyut, örtüşme, deterministiklik), BM25, RRF, getirme bağlantısının üretici üzerinden prompt katman 4'e girmesi (sahte model), örnek havuzu seçimi ve erken kesme, kart taslağı şeması (sahte model).
- "Altın sette kalite düşmüyor" ölçümü GPU ister; bu oturum `passages: index` ile D9 kollarını koşar.

## Kurallar

Ücretli kaynak ve hakem yok (alt oturum). `core/` HTTP ya da veritabanı içe aktarmaz. `make test`, `make lint` yeşil. Ayarlar `config/pipeline.yaml` `kb:` bölümünde.
