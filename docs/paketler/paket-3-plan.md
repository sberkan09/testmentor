# Paket 3 planı: aşamalar ve prompt'lar (öbekleme, test üretimi, doğrulama yöntemi)

Tarih: 20 Kasım 2026. Model: Opus. Dal: `claude/tender-knuth-ouy8ft`, origin/main'e (`8f41caa`, paket 2 birleşti, #4) hızlı ileri alınır. Bu dosya onaydan sonra `docs/paketler/paket-3-plan.md` olarak kaydedilir.

## Bağlam

Paket 2 çekirdeği kurdu: düğümler, `input_hash` / `cache_key`, aşama kaydı (yalnızca bağımlılık bildirimleri), `apply` / `settle` / `settle_many`, `Hint` (full, incremental, merge). Aşamaların üretim fonksiyonları yok; ölçüm hâlâ paket 1'in yalın `eval/pipeline.py` dosyasıyla yapılıyor. Paket 3 her aşamanın üretim fonksiyonunu ve prompt'unu yazar, `eval/` koşucusunu bu aşamalara bağlar ve D6, D7, D8'i koşar.

Bitti ölçütü (`docs/tasarim.md`, Geliştirme planı): **altın sette belirlenen eşikler aşılıyor.** Eşikler `docs/paketler/paket-1-olcum.md` Karar kuralı adım 1'dedir: şema ≥ %99, onarım sonrası kapsama %100, adım yapısı %100, Test olmayana test 0. Yorumu aşağıda, "Bitti ölçütü" bölümünde.

