# Paket 8 planı: ön yüz

23 Kasım 2026. Model: Sonnet (tuval etkileşimi Opus incelemesiyle). Paket 6'nın sözleşmesine göre (`worker/contracts.py`, `api/schema.json`). Bitti ölçütü (tasarım): kullanıcı bir seti yükleyip düzenleyerek matrisi dışa aktarabiliyor.

Okunacaklar: `docs/tasarim.md` (Stüdyo arayüzü, Sunucu mimarisi ve API, Çok kullanıcılı çalışma), `worker/contracts.py`.

## Kapsam

- `web/`: Vite, React 18, TypeScript katı kip, ESLint. Durum `zustand`; sürükle bırak `@dnd-kit`. Tipler `api/schema.json`'dan (`json-schema-to-typescript`, `npm run types`).
- Bağlantı katmanı (`web/src/api/`): REST istemcisi (`X-User` başlığı; kullanıcı adı ilk açılışta sorulur ve `localStorage`'da tutulur), WebSocket (`after=<seq>`; kopunca üstel geri çekilmeyle yeniden bağlanma; `snapshot` mesajında durumu değiştirme), iyimser güncelleme ve olayla teyit (çelişkide sunucu kazanır), reddedilen komutta bildirim.
- Ekranlar:
  - Proje listesi ve içe alma: dosya (csv, xlsx), kolon eşleme (önizleme ilk 5 satır), ad ve anahtar.
  - Öbek görünümü (2B): öbek kartları (ad, gerekçe, üye çipleri, durum dili), sürükle bırak ve klavyeyle taşıma, öbek oluşturma, silme, birleştirme, yeniden adlandırma, ayrıntı kaydırıcısı (`set_granularity`). Büyük projede yakınlaştırmaya göre ayrıntı.
  - Denetçi (sağ panel): gereksinim (metin düzenleme, yöntem düzenleme), öbek (ad), test durumu (adım adım: her adımın işlemi ve beklenen sonucu ayrı alan; ön koşul, test girdisi, varsayım), sabitleme ve çözme, sürüm geçmişi; düzenlemede kilit.
  - Aşama çubuğu: aşama başına durum sayıları, mod (otomatik ya da onaylı), onayla, kuyruk ilerlemesi; üretilen metin yerinde akar (`job_progress`).
  - Matris görünümü: tablo, filtre (öbek, yöntem, uyarı, kapsama), iki tutarlılık uyarısı, hücreden test durumuna gitme, xlsx indirme.
  - Fark ekranı: sabitlenmiş öğe bayatlayınca (`pinned_warning`): yenisini al (`unpin` + `regenerate`), benimkini koru (`keep_mine`).
  - Geri alma: Ctrl+Z → `undo`.
- Durum dili (tasarım tablosu): taze, bayat (soluk, kesikli çerçeve), üretiliyor, sabit (iğne), hata (kırmızı çerçeve, yeniden dene), kapsanmamış gereksinim (uyarı rozeti).
- Erişilebilirlik: klavye ile taşıma ve odak sırası; metin HTML'de.

## Testler

- Birim: bağlantı katmanı (olay uygulama, yeniden bağlanma, iyimser güncellemenin geri alınması) `vitest`.
- **Bitti testi** `web/e2e/flow.spec.ts` (Playwright, `--trace off`): `TESTMENTOR_FAKE_LLM=1` ile API ve önizleme sunucusu açılır; altın set v0'dan üretilen csv yüklenir → öbekler görünür → bir gereksinim sürüklenip başka öbeğe taşınır → bir test durumunun bir adımı düzenlenir ve sabitlenir → matris görünümünde kapsama görünür → xlsx indirilir ve dosya boş değildir. Bir de iki sekmeli çakışma senaryosu (ikinci sekmede güncel durum görünür).
- `npm run build`, `npm run lint`, `npm test` yeşil; `make web-test` hedefi.

## Kurallar

Ücretli kaynak ve hakem yok. Sözleşme değişmez; eksik görülürse not düşülür (bu oturum karar verir).

## Uygulamada netleşenler

Sözleşme (`worker/contracts.py`, `api/schema.json`) değiştirilmedi. Ön yüzün sözleşmeden okuduğu varsayımlar ve eksikler (paket 6 birleşince doğrulanacak):

- **Düğüm anahtarları.** Gereksinim `requirement:<id>`, öbek `cluster:<anahtar>`, öbek adı `cluster_label:<öbek>`, test seti `test_set:<öbek>`, test durumu `test_case:<öbek>:<id>`, yöntem `method:<gereksinim>`, proje kartı `project_card:card`. `NodeView.content` boş olabilir (üretilmemiş yer tutucu). `embedding` ve `clustering` düğümleri istemcide tutulmaz.
- **Snapshot tüm düğümleri taşır.** Ön yüz matrisi, aşama sayılarını ve kapsamayı düğümlerden türetir (olaylar matris satırı ya da aşama sayısı taşımadığı için). Yalnızca `MatrixRowView.warning` sunucudan gelir: matris etkileyen düğüm olaylarından sonra 800 ms bekleyip `snapshot` yeniden okunur ve yalnızca uyarılar alınır.
- **`job_progress` seq'i.** Kalıcı olmadığı için `seq` ilerletme ve yinelenen-olay denetiminde yok sayılır; metin düğümün (`job.node`) anahtarıyla biriktirilir ve düğüm `node_updated`/`job_done`/`job_failed` ile temizlenir. Sözleşme bu olayın `seq` değerini tanımlamıyor; paket 6 bunu açıkça yazmalı.
- **Boşluklara hoşgörü.** `seq` atlaması hata sayılmaz (yeniden bağlanma protokolü zaten eksikleri getirir); `seq` küçük ya da eşit olay yok sayılır.
- **`command_applied.payload.command`** aşama modu ve onay durumunu güncellemekte kullanılır (`stage_waiting_approval` yalnızca `{"stage": ...}` taşıyorsa yeterli; yük biçimi sözleşmede tanımsız, `payload.stage` varsayıldı).
- **Sürüm geçmişi.** Sözleşmede geçmiş uç noktası yok. Denetçi yalnızca bu oturumda olaylarla görülen sürümleri listeler (sürüm, köken, aktör). Tam geçmiş için `GET /projects/{id}/nodes/{ref}/versions` gibi bir uç nokta sonraki sürüme kalır.
- **Fark ekranı.** `NodeView` bayat sabit öğenin önerilen yeni içeriğini taşımaz; ekran benim sürümümü ve güncel girdileri (kapsanan gereksinim metinleri) gösterir. "Yenisini al" = `unpin` ardından `regenerate`; "benimkini koru" = `keep_mine`; "birleştir" yok.
- **`expected_versions`** yalnızca düzenleme komutlarında gönderilir (`edit_test_case`, `edit_requirement`, `edit_method`, `rename_cluster`); taşıma ve sabitleme gönderilmez.
- **Komut reddi.** 409, 422, 423 yanıtları `CommandResult` gövdesi olarak okunur (`accepted: false`); gövde yoksa HTTP koduna göre `reason` türetilir. `version_conflict` durumunda istemci `snapshot` yeniden okur (sunucu kazanır).
- **`GET /projects`** `[{id, name}]` bekler; `[[id, name]]` (servis çiftleri) de kabul edilir.
- **WebSocket.** `ws(s)://host/projects/{id}/events?after=<seq>&user=<ad>`; `{"type":"ping"}` metin mesajına `{"type":"pong"}` döner (çerçeve düzeyi ping tarayıcıda kendiliğinden yanıtlanır).
- **Kilit.** Metin düzenlemesi başlayınca (taslak oluşunca) `POST /locks` 20 sn aralıkla yenilenir; `lock_changed` olayı ve snapshot `locks` alanı başkasının kilidini gösterir, alanlar devre dışı kalır.
- **Sürüm.** React 18.3.1 (plan), Vite 8, TypeScript 6, Vitest 5; tüm sürümler `package.json` içinde sabit, `package-lock.json` depoda. Playwright tarayıcı yolu `/opt/pw-browsers/chromium-1243` (Playwright'ın beklediği revizyon farklı, config yolu doğrudan verir).
- **Sahte API** (`web/mock/server.mjs`) yalnızca geliştirme ve ön doğrulama içindir; `create_cluster`, `delete_cluster`, `merge_clusters` komutlarını desteklemez (arayüzde bunlar gerçek API ile denenmeli).
- **Katman görünümü (3B)** bu pakette yok (tasarımda en son sıradadır).
