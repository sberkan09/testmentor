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
