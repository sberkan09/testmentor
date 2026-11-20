# Paket 2 planı: çekirdek (veri modeli, hash, bağımlılık grafiği, geçersiz kılma)

Tarih: 20 Kasım 2026. Model: Opus. Dal: `claude/tender-knuth-ouy8ft` (main'e, `306374c`, hızlı ileri alındı). Önkoşul: paket 1b birleşti (PR #3).

## Bağlam

`docs/paketler/` altında paket 2 görev tanımı yok; bu dosya hem kapsamı hem planı tutar. Bitti ölçütü `docs/tasarim.md` Geliştirme planından gelir: **bayatlama tablosundaki her satırın birim testi geçiyor.** Paket 3 (aşamalar), 4 (matris), 5 (orkestratör), 7 (bilgi havuzu) bu paketin arayüzlerini içe aktarır; sistemin doğruluğu bu pakete bağlıdır.

Tasarım okunurken bayatlama tablosunu bozan çelişkiler bulundu. Kullanıcı kararları (20 Kasım 2026) aşağıda; kod yazılmadan önce `tasarim.md` ayrı commit'le güncellenir.

Maliyet: 0 USD. Pod açılmaz; model çağrısı yok, testler sahte üreticiyle çalışır.

## Kapsam

İçinde:
- Düğüm tipleri ve ortak alanlar (pydantic v2), düğüm başına hash girdileri.
- Aşama kayıt arayüzü (`core/stages/`): her aşama düğüm tipini, bağımlılıklarını, bağlamını ve model çağırıp çağırmadığını bildirir. Bu pakette yalnızca bağımlılık bildirimleri yazılır, üretim fonksiyonları yazılmaz.
- Olay modeli (`requirement_moved`, `cluster_created` ...) ve olaydan bayatlama hesabı.
- Sabitleme, sürümleme, çıktı cache'i, sürüm denetimi (CAS) içeren depo arayüzü; bellek içi uygulama ve depo sözleşme testleri.

Dışında:
- Prompt'lar, üretim fonksiyonları, öbekleme kesimi (paket 3).
- Postgres şeması (DDL) ve bağdaştırıcı (paket 5; aynı sözleşme testlerini geçmek zorunda).
- Kuyruk, öncelik, bekleme, iptal yürütme, aşama kapıları (paket 5). Matris SQL ve xlsx (paket 4). Parçalama ve arama (paket 7). REST, WebSocket, kilit (paket 6).

## Kullanıcı kararları (20 Kasım 2026)

| Soru | Karar |
| --- | --- |
| Kalıcı depo | `core/` içinde `NodeStore` Protocol, bellek içi uygulama ve sözleşme testleri. Postgres paket 5'te. |
| Test seti doğrulama yöntemine bağlı mı | Evet. Paket 1'de ölçülen pipeline (`core/prompts.py` `generation_messages`) yöntemi prompt'a veriyor; veri modeli tablosu güncellenir. Elle değişen yöntem öbeğin setini bayatlatır. |
| Öbek adı neye bağlı | Üye kimlik ve metinlerine. Tablo tutarlı hale getirilir: metin değişikliği, silme ve birleştirme satırlarına ad çağrısı eklenir. |
| Arama sorgusunda öbek adı | Yok, sorgu yalnızca üye metinleri. Yeniden adlandırma gerçekten 0 çağrı; adın faydasını paket 7 / D9 ölçebilir. |

## Tasarım netleştirmeleri (`tasarim.md`, ayrı commit, koddan önce)

1. **Düğüm tipleri.** Öbek ikiye ayrılır: *öbek* (üyelik; algoritma ya da kullanıcı) ve *öbek adı* (model; ad ve gerekçe). *Arama sonucu* düğümü eklenir (girdi: üye metinleri ve indeks sürümü; çıktı: sıralı parça kimlikleri). *Test durumu* kendi düğümüdür, *test seti* durumların sıralı listesini tutar. Sabitleme test durumu başınadır (prompt'a "sabitlenmiş test durumları" olarak giden birim zaten budur).
2. **İki anahtar.** `input_hash` yalnızca bağımlılıklardan çıkar ve bayatlığı belirler. Bağlam (sabit test durumlarının içeriği, kullanıcının ek talimatı) bayatlatmaz, ama çıktı cache'inin anahtarına girer: `cache_key = H(input_hash, context_hash)`. Üretim biçimi (artımlı, baştan, birleştirme, onarım; önceki set) hiçbir anahtara girmez, `produced_by` içinde kaydedilir. Böylece elle düzenleme 0 çağrıdır ve taşıyıp geri almak cache'ten döner.
3. **Bayatlık tanımı.** Düğüm bayattır ⇔ kayıtlı `input_hash` ≠ güncel girdilerden hesaplanan beklenen hash. Her olaydan sonra beklenen hash'ler tüm proje için yeniden hesaplanır (2.000 gereksinimde birkaç bin SHA-256; artımlı yayılım optimizasyonu ölçüm gerektirirse yapılır). Ters bağımlılık dizini arayüz ve "doğrulanacak" listesi için tutulur.
4. **Erken kesme.** Modelsiz ucuz düğümün (embedding, arama sonucu) üst girdisi değişince aşağısı hemen bayat sayılmaz, *doğrulanacak* listesine girer; durum alanı `fresh` kalır, düğüm üstü taze olana kadar kuyruğa alınamaz. Ucuz düğüm yeniden hesaplanıp çıktısı aynıysa aşağısı taze kalır. Dört durum (`fresh`, `stale`, `running`, `failed`) değişmez.
5. **Öbekleme.** Üyelik somut durumdur; öbekler ağaca değil üyeliğe bağlıdır. Embedding değişince öbekleme ağacı bayatlar ve arayüzde gösterilir, ama yeniden kesim yalnızca açık komutla (ayrıntı kaydırıcısı, yeniden öbekle) yapılır ve sabit atamaları korur. Aksi halde tek metin değişikliği tüm öbekleri bayatlatabilirdi.
6. **Çalışan düğüm.** Girdisi değişen `running` düğüm `stale` olur ve iptal listesine girer. Eski girdiyle biten sonuç çıktı cache'ine kendi anahtarıyla yazılır, düğüme yazılmaz.
7. **Boşalan öbek.** Son üyesi taşınan öbek silinir; adı, seti ve arama sonucu kaldırılır, model çağrısı yok.
8. **Sayım kuralı.** Tablodaki sayı büyük model çağrısıdır; embedding ayrı sayılır. Sabitlenmiş bayat düğüm çağrı sayısına girmez, uyarı olarak döner.
9. **Prompt ve model sürümü.** Aşama sürümü şablonla birlikte durur, model kimliği ve üretim parametreleri ayardan enjekte edilir; `core/` ayar dosyası okumaz.

### Güncellenmiş bayatlama tablosu

| Olay | Bayatlayan | Model çağrısı |
| --- | --- | --- |
| Gereksinim A öbeğinden B'ye taşındı | A ve B'nin setleri ve adları | 2 artımlı test, 2 ad |
| Öbek yeniden adlandırıldı | hiçbir şey | 0 |
| Öbek silindi, üyeleri dağıtıldı | üye alan öbeklerin setleri ve adları | üye alan öbek başına 1 test, 1 ad |
| İki öbek birleştirildi | yeni öbeğin seti ve adı | 1 test (iki set birleştirilir, model tekrarları ayıklar), 1 ad |
| Gereksinim metni değişti | embedding, doğrulama yöntemi, öbeğin seti ve adı | 3 (yöntem, test, ad) |
| Test durumu elle düzenlendi | yalnızca matris satırları | 0 |
| Bilgi havuzuna belge eklendi | getirilen parçaları değişen öbeklerin setleri | değişen öbek başına 1 |
| Prompt ya da model sürümü değişti | o aşamanın tüm çıktıları, kullanıcı onayıyla | toplu, arka planda |
| Doğrulama yöntemi elle değişti (yeni) | öbeğin seti | 1 |
| Proje kartı değişti (yeni) | projedeki tüm model çıktıları, kullanıcı onayıyla | toplu, arka planda |

Matris satırları her satırda kapsanan gereksinimler için bayatlar ve model çağırmaz.

## Mimari ve dosyalar

| Dosya | İçerik |
| --- | --- |
| `core/nodes.py` | `NodeKind`, `Status`, `Origin`, `NodeRef(project_id, kind, key)`, `NodeHeader` (`input_hash`, `cache_key`, `status`, `pinned`, `origin`, `version`, `produced_by`), düğüm içerikleri. Kimlik üretici enjekte edilir (testler deterministik). |
| `core/hashing.py` | `canonical` ve `input_hash` **değişmez**: hakem cache'i bu çıktıyla anahtarlı (`eval/judge.py:145`). Yeni `plain_hash(obj)`: `default` olmadan JSON; küme ya da numpy dizisi gelirse hata verir. Aşağı akış hash'leri ham vektör yerine üst düğümün hash'ini kullanır. |
| `core/stages/base.py` | `StageSpec`: `kind`, `uses_llm`, `dependencies(state, ref)`, `context(state, ref)`; `StageConfig(prompt_version, model, params)` dışarıdan verilir. Kayıt: `register`, `get`, `all_specs` (deterministik sıralı). |
| `core/stages/{embedding,clustering,cluster_label,retrieval,test_set,method,matrix}.py` | Yalnızca bağımlılık bildirimleri. Test seti: üye `(id, metin hash'i, yöntem çıktısı hash'i)` kimliğe göre sıralı, arama sonucunun parça kimlikleri, proje kartı hash'i. Bağlam: sabit test durumları, ek talimat. |
| `core/events.py` | Olay modelleri: taşıma, öbek oluşturma/silme/birleştirme/adlandırma, metin değişikliği, test durumu düzenleme, yöntem düzenleme, belge ekleme, aşama ayarı değişikliği, kart değişikliği, sabitle/çöz, üyelik değişikliği (paket 3'ün yeniden kesimi bunu kullanır). |
| `core/graph.py` | `ProjectState` (değişmez anlık görüntü), `expected_hashes(state)`, `dependents(ref)`. |
| `core/invalidation.py` | `apply(state, event) -> (ProjectState, Invalidation)`. `Invalidation`: `stale`, `to_verify`, `cancel`, `llm_calls`, `pinned_warnings`, `requires_approval`. `settle(state, ref, output, input_hash, cache_key)`: sonuç yazımı ve erken kesme. `regeneration_plan(state)`: sabitlenmemiş, üstü taze bayat düğümler. |
| `core/store.py` | `NodeStore` Protocol: düğüm sürümleri, `put(expected_version)` ile CAS (`VersionConflict`), sürüm geçmişi, çıktı cache'i (`cache_key`), olay günlüğü; her çağrı `project_id` taşır. `InMemoryStore`. |

Yeniden kullanılanlar: `core/hashing.canonical`/`input_hash`, `core/schemas.Requirement` ve `case_set_model` (test durumu içeriği aynı alanlarla), `core/clustering.ClusterTree` (öbekleme düğümünün çıktısı).

`config/` altına yeni ayar eklenmez: bu pakette ayarlanabilir değer yok. Model kimliği ve parametreler paket 3/5'te `services/settings.py` üzerinden `StageConfig`'e dönüşür.

## Testler (`tests/core/`)

Ortak düzen: proje P, gereksinimler R1–R6, öbekler A{R1,R2}, B{R3,R4}, C{R5,R6}; sahte üreticilerle her şey taze. Her test bayat kümeyi **tam olarak** ve model çağrısı sayısını doğrular.

| Satır | Test | Beklenen |
| --- | --- | --- |
| Taşıma R2: A→B | `test_move_requirement` | set A, set B, ad A, ad B bayat; arama A/B ve matris R1–R4 bayat; 4 çağrı |
| Yeniden adlandırma | `test_rename_cluster` | bayat yok, 0 çağrı; ad yeni sürüm, `origin=edited`, `pinned` |
| Silme, R1→B, R2→C | `test_delete_cluster_distributes` | B ve C'nin set ve adları; 4 çağrı; A'nın düğümleri kalkar |
| Birleştirme A+B→D | `test_merge_clusters` | D'nin seti ve adı; 2 çağrı; bağlamda iki eski set |
| Metin R1 | `test_requirement_text_changed` | embedding R1, yöntem R1, set A, ad A; öbekleme ağacı bayat ama öbekler aynı; 3 çağrı |
| Test durumu düzenleme | `test_test_case_edited` | yalnızca eski ve yeni `covers` gereksinimlerinin matris satırları; 0 çağrı |
| Belge ekleme | `test_kb_document_added` | arama A–C doğrulanacak, setler `fresh`; yalnızca A'nın parçaları değişince set A bayat; 1 çağrı |
| Aşama sürümü | `test_stage_version_changed` | aşamanın tüm düğümleri bayat, `requires_approval`; sabitler uyarıda |

Ek testler: yöntem elle değişti (1 çağrı); kart değişti (tüm model çıktıları, onay); sabit ad taşımada bayatlar ama çağrı sayısına girmez, uyarı döner; taşı ve geri taşı (cache'ten, 0 çağrı); çalışan düğümün girdisi değişir (iptal, eski sonuç düğüme yazılmaz); boşalan öbek; hash determinizmi (üye sırası, sözlük sırası, ad hash'e girmez, sürüm/model/parametre girer, `plain_hash` küme reddeder); depo sözleşmesi (CAS çakışması, sürüm geçmişi, proje yalıtımı) bir depo fabrikası listesiyle parametreli, paket 5'te Postgres eklenir.

## Adımlar

1. Bu planı `docs/paketler/paket-2-plan.md` olarak kaydet, commit.
2. `docs/tasarim.md`: veri modeli tablosu, kurallar, öbekleme, bayatlama tablosu, indeks sorgusu; Geliştirme planında paket 2 satırına "plan: `paket-2-plan.md`". Ayrı commit.
3. Arayüzler ve testler: `core/nodes.py`, `events.py`, `stages/base.py`, `store.py`, `invalidation.py` imzaları; `tests/core/` testleri yazılır, kırmızı. Commit.
4. Uygulama: hash, aşama bildirimleri, grafik, bayatlama, depo; testler yeşil. `make test`, `make lint`. Commit, push.
5. Ayrı Opus oturumunda kod incelemesi (tasarım kuralı: paket 2 ve 5). PR yalnızca istenirse.

## Doğrulama

- `uv run pytest -q --tb=short tests/core` ve `make test`: tümü geçer; tablo testleri satır başına bir test olarak raporlanır.
- `make lint` temiz; `core/` içinde `httpx`, `anthropic`, veritabanı sürücüsü içe aktarımı yok (`grep` ile).
- Mevcut hakem cache'i bozulmadı: `tests/test_judge.py` ve `tests/test_core.py::test_input_hash_changes_with_version_and_params` geçer.
- Ölçek kontrolü (test değil, tek seferlik): 2.000 gereksinim / 100 öbekte `apply` süresi yazdırılır, sonuç plana not edilir.

## Riskler

- Tam yeniden hesap büyük projede yavaş kalırsa ters dizinle artımlı yayılıma geçilir; testler aynı kalır.
- Bağlam ile bağımlılık ayrımı yanlış çizilirse ya elle düzenleme gereksiz çağrı doğurur ya da cache eski sabitlerle üretilmiş seti döner; iki yön de testle bağlanır.

## Arayüz adımında netleşenler (adım 3, 20 Kasım 2026)

- `NodeRef(kind, key)` proje kimliği taşımaz: `ProjectState` tek projedir, depo çağrılarının her biri `project_id` alır.
- Kaynak düğüm tiplerine `PROJECT_CARD` (anahtar `card`) ve `KB_INDEX` (anahtar `index`) eklendi; kart ve indeks sürümü de birer düğümdür ve bağımlılık olarak görünür. Öbek üyeliği (`CLUSTER`) kaynak düğümdür.
- Test durumu düğüm anahtarı `<öbek>:<test kimliği>`; test durumunun üstü kendi setidir.
- Bir düğümü aşağısı, içerik hash'iyle görür. Embedding bayt düzeyinde kararlı olmadığı için beklenen `input_hash`'iyle görünür (`identity_by_input`). Bayat üst düğüm eski içeriğiyle katılır: alt düğüm yalnızca görebildiği bir girdi değiştiyse bayattır, değilse `to_verify` listesine girer.
- `Invalidation` alanları değişiklikten önceki duruma görelidir: `llm_calls`, değişiklikten sonra çağrı gerektiren ve önce gerektirmeyen düğüm sayısıdır. Sabitlemeyi kaldırmak bir çağrı ekler; geri alma sıfıra indirir.
- Üretim ipucu (`Hint`: `full`, `incremental`, `merge` ve kaynak setler) `Invalidation.hints` içinde orkestratöre gider. Birleştirilen öbeklerin eski setleri depo geçmişinden okunur.
- Depo arayüzü: `get_node`, `put_node(expected_version)`, `remove_node`, `history`, `load`, `append_event`, `events`, ve çıktı cache'i için `get` / `put` (`OutputCache`).
- Gözden geçirmeden sonra eklenenler (tasarım commit'i `9897d7f`): düzenleme düğümü güncel hash'le damgalar, bayat düğümü düzeltmek kalıcı uyarı bırakmaz; `node_kept` ("benimkini koru"); silinen ya da birleştirilen öbeğin sabit test durumları kapsadığı ilk gereksinimin öbeğine taşınır (`Invalidation.carried`, çakışmada `<öbek>:<eski öbek>.<kimlik>`); durum değişikliği sürüm yazmaz (`NodeStore.set_status`), silinip yeniden oluşan düğüm 1. sürümden başlar; `mark_failed` ve `Analysis.failed`; matris satırı test durumunu anahtarıyla görür.
- Adım 4 için not: tam yeniden hesap her `settle`'da da çalışır; ölçek kontrolü tek `apply` değil, 2.000 gereksinimin baştan üretim döngüsüyle yapılır.
