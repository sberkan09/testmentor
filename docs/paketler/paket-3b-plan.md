# Paket 3b planı: dejenere uzun girdi (KDH-030)

Tarih: 21 Kasım 2026. Paket 3'ün açık bulgusunu kapatan küçük iş. Dal: `claude/tender-knuth-ouy8ft`.

## Sorun

Altın set v1'de tek üyeli öbek KDH-030 ("When verifying a company representative's password, VBP shall request the password in full … without truncating it"): model "uzun parolanın tam doğrulanması" sınır testinde `test_inputs` alanına bitmeyen bir dizi yazıyor (`A1b2C3d4…`). Paket 3'te bu öbeğin göründüğü beş koşunun üçünde çıktı `max_tokens`'ta (16.384 / 20.480) kesildi; tek çağrı 472 sn'ye kadar sürdü, düğüm başarısız oldu, öbek kapsanmadı. Kapsama eşiği (%100) bu yüzden tekrarlanan bir koşuda rastgele kaçabilir (`d7-cluster` 0,996).

## Düzeltme

İki katman, biri diğerini yedekler:

1. **Prompt kuralı** (test seti katman 3, `GENERATION_INSTRUCTION`): uzun ya da tekrarlı girdi değerleri yazılmaz, tarif edilir ("129 karakterlik parola", "10 MB'lık dosya"). Modelin davranışını düzeltir.
2. **Alan uzunluk sınırı** (çıktı şeması, `maxLength`): `config/pipeline.yaml` `generation.field_max_chars`; şema `pydantic` modelinden türediği için JSON şemasına `maxLength` olarak girer. vLLM'in yapılandırılmış çıktısı (xgrammar, desteklemediğinde guidance) sınırı üretim sırasında uygular; uygulamazsa `pydantic` doğrulaması şema hatası verir ve tek yeniden deneme hata mesajıyla yapılır. Dejenere bir alan böylece en çok birkaç yüz token'da durur.
   - Sınırlar gözlemden: paket 1 ve 3'ün 7.374 testi ve 14.187 adımında en uzun değerler başlık 168, ön koşul 485, test girdisi 332, varsayım 1.478, adım işlemi 257, beklenen sonuç 3.051 karakter. Seçilen: başlık 300; ön koşul, test girdisi, adım işlemi 1.000; varsayım, beklenen sonuç 4.000. Normal çıktılar etkilenmez.
   - Sınır yalnızca model çıktı şemasındadır; kullanıcının düzenlediği test durumu (`TestCaseContent`) sınırsızdır.

Sürüm: test seti şablonu `g3` → `g4` (`core/prompts.STAGE_VERSIONS`), `RENDER_HASHES`'e yeni satır. Parmak izi şema ve talimatı kapsadığı için tüm test setleri bayatlar ("Prompt ya da model sürümü değişti" satırı). Paket 1 tabanıyla bayt eşitliği bu sürümle biter; bundan sonraki karşılaştırma tabanı paket 3 koşularıdır (`p3-v1-reference`, `p3-v0-reference`).

## Doğrulama

Birim testleri (model yok): şemada `maxLength` alanları ayardan gelir; sınırı aşan çıktı şema hatası olur ve yeniden denenir; talimat yeni kuralı içerir; sürüm `g4` ve çizim hash'i; ayar değişince yalnızca test setinin sürümü değişir. `make test`, `make lint`.

GPU (`make batch BATCH=paket3b`, RTX PRO 6000, 2,69 USD/saat, `max_hours: 0.75`, üst sınır 2,02 USD):

- `p3b-kdh` : KDH (120 gereksinim), referans girdiler, 3 tekrar. Geçme: üç tekrarda da kesilme 0, KDH-030 kapsanmış, şema ≥ 0,99.
- `p3b-v1-reference`: v1 referans, tek koşu. Geçme: katman 1 eşikleri; `p3-v1-reference`'a göre eşleştirilmiş check_recall farkının alt sınırı ≥ −0,05 (`python -m eval.paired`); test girdisi alanlarında sınıra dayanan değer sayısı raporlanır.

Beklenen süre ~25 dk (hazır olma ~5 dk, KDH 3 × ~4 dk, v1 ~7 dk), ~1,1 USD. Bakiye 8,65 USD. Pod açılmadan önce kullanıcı onayı alınır; açılışta fiyat, bekçi son tarihi ve bakiye yazılır; iş sonunda `get-pod` 404 ve `list-pods` boş doğrulanır, doğrulama defteri güncellenir.

## Kapsam dışı

Motor tarafında tekrar cezası (çıktıyı genel olarak değiştirir, ayrı deney ister). Sınır testi kalitesi (paket 1'den beri sınır kapsaması 0,19) ayrı prompt deneyidir.

## Sonuç (22 Kasım 2026)

Koşular: [`p3b-kdh`](../../results/20261122-085220-p3b-kdh/report.md) (KDH × 3), [`p3b-v1-reference`](../../results/20261122-090504-p3b-v1-reference/report.md). Pod `qo96f4iin3ii3s`, 0,36 saat, ≈ 0,96 USD, silindi (404).

| ölçüt | sonuç | durum |
| --- | --- | --- |
| KDH × 3: kesilme 0, KDH-030 kapsanmış, şema ≥ 0,99 | 213 çağrıda kesilme 0, şema hatası 0; KDH-030 üç tekrarda da 3'er testle kapsandı; kapsama 1,0 | ✓ |
| v1 referans: katman 1 eşikleri | şema 1,0, kapsama 1,0, adım yapısı 1,0, ham ihlal 0; 109 çağrıda kesilme 0 | ✓ |
| v1 referans: `p3-v1-reference`'a göre eşleştirilmiş fark ≥ −0,05 | 0,432 − 0,449 = −0,017 [−0,048, +0,012] | ✓ |
| KDH × 3: `p3-v1-reference`'ın KDH gereksinimlerine göre | 0,456 − 0,470 = −0,015 [−0,047, +0,017] | ✓ |

- Düzeltmeyi prompt kuralı sağladı: model sınır testinde parolayı yazmak yerine tarif ediyor ("65 karakterlik tam doğru parola", "Kayıtlı 64 karakterlik parola"). Hiçbir alan sınıra yaklaşmadı (en uzun test girdisi 190, ön koşul 305 karakter); motorun `maxLength`'i üretimde uygulayıp uygulamadığı bu yüzden gözlenmedi, sınır yedek olarak durur (uygulanmazsa şema hatası ve tek yeniden deneme; birim testiyle bağlı).
- Fark gürültü aralığında: aynı ayarlı iki g3 koşusu (`d7-cluster`, `p3-v1-reference`) arasında −0,023 [−0,051, +0,006] görülmüştü. Türkçe recall 0,406 → 0,348 da bu aralıkta (`d7-cluster` Türkçe 0,348).
- Şablon g4 bundan sonra çalışma varsayımıdır; karşılaştırma tabanı `p3b-v1-reference` (v1) ve `p3-v0-reference` (v0, g3; v0'da g4 ölçülmedi).
