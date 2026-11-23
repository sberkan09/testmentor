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

## Uygulamada netleşenler

(doldurulacak)
