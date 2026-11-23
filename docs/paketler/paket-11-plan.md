# Paket 11 planı: D10 (sızıntısız örnek havuzu) ve D9 reranker kolu

23 Kasım 2026. Model: Opus. Bu oturumda (ücretli GPU yalnızca ana oturumda). Tasarım: Örnek havuzu ve İndeks bölümleri, Deney planı D9 ve D10 satırları.

## Kapsam

1. **Ürün kuralı** (`services/kb_examples.py`): havuz girdisi kapsadığı gereksinim kimliklerini taşır; bir öbeğe seçim, öbeğin üyelerini kapsayan girdileri dışlar (onlar sabit test olarak zaten prompt'ta). Birim testi.
2. **Ölçüm havuzu** (`eval/`): altın setin referans denetimlerinden (`reference_checks`, `reference_preconditions`) proje başına test durumu havuzu. Hedef öbek için dışlama: öbeğin bir üyesini kapsayan ya da bir üyeyle `reference_candidates` paylaşan gereksinimin testi. Koşu, her öbek için seçilen örneklerle öbek üyeleri arasında kimlik ve kaynak örtüşmesinin sıfır olduğunu doğrular (değilse hata) ve öbek başına seçilen örnek anahtarlarını çıktıya yazar.
3. **Deneyler** (`config/experiments/`), hepsi altın set v1, `passages: index`, `top_k: 4` (D9 kararı):
   - `d10-base`: `kb.examples: 0` (aynı batch'teki taban)
   - `d10-ex2`: `kb.examples: 2`
   - `d10-ex4`: `kb.examples: 4`
   - `d9-rerank`: `kb.reranker: BAAI/bge-reranker-v2-m3`, aday 3 × 4 (CPU; resmî BAAI hesabı, indirme ve puanlama 23.11'de doğrulandı: yükleme 47 sn, 12 çift 3,8 sn)
4. **Üslup uyumu yaklaşığı** (`eval/`): üretilen ve referans testlerde adım sayısı ve beklenen sonuç uzunluğu; kol başına referansa uzaklık. Hakem puanının yanında raporlanır.
5. **Batch** `config/batches/paket11.yaml`, sabit commit'li ayrı çalışma ağacından. Önce her kol sahte modelle uçtan uca (GPU'suz) koşar.

## Karar kuralı

Eşleştirilmiş bootstrap (`eval/paired.py`), taban `d10-base`. Aralık sıfırı dışlamıyorsa basit ve ucuz olan kalır (`examples: 0`, `reranker: none`). Kazanan kol tek satırlık ayar değişikliğiyle (`config/pipeline.yaml`) uygulanır.

## Bütçe

Dört kol × ~7–8 dk + hazır olma ~5 dk + reranker CPU süresi: ~45 dk, ~2 USD (2,69 USD/saat). `max_hours: 1.25`. Hakem ayrı.

## Bitti ölçütü

Kollar aynı batch'te taban koluyla koşuldu, `docs/deneyler/D10.md` ve D9 ek bölümü yazıldı, tasarım tablosu ve ayarlar güncellendi, pod silindi ve defter satırı yazıldı.

## Tekrarlı ölçüm (paket 11b, pod açılmadan önce yazıldı)

İlk batch'te (pod `2muhu5folo55ck`) 4 örnek tabana göre +0,046 [+0,009, +0,083] verdi. Ancak aynı ayarla koşan iki taban (D9 `d9-top4` 0,518 ve `d10-base` 0,484) birbirinden −0,035 [−0,064, −0,004] farklı çıktı. Getirilen parçalar 98 öbeğin 97'sinde aynı, şablonlar aynı, sıcaklık 0. Fark üretimin koşudan koşuya oynamasından (vLLM toplu işleme sayısal farkları) ve onu izleyen hakem kararlarından geliyor. Gereksinim düzeyindeki bootstrap bu oynamayı içermiyor.

Bu yüzden 0 ve 4 örnek ayrıca 3'er tekrarla koşar (`d10-base-r3`, `d10-ex4-r3`, batch `paket11b`).

**Karar kuralı.** 4 örnek ancak iki koşulun ikisi de sağlanırsa açılır:

1. Kol ortalamaları farkı, kollar içindeki en geniş tekrar aralığından (en yüksek − en düşük tekrar) büyük olmalı.
2. Tüm tekrarları birleştiren eşleştirilmiş bootstrap aralığı sıfırı dışlamalı.

Aksi halde `kb.examples: 0` kalır. Reranker kararı (kapalı) bu ölçümü beklemez: tek koşuda bile tabana göre sıfırı kapsıyor ve aynı ayarlı eski tabana göre −0,017.

Bütçe: 6 koşu × ~7 dk + hazır olma, ~45 dk, ~2 USD.

## Uygulamada netleşenler

- Reranker CPU'da öbek başına ~13 sn (512 token sınırıyla 12 çift); 98 öbek ~19 dk. Kol batch'te ilk sırada koştu (1466 sn).
- Sunucu sabitlenen testleri havuza hiç yazmıyordu; `services/kb_example_sync.py` eklendi (tasarım, Örnek havuzu).

## Sonuç

- Tekrarlı ölçüm: taban 0,489 / 0,482 / 0,515, 4 örnek 0,543 / 0,540 / 0,551. Fark +0,050, en geniş kol içi aralık 0,033, birleşik eşleştirilmiş aralık [+0,025, +0,074]. Kuralın iki koşulu da sağlandı: `kb.examples: 4`.
- Reranker kapalı kalır. Rapor: [D10](../deneyler/D10.md), [D9](../deneyler/D9.md) paket 11 bölümü.
- Maliyet: pod `2muhu5folo55ck` 0,81 saat ≈ 2,17 USD, pod `ojij9aaejbqad2` 0,75 saat ≈ 2,01 USD. Bakiye 17,74 → 13,68 USD.