Başlangıç durumu (20 Kasım 2026): açık pod yok (`list-pods` boş, `make status` son pod'u silinmiş gösteriyor). Bakiye 13,55 USD. Hakem anahtarı ortamda var.

## Kapsam

İçinde:
- Üretim arayüzü: `core/` model istemcisi içe aktarmaz; üreticiler enjekte edilen bir tamamlama protokolüyle çalışır.
- Aşama üreticileri: embedding, öbekleme ağacı, ilk öbekleme ve yeniden kesim, öbek adı, arama sonucu (yer tutucu getirici), doğrulama yöntemi (toplu), test seti (baştan, artımlı, birleştirme, onarım, 25'ten büyük öbeği bölme), matris satırı (modelsiz, en yalın hali).
- Prompt'lar ve aşama başına prompt sürümü; öbek adı prompt'u (yeni), artımlı ve birleştirme kuyrukları.
- `eval/` koşucusunun yeni aşamalarla çalışması (dalga sürücüsü), yeni ölçütler (tekrar eden test oranı, taşıma sayısı, korunma oranı).
- D6, D7, D8 deneyleri ve raporları; sonuçların tek satırlık `config/` değişikliğiyle uygulanması.

Dışında:
- Kuyruk, öncelik, bekleme, iptal yürütme, aşama kapıları, hint'lerin kalıcı saklanması, Postgres (paket 5). Paket 3'ün dalga sürücüsü yalnızca ölçüm içindir; paket 5 onun yerine gerçek kuyruğu koyar.
- Gerçek arama, parçalama, proje kartı çıkarımı, örnek havuzu (paket 7; D9, D10). Bu pakette getirici `none` ya da `gold` (altın set v1 destek parçaları).
- İçe alma, matris görünümü ve SQL'i, xlsx (paket 4). REST, WebSocket (paket 6). Arayüz (paket 8).
- Model, motor, ağırlık hassasiyeti, eşzamanlılık değişikliği (paket 1'de kararlaştı). D0 (test mühendisi yok), D10, D11.

## Üretim arayüzü (`core/stages/base.py`, `core/llm.py`)

- `core/llm.py`: `LLMRequest(stage, unit, messages, schema: type[BaseModel], temperature, thinking, max_tokens)`, `LLMReply(parsed, schema_error, content, metrics)`, `Complete` Protocol (`async (LLMRequest) -> LLMReply`). `core/` yalnızca bu tipleri bilir. `services/stage_llm.py` `Complete`'i `LLMClient.chat_stream` ile uygular (iptal edilebilir, akış metrikleriyle); testler sahte `Complete` verir.
- `ProduceContext`: `state`, `refs` (yöntem aşamasında bir toplu iş, diğerlerinde tek düğüm), `hint`, `settings` (`StageSettings`: etiket listeleri, sınırlar, örnekler; `config/` dosyalarından `services/settings.py` kurar), `sources` (birleştirmede eski setlerin içerikleri; depo geçmişinden çağıran verir), `passages` (`PassageSource` Protocol: parça kimliği → metin; paket 7 uygular), `embed` ve `retrieve` (Protocol, modelsiz aşamalar için), `new_id` (kimlik üretici; core kimlik üretmez).
- `StageSpec`'e iki alan eklenir: `produce: Producer | None` ve `batch_size` (yöntem aşaması için). Üretici `async def produce(ctx, complete) -> list[tuple[NodeRef, Result]]`. `Result` baştaki durumdan hesaplanan `expected_hash` ve `cache_key` ile kurulur; iş sürerken durum değişirse `settle` sonucu reddeder (paket 2 kuralı), sonuç cache'e kendi anahtarıyla yazılır.
- Hata sınırı: üretici şema hatasında bir kez yeniden dener (hata mesajı prompt'un sonuna eklenir), sonra `ProductionFailed` fırlatır. Çağıran `mark_failed` der (paket 5). Onarım çağrısından sonra kapsanmamış kalan gereksinim varsa set yine yazılır; gereksinim matris satırında `covered=false` görünür ("kapsanmamış gereksinim" durumu), düğüm `failed` olmaz.

## Aşamalar ve paket 2'ye bağlanışları

| Aşama | Üretim | Bağlanış |
| --- | --- | --- |
| Embedding | `embed` ile toplu vektör | `settle_many`; `identity_by_input` olduğundan aşağısı beklenen hash'i görür |
| Öbekleme ağacı | `core.clustering.build_tree` → `ClusteringContent` | modelsiz, tek düğüm |
| İlk öbekleme | `initial_membership(ids, vectors, cfg, new_id)`: içe almada vektörlerden ağaç, kesim, öbek kimlikleri; `new_project(clusters=...)` bunu alır, embedding ve ağaç aynı vektörlerden hemen `settle_many` ile yazılır | `new_project` her gereksinimin bir öbekte olmasını istediği için kesim projeden önce yapılır |
| Yeniden kesim | `recut(state, threshold, max_size, new_id) -> MembershipChanged`: sabit atamalar yerinde kalır; yeni öbekler eski öbeklerle kesişim büyüklüğüne göre birebir eşlenir (`scipy` `linear_sum_assignment`), anahtar yalnızca kesişim ≥ 1 ise ve eski öbeğin üyelerinin yarısından fazlası yeni öbekteyse yeniden kullanılır, aksi halde yeni kimlik. Eşitlikte en küçük kimlik | paket 2 notu: var olan anahtar başka üyelerle kullanılmaz. Sabit test durumları bu sayede çoğunlukla kendi gereksinimleriyle aynı sette kalır; paket 2'nin taşıma kuralı değişmez |
| Öbek adı | öbek başına bir çağrı, 3–6 kelime ve bir cümle gerekçe, üyelerin çoğunluk dilinde | `settle` |
| Arama sonucu | `retrieve(üye metinleri)`; `none` boş liste, `gold` altın destek parçalarının kimlikleri (deterministik sıra) | modelsiz; test seti buna bağlı olduğu için önce yazılır |
| Doğrulama yöntemi | kimlik sırasıyla `batch_size` (25) gereksinimlik toplu çağrı; yalnızca bayat olanlar | `settle_many`; dönmeyen kimlik bir kez tekli çağrıyla tekrar denenir, yine dönmezse o düğüm başarısız |
| Test seti | baştan, artımlı, birleştirme; onarım; bölme (aşağıda) | `settle`; `Result.cases` her zaman tam settir |
| Matris satırı | yöntem, kapsayan test anahtarları, `covered` (modelsiz) | `settle_many`; görünüm ve xlsx paket 4 |

Dalga sürücüsü (`eval/stage_driver.py`): `analyze(state).ready` → türe göre grupla → üreticileri eşzamanlı koş (`asyncio.Semaphore(concurrency)`) → `settle_many` → hazır kalmayana kadar tekrar. Referans kipinde (`generation_inputs: reference`) proje referans öbekleriyle kurulur ve yöntem aşaması tahmin için yine koşar (yöntem doğruluğu raporlanır), sonra referans yöntemler `MethodEdited` olarak yazılır (sabit ve taze; `settle` sabit üstü kabul eder). Uçtan uca kipte (`predicted`) öbekler `initial_membership`, yöntemler model çıktısıdır.

## Prompt düzeni ve sürümleme (`core/prompts.py`)

- Tüm model aşamaları aynı sistem talimatını ve proje kartını paylaşır (katman 1–2). Katman 3 aşama başına sabittir (talimat, şema, örnek). Test setinin tüm kipleri (baştan, artımlı, birleştirme, onarım, şema yeniden denemesi) katman 1–5'i **bayt bayt aynı** kullanır; kipe özgü malzeme prompt'un sonuna eklenir: sabit test durumları, mevcut testler, değişiklik bildirimi, kip çıktı şeması, onarım talimatı. Böylece artımlı ve onarım çağrıları baştan üretimin önek cache'inden yararlanır.
- Baştan üretim prompt'u paket 1'deki `generation_messages` (şablon `t2`) çıktısıyla aynı kalır; anlık görüntü testi bunu bağlar. Paket 1 tabanı (check_recall v0 0,454, v1 0,449) böylece karşılaştırılabilir kalır.
- Proje kartı düğümü (`ProjectCardContent`) yöntem listesini yapısal olarak da taşır (`methods: [{name, criterion}]`); kart metni bundan üretilir, yöntem şemasının enum'u buradan gelir. Tasarımda liste zaten kartta duruyor; yalnızca veri modeli bunu açık yapar.
- **Aşama başına sürüm.** Paket 2'de `stage_configs[kind].prompt_version` zaten tür başına hash'e giriyor; eksik olan bu metnin nereden geldiği. Kural:
  - `SHARED_VERSION` (sistem talimatı ve kart çizimi) ve aşama başına `STAGE_VERSIONS = {method: "m1", cluster_label: "l1", test_set: "g3"}` kodda, şablonun yanında durur. Embedding ve ağaç için sürüm, model ve kümeleme parametreleri ayardan gelir.
  - `prompt_version(stage, settings) = f"{SHARED_VERSION}.{STAGE_VERSIONS[stage]}+{parmak_izi}"`; parmak izi, sistem talimatı ile ayarla çizilmiş katman 3'ün (etiketler, örnekler, şema) SHA-256'sının ilk 12 karakteridir. Örnek dosyası ya da etiket listesi değişirse sürüm kendiliğinden değişir; ortak katman değişirse tüm model aşamaları bayatlar ("Prompt ya da model sürümü değişti" satırı, onaylı).
  - Kodda değişen dinamik çizim (gereksinim bloğu, kuyruk) için elle sürüm artırılır. Bunu unutmamak için anlık görüntü testi sabit bir girdinin çizimini `{sürüm: hash}` tablosuyla karşılaştırır; çizim değişip sürüm değişmezse test kırılır.
  - `services/settings.py` `StageConfig(prompt_version, model, params)` nesnelerini kurar; `config/pipeline.yaml` içindeki tek `prompt_version: p1` ve `core/prompts.TEMPLATE_VERSION` kalkar. `eval/` çağrı kayıtları aşama sürümünü yazar.

## Test seti üretimi

**Kip seçimi.** Paket 2'nin `Hint`'i nedene bakmaz: içeriği olan her bayat sete `incremental` der (kart, aşama ayarı, belge değişikliği dahil). Bu yüzden üretici kipi kendisi doğrular. Her üretilen setin `produced_by.params.basis` alanına dayanak yazılır: aşama `prompt_version`, model ve parametreler, kart hash'i, parça kimlikleri, üye başına `(metin hash'i, yöntemler)`. Artımlı kip yalnızca kart, aşama ayarı ve parça kimlikleri dayanakla aynıyken kullanılır; aksi halde baştan üretilir. `merge` hint'i (eski setler) ancak `ctx.sources` verilmişse kullanılır, yoksa baştan. Hint'leri olaydan işe kadar taşımak paket 5'in işidir; paket 3 hint olmadan da doğru çalışır.

**Değişiklik.** Dayanak ile güncel durum karşılaştırılır: eklenen, metni ya da yöntemi değişen ve çıkan üyeler.
- Çıkan üyeler: yalnızca çıkan gereksinimleri kapsayan sabit olmayan testler düşer; karışık kapsamlı testlerin `covers` listesi kırpılır ve kuyruğa tam metinleriyle "güncelle" diye verilir.
- Eklenen ya da değişen Test üyeleri: kuyrukta etkilenen testler tam metinle, diğerleri başlık ve kapsama özetiyle verilir (tasarım, Claude Code tablosu; D8 ölçer).
- Artımlı çıktı şeması: `{"add": [...], "update": [...]}`; `update` mevcut bir kimliği taşır ve testin tam halidir. Sabit test kimliğine gelen güncelleme yok sayılır ve sayılır (`pinned_update_attempts`).
- Sonuç tam set olarak yazılır: değişmeyen testler aynı kimlik ve içerikle döner, böylece `_write_cases` düğümlerini ve matris satırlarını taze bırakır. Yeni testlere `TC-<n>` biçiminde boş ilk numara verilir.

**Sabit test durumları** (setin bağlamı, `cache_key`'e girer) her kipte kuyruğa "değiştirilemez; tekrarlama" diye tam metinle eklenir. Üretilen ve sabitle aynı kimliği taşıyan test `settle` tarafından zaten düşürülür.

**Birleştirme.** Kaynak setlerin testleri tam metinle kuyruğa verilir; çıktı `{"drop": [kimlik]}` (yalnızca tekrarları ayıklar). Kaynaklardaki kimlik çakışması `<eski öbek>.<kimlik>` ile çözülür. Ardından kapsama denetimi ve gerekirse onarım.

**Doğrulama ve onarım.** Kod, her çıktıda `covers` listesini öbeğin yöntemi Test içeren üyelerine süzer (geçersiz ya da Test olmayan kimlik atılır, sayılır); boş kalan test düşer. Yöntemi Test içeren ve hiçbir `covers` listesinde geçmeyen gereksinimler için tek onarım çağrısı yapılır (yalnızca onları ister; paket 1 kuyruk metni). Onarımdan sonra da eksik kalan, yukarıdaki "kapsanmamış" durumudur.

**Bölme.** İki sınır ayrıdır: `clustering.max_cluster_size` (kesimde öbek parçalar, arayüzdeki öbekler) ve yeni `generation.max_unit_size` (üretimde birim; kullanıcının oluşturduğu ya da birleştirdiği büyük öbekler). İkisinin çalışma varsayımı 25. Birimden büyük öbek kimlik sırasıyla dengeli parçalara bölünür (⌈n/25⌉ parça), parçalar paralel üretilir, testler tek sette birleşir, kimlikler parça önekiyle tekilleşir; kapsama denetimi bütün sette yapılır. D7 `generation.max_unit_size` ile üretim birimini değiştirir; `clustering.max_cluster_size` sabit kalır. Altın sette en büyük referans öbek 15 olduğundan bölme birim testleriyle bağlanır.

## Tasarım güncellemeleri (`docs/tasarim.md`, ayrı commit, koddan önce)

1. Veri modeli kuralları: aşama başına prompt sürümü (ortak sürüm, aşama sürümü, parmak izi); proje kartı yöntem listesini yapısal taşır; test setinin `produced_by` alanında dayanak.
2. Test durumu üretimi: tüm kipler katman 1–5'i paylaşır, kip malzemesi sonda; artımlı yalnızca kart, aşama ayarı ve parçalar aynıyken; sonuç tam set olarak yazılır; `covers` sunucuda Test üyelerine süzülür; tek onarımdan sonra eksik kalan "kapsanmamış" durumudur (`failed` değil); iki ayrı 25 sınırı.
3. Öbekleme: ilk kesim içe almada vektörlerden; yeniden kesimde anahtar seçimi üyelik örtüşmesine göre.
4. Geliştirme planında paket 3 satırına "plan: `paket-3-plan.md`".

## Deneyler

Kurallar tasarımdan: tek değişken; ölçülebilir fark yoksa daha basit olan kalır; sonuç tek satırlık ayar değişikliğiyle uygulanır ve Deney planı tablosuna Sonuç sütunu olarak yazılır (`docs/deneyler/D6.md`, `D7.md`, `D8.md`). D7 ve D8 altın set v1'in referans öbekleriyle koşar (üretim kalitesi öbeklemeden ayrı); hakem Claude Sonnet, rubrik r1.

### D6: Embedding ve kümeleme (pod gerekmez, 0 USD)

- Çalışma varsayımı: BGE-M3, agglomerative (average, eşik 0,35).
- Denenenler: embedding BGE-M3 ve iki alternatif. Adaylar `intfloat/multilingual-e5-large` ve `Qwen/Qwen3-Embedding-0.6B`; uygulama adımında Hugging Face API'siyle resmî kuruluş hesabından doğrulanır, yoksa aynı boyutta resmî bir çok dilli model seçilip plana not edilir. Kümeleme agglomerative (average ve complete; eşik 0,20–0,60, adım 0,05) ve HDBSCAN (`min_cluster_size` 2, 3, 5).
- Vektörler: BGE-M3 için mevcut önbellek (`eval/cache/embeddings.json`, 269 = 40 + 109 + 120 gereksinim, GPU'da hesaplanmış). Alternatifler bu konteynerde CPU'da hesaplanır (`uv` bağımlılık grubu `d6`: `sentence-transformers`); BGE-M3 CPU'da da hesaplanıp GPU vektörleriyle aynı öbeklemeyi verdiği doğrulanır.
- Ölçüt: proje başına ARI ve **taşıma sayısı** (gereksinim sayısı eksi öbekler arası en iyi birebir eşleşmedeki ortak üye sayısı; kullanıcının referansa ulaşmak için taşıması gereken en az gereksinim), öbek sayısı. Eşik v1 projeleri üzerinde seçilir, birini dışarıda bırakma ile genellenebilirlik raporlanır; v0 (proje başına 8 gereksinim) ayrı gösterilir.
- Sınır: referans öbekler uzman değil, kaynak belge bölümleridir (ETC SRS bölümü, KDH standart alanı; KDH 120 gereksinimde 66 öbek). "Uzmanın elle öbeklemesiyle uyum" yerine bu vekil ölçülür ve rapora yazılır.
- Uygulama: eşik ya da yöntem tek satırla `config/pipeline.yaml`'a. Embedding modeli değişirse üretim embedding servisi (vLLM pooling) desteği paket 3'ün dışında doğrulanır; o zamana kadar BGE-M3 kalır ve karar tabloya "açık" diye yazılır.

### D7: Üretim birimi (GPU)

- Çalışma varsayımı: öbek başına tek çağrı, sınır 25.
- Denenenler: gereksinim başına çağrı (birim 1); birim sınırı 10, 25, 50. Birimler referans öbeklerden kurulur: sınırdan büyük öbek bölünür, küçük öbekler referans sırasıyla (aynı belge bölümü komşu) sınıra kadar birleştirilir. Karıştırıcı: birleştirilen birimde konu karışır; bu, büyük birimin gerçek maliyetidir ve rapora yazılır.
- Ölçüt: check_recall (hakem), uydurma içerik, **tekrar eden test oranı** (aynı projede `covers` kümesi aynı ve normalleştirilmiş adım metinlerinin kelime Jaccard'ı ≥ 0,8 olan test çiftlerinin payı), test sayısı, süre ve çıktı token'ı.
- Karar: katman 1 eşiklerini geçenler arasında recall'da gürültüyü (gereksinim bootstrap %95 aralığı) aşan fark yoksa 25 kalır; tekrar oranı ve süre ikincil.

### D8: Yeniden üretim biçimi (GPU)

- Çalışma varsayımı: artımlı.
- Senaryo (v1, Test üyesi ≥ 3 olan 26 referans öbek, 144 gereksinim): her öbekten en büyük kimlikli Test üyesi ayrılır, set onsuz baştan üretilir, her sette bir test sabitlenir (başlığı ve bir adımı değiştirilmiş "kullanıcı düzeltmesi"). Sonra üye geri eklenir: (a) artımlı, (b) baştan.
- Ölçüt: **korunma oranı** (önceki sabit olmayan testlerden değişmeden kalanların payı; baştanda en iyi eşleşen testin metin benzerliği ≥ 0,9), sabit testlerin korunması (yapısal olarak %100 olmalı) ve sabitin tekrarı (sabite ≥ 0,8 benzer üretilmiş test), yeni gereksinimin onarım öncesi kapsaması ve recall'ı, tüm öbeğin recall'ı, süre ve çıktı token'ı.
- Ek kol, çıkarma: aynı öbeklerden bir üye çıkarılır; (a) artımlı çağrı, (b) modelsiz budama (yalnızca çıkan gereksinimi kapsayan testler düşer, karışık testlerin kapsaması kırpılır). Fark ölçülemezse daha basit olan budama seçilir ve bayatlama tablosundaki çağrı sayısı tasarımda ayrı commit'le güncellenir. Ölçüm gelene kadar tasarım geçerlidir (çıkarma da artımlı çağrıdır).
- Ek kol, birleştirme: komşu öbek çiftleri birleştirilir; birleştirme prompt'u (tekrar ayıklama) ve baştan. Ölçüt tekrar oranı, kapsama, recall, süre.
- Sınır: 26 eklenen gereksinim recall için küçük örneklemdir; aralıklar raporlanır.

## Bitti ölçütü

Kullanıcı kararı (20 Kasım 2026): referans girdilerle eşikler ve gerileme yok. Ölçüt:
1. Yeni aşama koduyla (eski `eval/pipeline.py` değil), `generation_inputs: reference` ile v0 (3 tekrar) ve v1'de katman 1 eşikleri geçer.
2. Gerileme yok: check_recall paket 1 tabanından (v0 0,454; v1 parçasız 0,449) gereksinim bootstrap %95 aralığının alt sınırı −0,05'in altına düşmez; yöntem tam eşleşmesi v0'da ≥ 0,75.
3. Uçtan uca (`predicted`) koşu v0 ve v1'de raporlanır: şema ve adım yapısı eşikleri ile **tahmin edilen yöntemlere göre** kapsama %100 aranır. Referansa göre kapsama ve ihlal yalnızca raporlanır (yöntem doğruluğu ~%75 iken %100 olamaz).
4. Bayatlama tablosu ve paket 2 testleri yeşil kalır; üretim yolunda her olayın beklenen kipte ve çağrı sayısında üretildiği birim testleri geçer.

## GPU planı ve bütçe

- GPU: NVIDIA RTX PRO 6000 Blackwell Server Edition, 96 GB, Secure Cloud, **2,69 USD/saat** (`list-gpu-types`, 20 Kasım 2026). EU-RO-1, network volume `testmentor-models`. Motor ve model paket 1 kararı: vLLM, Qwen3.8-27B FP8, 64 dizi, 32k bağlam. Hazır olma ~10 dk (587 sn).
- Pod 1, duman testi: `make up MAX_HOURS=0.5`; yeni aşamalarla v0 referans tek koşu ve v1 uçtan uca bir proje. Beklenen ~0,3 saat (0,8 USD), üst sınır 1,35 USD. Sonda `make down`.
- Pod 2, `make batch BATCH=paket3` (`max_hours: 2`): bitti koşuları (v0 referans ×3, v0 uçtan uca, v1 referans, v1 uçtan uca; ~25 dk), D7 dört kol (~35 dk), D8 ekleme, çıkarma, birleştirme (~35 dk). Beklenen ~1,7 saat (4,6 USD), üst sınır 5,38 USD. Batch son adımda her durumda pod'u siler.
- **Paket bütçesi: 7 USD** (iki pod'un üst sınırları toplamı 6,73 USD). Beklenen toplam ~5,4 USD; bakiye sonrası ~8 USD kalır. Her pod açılışından önce bakiye, saatlik fiyat ve bekçi son tarihi yazılır; `runpod-kredi-korumasi` skill'i ücretli işten önce okunur. Süre yetmezse önce D8 birleştirme kolu çıkarılır, bekçi kapatılmaz.
- D6 ve hakem pod kapalıyken yerelde koşar. Hakem çağrıları Anthropic API'sine gider (Runpod bütçesine girmez): yaklaşık 7 v1 koşusu × 220 gereksinim + v0 3 × 40 ≈ 1.650 çağrı; cache aynı çıktıyı yeniden puanlamaz.
- Her pod'dan sonra `docs/altyapi.md` doğrulama defteri: GPU, imaj etiketi, süre, bellek tepe değeri, maliyet, tuzaklar.

## Adımlar

1. Dalı origin/main'e hızlı ileri al. Bu planı `docs/paketler/paket-3-plan.md` olarak kaydet, commit.
2. `docs/tasarim.md` güncellemeleri (yukarıdaki liste ve bitti ölçütünün yorumu, Geliştirme planı paket 3 satırına), ayrı commit.
3. Arayüz ve testler (kırmızı): `core/llm.py`, `StageSpec.produce`, `ProduceContext`, üretici imzaları, `core/prompts.py` sürüm tablosu; `tests/stages/` (sahte `Complete`). Commit.
4. Uygulama: prompt'lar (öbek adı, artımlı, birleştirme kuyrukları), üreticiler, `recut` ve `initial_membership`, `services/stage_llm.py`, `services/settings.py` içinde `StageConfig` ve `StageSettings`. `make test`, `make lint`. Commit.
5. `eval/`: dalga sürücüsü, `eval/pipeline.py` yeni aşamalara geçer (koşucu arayüzü `Pipeline.run` aynı), yeni ölçütler, `config/experiments/p3-*.yaml`, `d7-*.yaml`, `d8-*.yaml`, `config/batches/paket3.yaml`. Sahte modelle uçtan uca test. Commit.
6. D6 (CPU), rapor, ayar değişikliği. Commit.
7. Pod 1 duman testi; hatalar düzeltilir. Pod 2 batch. `make down` 404 ile doğrulanır, defter güncellenir.
8. Hakem, `python -m eval.summarize`, `D7.md`, `D8.md`; Deney planı tablosuna sonuçlar; kazananlar `config/`'e tek satırla. Bitti ölçütü tablosu bu plana eklenir. Commit, push. PR yalnızca istenirse.

## Doğrulama

- `uv run pytest -q --tb=short` ve `make test`: paket 2'nin 195 testi ve yeni aşama testleri geçer. `make lint` temiz.
- `grep` ile `core/` içinde `httpx`, `openai`, `anthropic`, veritabanı sürücüsü içe aktarımı yok.
- Birim testleri (model yok): baştan prompt'un paket 1 çıktısıyla bayt bayt aynı olması; tüm kiplerde katman 1–5'in aynı, farkın yalnızca sonda olması; sürüm anlık görüntüsü; ortak sürüm değişince tüm model aşamalarının, test şablonu değişince yalnızca test setlerinin bayatlaması; artımlı sonucun değişmeyen testleri aynı kimlik ve içerikle döndürmesi (matris satırları taze kalır); sabit teste güncelleme yok sayılır; kart ya da parça değişince artımlı yerine baştan; birleştirmede `drop`; onarım yalnızca eksikleri ister ve sonrasında eksik kalan `covered=false`; şema hatasında tek yeniden deneme sonra `ProductionFailed`; 60 üyeli öbeğin 3 parçaya bölünmesi; `recut`'ın anahtarı örtüşmeye göre seçmesi, sabit atamaları koruması ve tamamen başka üyelere eski anahtarı vermemesi; bayatlama tablosunun olaylarının sahte üreticiyle uçtan uca taze duruma dönmesi ve çağrı sayısının tabloyla tutması.
- Sahte OpenAI sunucusuyla (`tests/fake_openai.py`) `eval` uçtan uca: referans ve uçtan uca kip, onarım, rapor.
- GPU koşuları: rapor tabloları, eşik sütunu ✓, `make down` sonrası `get-pod` 404 ve `list-pods` boş.

## Riskler

- Yeni aşama kodu baştan prompt'u değiştirirse paket 1 tabanıyla karşılaştırma bozulur; anlık görüntü testi bunu önler.
- Artımlı kuyruk uzun setlerde bağlamı şişirebilir; özet biçimi (başlık ve kapsama) ve D8 ölçümü bunun içindir.
- D6'nın referansı uzman değil, belge bölümüdür; eşik bu vekile aşırı uyabilir. Birini dışarıda bırakma raporlanır, karar "ölçülebilir fark yoksa basit olan" kuralıyla verilir.
- Hakem gürültüsü (±0,05) D7 ve D8'deki küçük farkları gizleyebilir; aralıklar raporlanır, fark yoksa çalışma varsayımı kalır.

## Arayüz adımında netleşenler (adım 3, 20 Kasım 2026)

- `core/llm.py`: `LLMParams`, `LLMRequest`, `LLMReply`, `LLMUsage`, `Complete`. `core/settings.py`: `StageSettings`, `ClusteringSettings` (`core/` dosya okumaz; `services/settings.load_stage_settings` kurar). `StageSettings` `core/stages/` altında değil: `core.prompts` onu içe aktarıyor, aşama paketi de `core.prompts`'u; döngü olmasın diye ayrı modülde.
- `core/stages/base.py`: `ProduceContext`, `ProduceOutcome` (`results`, `failed`, `stats`), `Producer`, `Embed` / `Retrieve` / `PassageSource` protokolleri; `StageSpec.produce` ve `StageSpec.batched` (embedding, yöntem, matris). Üretici hata fırlatmaz, başarısız düğümleri `failed` içinde döner (toplu aşamada bir kısmı başarısız olabilir). Planın `ProductionFailed` istisnası bu yüzden yok.
- Her aşama modülünde `produce` imzası ve davranışını tanımlayan docstring; test seti yardımcıları `core/stages/test_generation.py` (dayanak, kip seçimi, değişiklik, süzme, bölme, kimlik, budama, artımlı ve birleştirme uygulaması). Öbekleme: `cut`, `initial_membership`, `recut` (`core/stages/clustering.py`). HDBSCAN'de gürültü noktası tek üyeli öbek olur.
- Baştan üretimde (bölünmüş öbek dahil) testler parça sırasıyla birleşir ve `TC-1…` diye yeniden numaralanır; planın "parça öneki" yerine bu. Baştanda kimlik zaten kararlı değil; artımlı kip kimlikleri korur.
- Birleştirmede `sources` yalnızca sabit olmayan testleri taşır (sabitleri çekirdek yeni sete taşıdı, sabit bölümünde görünürler). Birleştirme sonrası kapsanmayan gereksinim onarılır.
- Yayınlanan sözleşmeler şimdiden yazıldı: `core/schemas.py` içinde `test_case_model`, `incremental_model`, `MergeDecision`, `ClusterLabel` (`case_set_model`'in JSON şeması paket 1'dekiyle aynı, doğrulandı); `core/prompts.py` içinde sürüm tablosu (`SHARED_VERSION = s1`, `STAGE_VERSIONS`), öbek adı, sabit testler, artımlı, birleştirme ve şema düzeltme metinleri. `ProjectCardContent.methods` (`MethodDef`), `ProjectCardChanged.methods` (None listeyi korur; çekirdekte uygulandı), `new_project(methods=...)`. `config/pipeline.yaml`: `cluster_label` parametreleri, `generation.max_unit_size: 25`.
- Testler `tests/stages/` (68 test): sahte `Complete` (`ScriptedComplete`, `smart_reply`) ve test içi dalga sürücüsü (`drive`). Bugün 4'ü geçiyor, 64'ü `xfail(raises=NotImplementedError, strict=True)`: üretici yazıldıkça XPASS olur ve katı işaret onları hataya çevirir.

## Uygulama adımında netleşenler (adım 4, 20 Kasım 2026)

- Durum: `make test` 263 geçti, xfail yok; `make lint` temiz; `core/` içinde HTTP, model istemcisi ya da veritabanı içe aktarımı yok; `core/` ve `services/` içinde `NotImplementedError` kalmadı. Paket 1 prompt'ları (`generation_messages` onarımlı ve onarımsız, `classification_messages`) değişiklikten önce ve sonra bayt bayt aynı (karşılaştırma dökümüyle doğrulandı). `RENDER_HASHES` üç sürüm için yazıldı (`s1.m1`, `s1.l1`, `s1.g3`).
- Ortak çağrı yardımcısı `core/stages/calls.py`: tek çağrı ve şema yeniden denemesi (`call`, `CallFailed`), çağrı sayısı ve token toplamları (`CallLog`, istatistiklere `prompt_tokens`, `completion_tokens`, `cached_tokens` olarak girer; D7 için), sonuç kurma (`result`: beklenen hash ve cache anahtarı işin başladığı durumdan, `produced_by` aşama ayarından). Yeniden deneme her zaman ilk mesajlara eklenir, üst üste binmez.
- **Hash'e giren ek parametreler.** `stage_configs`, prompt'u değiştirmeden çıktıyı değiştiren ayarları da `params`'a koyar: yöntem aşamasında `batch_size`, test setinde `max_unit_size` (D7'nin değişkeni) ve `repair`. Tasarımın `input_hash` tanımı (üretim parametreleri) ve `core/settings.py` kuralı bunu zaten istiyor; ayrı tasarım değişikliği gerekmedi. Sonradan eklenseydi tüm hash'ler değişirdi.
- **Test yöntemini kaybeden üye.** Artımlı kipte yöntemi değişip artık Test içermeyen üye, budamada çıkan üye gibi işlenir: yalnızca onu kapsayan sabit olmayan testler düşer, karışık testlerden kimliği çıkarılır (tasarım: `covers` Test üyelerine süzülür). Kapsanacak üye kalmayan öbekte (hiç Test üyesi yok) hiçbir kipte çağrı yapılmaz, set boş yazılır. Baştan kipte sabit testler tüm Test üyelerini kapsıyorsa da çağrı yok.
- Sabit testlerin "alınmış" kimlikleri düğüm anahtarından okunur (taşınan sabit testin anahtarı `<eski öbek>.<kimlik>` olabilir, içerik kimliği değişmez); `settle` çakışmayı anahtara göre denetlediği için.
- Bölünmüş baştan üretimde Test üyesi olmayan birim çağrılmaz (şema en az bir test istiyor). `incremental_section` ve `pinned_section` testleri doğal kimlik sırasıyla verir (`TC-2`, `TC-10`'dan önce); `case_block` `kind` alanını yazmaz (modelin çıktı biçimiyle aynı).
- `recut` eşitlik kuralı maliyet matrisine kodlandı: örtüşme ağırlığı, eşitlik terimlerinin toplamından büyük bir ölçekle çarpılır; eşitlikte küçük eski anahtar, sonra küçük ilk kimlikli grup. HDBSCAN önceden hesaplanmış kosinüs uzaklıklarıyla (`sklearn.cluster.HDBSCAN`, `metric="precomputed"`) koşar; `min_cluster_size`'tan az nokta hepsi gürültüdür (tek üyeli öbek).
- **Fikstür düzeltmesi** (`tests/stages/test_recut.py::test_hdbscan_puts_noise_in_singletons`): üç dik eksende tüm öbekler arası uzaklıklar ~0,99'du ve R6'nın R5'e uzaklığı (0,989) x–y öbekleri arasındakinden (≥0,991) küçüktü; HDBSCAN R6'yı y öbeğine katıyordu. Beklenti aynı kaldı; yalnızca vektörler değişti (x ile 0,5 uzaklıkta `xy` öbeği, ikisine ~1 uzaklıkta `-z` aykırı nokta).
- `load_stage_settings`: `examples_file` depo köküne göredir; `config_dir`'in üst dizinine göre çözülür. `ClientComplete` `LLMClient.chat_stream`'i istek parametreleriyle (sıcaklık, düşünme, `max_tokens`) çağırır, kullanım bilgisini `CallMetrics`'ten taşır.

## Adım 4 ve sonrası için devir (Sonnet)

- Sıra: `core/prompts.py` stub'ları → `core/stages/test_generation.py` → üreticiler (yöntem, ad, modelsizler, test seti) → `cut` / `initial_membership` / `recut` → `services/settings.py` (`load_stage_settings`, `stage_configs`) ve `services/stage_llm.py`. Her modül bitince ilgili test dosyasından `pytestmark` / `xfail_step4` işaretini kaldır; yeşil olmadan ilerleme.
- `tests/stages/test_prompts.py::test_rendering_snapshot_matches_version`: ilk koşuda eklenecek hash'i yazdırarak kırılır; `RENDER_HASHES`'e o satırı ekle. Sonradan çizimi değiştirirsen sürümü artır ve yeni satır ekle, eski hash'i değiştirme.
- Testlerin beklentisi tasarımla çelişirse testi sessizce değiştirme: önce `docs/tasarim.md` (ayrı commit) ya da bu plan, sonra test. `tests/stages/helpers.py` içindeki altyapı hataları (sahte model, sürücü) düzeltilebilir; düzeltme bu plana bir satırla yazılır.
- 64 xfail testi bir şartnamedir: gövdeleri ilk stub'da durduğu için hiçbiri sonuna kadar koşmadı. İlk yeşil koşuda test hatası çıkarsa yukarıdaki kural geçerli. Sahte modelin ayrıştırması (`requirement_rows`, `tail`, `smart_reply`) paket 1'in gerçek prompt'larıyla denendi.
- Adım 3 incelemesinde kapatılanlar: birleştirme ipucu kaynaksızsa normal kurala düşer; sabit testler kapsama sayılır (onarım çağırmaz); onarım prompt'u her kipte katman 1–5 + sabit bölüm + onarım metnidir (tek çıktı biçimi); artımlıda eklemeler modelin kimliğini hiç kullanmaz, yalnızca sabit kimliğe gelen güncelleme yok sayılır; `max_unit_size`'tan büyük öbekte artımlı yerine baştan (bölünmüş) üretim; mevcut testler `case_keys` sırasıyla okunur.
- Paket 5 için not: `_write_cases` setin `produced_by` alanını (dayanak dahil) her test durumu düğümüne kopyalar; Postgres şemasında dayanak set başına bir kez saklanmalı.
- Adım 5'te `core/prompts.TEMPLATE_VERSION` ve `config/pipeline.yaml` `prompt_version` kalkar; `eval/run.py` aşama sürümlerini yazar. Ücretli adımlar (7) planın GPU bölümüne ve `runpod-kredi-korumasi` skill'ine bağlıdır.
- Adım 5 için notlar (adım 4 sonunda, 20 Kasım 2026):
  - **İhlal ölçütü.** Yeni üretici `covers`'ı Test üyelerine süzer; referans kipte "Test olmayana test 0" böylece kendiliğinden sağlanır ve paket 1 tabanıyla karşılaştırılamaz (paket 1 yalnızca öbek dışı kimlikleri atıyordu, ihlali ölçüyordu). `eval/` ihlali süzmeden önceki ham model çıktısından saymalı (çağrı kaydındaki içerik ya da üreticinin `dropped_ids` istatistiğinin Test olmayan kısmı); süzülmüş setin ihlali ayrıca raporlanır. Bitti ölçütü yorumunu etkilediği için kararı kullanıcıya sor.
  - **Bayt eşitliği gerçek koşucuya karşı.** `eval/pipeline.py`'yi değiştirmeden önce eski koşucunun v0 ve bir v1 projesi için gönderdiği üretim ve sınıflandırma mesajlarını kaydeden bir istemciyle (GPU yok) döküm al (`passages: none` ve `gold`); yeni aşama yolunun mesajlarıyla karşılaştır. Yöntem etiketlerinin sırası: üretici sıralar, referans yöntemler `MethodEdited` ile yazılırken de sıralı olmalı.
  - **İstisnalar.** Üreticiler `LLMError`'ı geçirir; yöntem toplu işlerinde ve bölünmüş birimlerde `asyncio.gather` biri hata verince kardeşleri çalışır bırakır. Dalga sürücüsü iş başına yakalamalı, o düğümleri `failed` işaretlemeli ve hatayı kaydetmeli; tek bir HTTP 400 ücretli bir kolu durdurmamalı.
  - **Çağrı kayıtları.** `CallLog` yalnızca token toplamı taşır. Şema eşiği çağrı başına geçerlilik, D7 süre ister: `eval/` içinde `Complete`'i saran kaydedici (süre, `schema_error`, içerik) `core/`'a dokunmadan ikisini verir. Eski `CallStat` biçimi (`kind`: classification, generation, repair) `LLMRequest.unit` sonekinden türetilebilir (`/full`, `/incremental`, `/merge`, `/repair`, `/retry`).
  - **Kesilme.** `LLMReply` `finish_reason` taşımaz; kesilen çıktı şema hatası gibi görünür ve yeniden deneme aynı kesilmeyi iki kat maliyetle tekrarlar. Paket 1 çağrı başına 15 gereksinimi geçmedi. Paket 1 sonuçlarından test başına çıktı token'ını oku, 25 ve 50'lik birimlerin 8192 token'a sığıp sığmadığını hesapla, D7 kollarında `max_tokens`'ı buna göre ayarla; Pod 1 duman testine en büyük birimli bir çağrı koy. Gerekirse `LLMReply`'ye `finish_reason` eklenir (sözleşme değişikliği, plana yazılır).
  - Adım 7'den önce `make balance` (plandaki 13,55 USD eski olabilir) ve `runpod-kredi-korumasi` skill'i.

## Ölçüm adımında netleşenler (adım 5, 20 Kasım 2026)

- **İhlal ölçütü (kullanıcı onayı, 20 Kasım 2026):** eşik (`no_test_violations`) üreticinin süzmesinden önceki ham model çıktısından sayılır (`all.no_test_violations_raw`, `core.metrics.raw_violations`: şemaya uyan test seti çıktılarındaki `test_cases`, `add`, `update`); son setteki sayı (`all.no_test_violations`) ayrıca raporlanır. Referans kipte son setin ihlali yapısal olarak 0'dır.
- `eval/pipeline.py` yeni aşamalarla çalışır (`Pipeline.run` arayüzü aynı): proje durumu `new_project`, üretim `eval/stage_driver.py` dalga sürücüsüyle. Referans kipte yöntem aşaması bir kez doğrudan koşar (yöntem doğruluğu), sonra referans yöntemler sıralı olarak `MethodEdited` ile yazılır. Öbek adı aşaması ölçümde üretilmez (ölçülen hiçbir şey ona bağlı değil). `prefix_warmup` desteği kalktı (D12: faydasız; ayar `false` kalır).
- **Bayt eşitliği kapısı geçti:** eski koşucu ile yeni koşucunun gönderdiği mesajlar sahte modelle döküldü; v0 (5 proje) ve v1'in ilk projesi, `passages: none` ve `gold`, referans ve uçtan uca kip: 185 isteğin 185'i bayt bayt aynı. Kalıcı test: `tests/test_eval_pipeline.py::test_reference_prompt_is_the_paket1_prompt`.
- Dalga sürücüsü iş başına hata yakalar; hata veren işin düğümleri `failed` olur, hata `errors`'a ve proje kaydına yazılır. `settle`'ın reddettiği sonuç da başarısız sayılır (sonsuz döngü olmasın).
- Çağrı kaydedici (`eval.pipeline.Recorder`): eşzamanlılık sınırı, `CallStat` (tür birim sonekinden: classification, label, generation, repair, incremental, merge), çağrı kaydı (içerik, `finish_reason`, `schema_error`, kullanım), ham çıktılar. `LLMReply`'ye `finish_reason` eklendi (kesilme ile şema hatasını ayırmak için; `ClientComplete` doldurur).
- `core/prompts.TEMPLATE_VERSION` ve `config/pipeline.yaml` `prompt_version` kalktı; `metrics.json` `meta.prompt_versions` (aşama başına) yazar, rapor bunu gösterir (eski koşular için `template_version`).
- Altın parçalar `eval.pipeline.gold_passages` (kimlik, metin); `tests/test_golden_v1.py` eski `Pipeline.passages` yerine bunu çağırır, beklenti aynı.
- **Kesilme ve D7 kolları.** Paket 1 v1 koşusunda Test gereksinimi başına ~624 çıktı token'ı (2,19 test, test başına ~285 token) düştü. 25 Test gereksinimlik birim ~15,6 bin token ister ve `max_tokens: 8192`'yi aşar; 50'lik birim ~31 bin token ister ve 32 bin bağlama (prompt dahil) sığmaz. Bu yüzden **50 kolu çıkarıldı**; D7 kolları `d7-cluster` (öbek başına çağrı, karşılaştırma tabanı), `d7-unit1`, `d7-unit10`, `d7-unit25`, hepsi `max_tokens: 16384` (yalnızca kesilmede çıktıyı etkiler; kollar arasında tek değişken birim kalır). Küçük referans öbekleri referans sırasıyla birim sınırına kadar birleştirilir (`unit_packing: true`, `eval.pipeline.pack_units`). Çalışma varsayımı (25, 8192) gerçek kullanımda ~13'ten fazla Test üyeli öbekte kesilme riski taşır; D7 sonucu `max_tokens`'ı da kapsayacak şekilde tabloya yazılır. Kesilen çıktı (`finish_reason == "length"`) yeniden denenmez (aynı prompt yine kesilir), düğüm başarısız olur.
- **Tekrar eden test oranı** (`core.metrics.duplicate_tests`, `all.duplicate_test_rate`): aynı projede `covers` kümesi aynı ve adım kelimelerinin Jaccard'ı ≥ 0,8 olan çiftlere giren testlerin payı; çift sayısı ayrıca.
- **D8 eşleştirilmiş kollar.** Taban proje başına bir kez üretilir; her kol aynı değişikliği tabanın bir kopyasına uygular (`eval/scenarios.py`, deney anahtarı `scenario: {kind, min_test_members, arms}`). Bunun için üretim biçimi ayarları (`generation.regeneration: incremental | full`, `generation.prune_removals`) `input_hash`'e girmez; tasarımın "üretim biçimi hash'e girmez" kuralı (`core/stages/base.py`) ve bağlayan test (`test_production_mode_settings_stay_out_of_the_hash`). Birleştirme kolu kaynak setlerin verilip verilmemesidir (`merge_sources`). Planın altı D8 deneyi üçe indi (`d8-add`, `d8-remove`, `d8-merge`); maliyet yaklaşık yarıya iner, karşılaştırma aynı setler üzerinde yapılır. Ekleme senaryosunda ayrılan üyeler Test olmayan yöntemle bir `park` öbeğinde bekler (çağrı gerektirmez); çıkarmada çıkan üye yöntemi Test dışına alınarak `park`'a taşınır (bu yüzden katman 1 kapsaması çıkarma koşusunda referansa göre düşük görünür; D8 ölçütü değildir). Korunma oranı başlık ve adım metninin benzerliğiyle (≥ 0,9, `difflib`) ölçülür; çıkarmada yalnızca çıkan gereksinimi kapsayan testler paydaya girmez. Kol başına son setler `scenario_project` kayıtlarıyla yazılır (hakem adım 8'de kol başına puanlar); proje kaydı ve katman 1 ilk kolu (çalışma varsayımı) kullanır.
- Deneyler: `p3-v0-reference` (×3), `p3-v0-predicted`, `p3-v1-reference`, `p3-v1-predicted`, D7 dört kol, D8 üç kollu deney; duman testi `p3-smoke-v0`, `p3-smoke-v1` (ETC uçtan uca), `p3-smoke-unit25` (KDH, en büyük birim, kesilme denetimi), `p3-smoke-d8` (ETC ekleme). Batch'ler `config/batches/paket3-smoke.yaml` (`max_hours: 0.5`) ve `paket3.yaml` (`max_hours: 2`). Hepsi sahte modelle uçtan uca kuru koşturuldu, hatasız.
- Süre tahmini (paket 1 v1: 109 çağrı 411 sn, ~408 çıktı token/sn): bitti koşuları ~18 dk, D7 ~30 dk (büyük birimlerde süre en uzun çağrıya bağlı: ~16 bin token tek akışta ~7–8 dk), D8 üç deney × (taban ~7 dk + iki kol) ~35–40 dk; toplam ~1,4 saat + hazır olma ~10 dk.

## Pod öncesi kontroller (adım 7 öncesi, 20 Kasım 2026)

- **D6 eşiği geri alındı:** 0,30 gereksinim bootstrap'ında ölçülebilir fark vermedi (ETC [0, +0,17], KDH [0, +0,13]; v0'da kötü); 0,35 kalır, 0,30 aday (`docs/deneyler/D6.md`).
- **`max_tokens`.** Paket 1'in 240 üretim çağrısında çıktı ≈ 538 + 382 × (çağrıdaki Test üyesi) token (artık sapma 526; en kötü oran gereksinim başına ~650). Uçtan uca v1'de öbekler 24'e, D8 birleştirmede Test üyesi 20'ye, D7 25'lik birimde 25'e çıkıyor: 8192 yetmez. `generation.max_tokens: 16384` (pipeline.yaml), D7 kolları 20480; prompt + `max_tokens` 32k bağlamın altında. `max_tokens` yalnızca kesilmede çıktıyı etkiler (paket 1'de kesilme 0), taban karşılaştırması bozulmaz.
- Duman testi sırası: önce en büyük birim (kesilme), sonra D8 artımlı, sonra uçtan uca ve v0; `max_hours: 0.6` (dört adım + ~10 dk hazır olma). Üst sınırlar toplamı 0,6 × 2,69 + 2 × 2,69 = 6,99 USD (bütçe 7 USD). Pod 2'ye geçme koşulu: `finish_reason: length` yok, proje ve senaryo kayıtlarında `errors` boş, `TestCaseDelta` çağrıları şemaya uyuyor, adım süreleri 2 saate sığıyor. Pod 2 uzarsa önce `d8-merge` çıkarılır; `make extend` bütçeyi aşacağından kullanıcıya sorulur.
- `eval/run.py` kayıtları metriklerden önce yazar (metrik ya da rapor hatası ücretli üretimi kaybettirmez); `main()` sahte modelle düz ve senaryo deneyinde uçtan uca test edildi, yargıç yükleyicisi çıktıyı okuyor (`tests/test_scenarios.py::test_runner_main_writes_outputs_metrics_report`).
- D8 projeleri sırayla koşar (bir projenin değişiklik aşaması diğerinin tabanıyla örtüşmesin); kollar sabit sırada, maliyet ölçütü önce çıktı token'ı ve çağrı sayısı, süre ikincil.
- Süreç notu: D7/D8 tasarım satırı değişikliği (`0e54a54`) ilgili kod commit'inden (`547e6af`) sonra geldi; kural tasarımın önce güncellenmesini ister.
