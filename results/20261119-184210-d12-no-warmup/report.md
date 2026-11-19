# d12-no-warmup

- Soru: D12 Önek ısıtma: paralel çağrıları bekletmeden gönder (varsayım: ilk çağrı öneki işleyene kadar beklet). Taban: d2-qwen.
- Değişken: prefix_warmup=false
- Koşu: `20261119-184210-d12-no-warmup`, ayar `config/experiments/d12-no-warmup.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 61 | 0.75 | 0.8125 |
| en | 20 | 1 | 1 | 0 | 1 | 25 | 0.6 | 0.675 |
| tr | 20 | 1 | 1 | 0 | 1 | 36 | 0.9 | 0.95 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 69.54 sn, öbek başına 2.05 sn, 297.6 çıktı token/sn, toplam 43923 token, önek cache isabeti 0.5373
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 2

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 67 | 0.775 | 0.8375 |
| en | 20 | 1 | 1 | 0 | 1 | 29 | 0.65 | 0.725 |
| tr | 20 | 1 | 1 | 0 | 1 | 38 | 0.9 | 0.95 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 2 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 71.92 sn, öbek başına 2.12 sn, 331 çıktı token/sn, toplam 47034 token, önek cache isabeti 0.5373
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Tekrar karşılaştırması (katman 1)

- all.method_exact_match: 0.75 → 0.775
- all.method_jaccard: 0.8125 → 0.8375
- all.test_cases: 61 → 67
- by_language.en.method_exact_match: 0.6 → 0.65
- by_language.en.method_jaccard: 0.675 → 0.725
- by_language.en.test_cases: 25 → 29
- by_language.tr.test_cases: 36 → 38
- traps.test_cases: 1 → 2

## Hakem (katman 2)

- check_recall: 0.4681
- en: 0.4921
- tr: 0.4487

