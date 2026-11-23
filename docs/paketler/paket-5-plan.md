# Paket 5 planı: orkestratör ve kuyruk

23 Kasım 2026. Model: Opus. Sözleşme: `worker/contracts.py` (`ProjectService`, komutlar, olaylar, görünümler); değiştirilmez. Bitti ölçütü (tasarım, 23 Kasım güncellemesi): taşıma senaryosu bir artımlı test ve iki ad çağrısıyla bitiyor, diğer öbekler cache'ten geliyor; geri alma cache'ten dönüyor.

Okunacaklar: `docs/tasarim.md` (Veri modeli kuralları, İş kuyruğu, Aşama kapıları, Sunucu mimarisi ve API, Çok kullanıcılı çalışma), `core/invalidation.py` (`apply`, `settle_many`, `Invalidation.cancel`, `hints`, `APPROVAL_EVENTS`), `core/store.py`, `core/stages/base.py`, `eval/stage_driver.py` (dalga sürücüsü; kuyruk onun yerini alır).

## Kapsam

- `worker/store_pg.py`: `PostgresStore` (`core.store.NodeStore` ve `OutputCache`): düğümler ve sürüm geçmişi (eklemeli), çıktı cache'i, olay günlüğü (`seq`, aktör, olay JSON), iş kayıtları. Şema `worker/schema.sql` (idempotent). `psycopg` 3. Sürüm denetimi `VersionConflict` ile.
- `worker/queue.py`: öncelikli iş kuyruğu: P0 (odaktaki düğümler, `Focus` komutu ve `Regenerate`), P1 (kullanıcının tetiklediği), P2 (otomatik); `debounce_s` bekleme (art arda komutlar tek işe iner); aynı düğüm için bekleyen iş yenisiyle değişir; eşzamanlılık `concurrency`, P2 en çok `p2_share`; çalışan işin girdisi ya da bağlamı değişince (`Invalidation.cancel`) iş iptal edilir (asyncio görevi iptal; `ClientComplete` akışı keser).
- `worker/runtime.py`: `ProjectRuntime`: bellekteki `ProjectState`, depo, `Complete`, `Embed`, `Retrieve`/`PassageSource` (varsayılan yok; paket 7 bağlar), `StageSettings`, aşama ayarları. Komut → doğrulama → çekirdek olayı (`apply`) → depo (tek işlem) → bayatlayanlar → aşama otomatikse kuyruğa → `ServerEvent`'ler. İş: önce `OutputCache` (cache anahtarıyla; isabet model çağırmadan `settle`), yoksa üretici (`StageSpec.produce`, `ProduceContext` ipucu ve birleştirmede kaynak setlerle: kaynaklar depo geçmişinden), sonuç cache'e ve `settle_many`; reddedilen sonuç yalnızca cache'e. Toplu aşamalar (embedding, yöntem, matris) hazır düğümleri tek işte toplar.
- Aşama kapıları: aşama başına `auto` / `approval` (varsayılan `auto`); `APPROVAL_EVENTS` (kart, aşama ayarı) bayatlattıklarını onay bekletir. `approve_stage` kuyruğa alır. `stage_waiting_approval` olayı.
- Geri alma: kullanıcı başına yığın. Her geri alınabilir komut, etkilediği kaynak düğümlerin (öbek üyelikleri, gereksinim metni, yöntem düzenlemesi, test durumu düzenlemesi, sabitleme, ad) önceki içeriğini kaydeder; geri alma bunu yeni olaylarla geri yazar (sürüm artar, geçmiş silinmez; tasarım: "geri alma sürüm değiştirmektir"). Türev düğümler beklenen hash'leri eskiye döndüğü için cache'ten gelir.
- `worker/service.py`: `ProjectService` gerçeklemesi: projeler bellekte ve depoda; açılışta depodan yükleme; olay halkası (`event_buffer`), `events_after`, `subscribe` (asyncio kuyrukları; `job_progress` yalnızca canlı), kilit (`lock_s`, komutlar kilitli düğümü başka kullanıcıya reddeder), `snapshot` (`core.matrix_view.matrix_rows` paket 4'ten; yoksa paket 4 birleşene kadar boş matris ve bir TODO testi), `create_project` paket 4'ün `services.importer.build_project`'ini çağırır, `matrix_xlsx` paket 4'ün dışa aktarımını.
- Ayarlar `config/runtime.yaml` `orchestrator:` bölümünden.

Dışında: HTTP ve WebSocket (paket 6), bilgi havuzu (paket 7), arayüz (paket 8).

## Testler (önce yazılır; model yok, `services.fake_llm`)

- **Bitti testi** `tests/worker/test_move_scenario.py`: üretilmiş bir proje (her düğüm taze) → `move_requirement` R2 A→B → kuyruk boşalınca model çağrıları: tam olarak bir `TestCaseDelta` (B) ve iki `ClusterLabel` (A, B); A'nın seti çağrısız budanır (`prune_removals`); diğer öbeklerde çağrı yok → `undo` → model çağrısı yok (hepsi cache), içerik hash'leri taşımadan önceki haliyle aynı.
- Kuyruk: öncelik sırası, P2 payı, bekleme sırasında art arda komutların tek işe inmesi, aynı düğüme yeni işin eskisinin yerini alması, çalışan işin girdisi değişince iptal ve sonucun yalnızca cache'e yazılması.
- Aşama kapısı: onaylı modda iş beklemesi ve `approve_stage`; kart değişikliğinin onay istemesi.
- Çok kullanıcı: eski sürümle gelen komutun reddi (`version_conflict`, güncel sürümler), kilit.
- `PostgresStore`: düğüm, geçmiş, cache, olay, iş gidiş-dönüşü; süreç yeniden başlayınca proje depodan aynı durumla yüklenir. Postgres testleri `tests/worker/conftest.py` içindeki bir fixture ile: `TESTMENTOR_PG_DSN` varsa onu, yoksa `/usr/lib/postgresql/*/bin/initdb` ile geçici küme açar; ikisi de yoksa atlanır. `make pg-test` hedefi eklenir.

## Kurallar

Ücretli kaynak ve hakem yok. `core/` değişikliği gerekirse önce `docs/tasarim.md` (ayrı commit). `make test`, `make lint` yeşil. Tasarım kuralı gereği paket 5'in kodu ayrı bir Opus incelemesinden geçer (bu oturum yapar).
