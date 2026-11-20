# d12-no-warmup

- Soru: D12 Önek ısıtma: paralel çağrıları bekletmeden gönder (varsayım: ilk çağrı öneki işleyene kadar beklet). Taban: d2-qwen.
- Değişken: prefix_warmup=false
- Koşu: `20261119-183002-d12-no-warmup`, ayar `config/experiments/d12-no-warmup.yaml`, şablon `t1`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 0.9459 | 0.9189 | 0 | 1 | 60 | 0.725 | 0.8 |
| en | 20 | 0.8889 | 0.8889 | 0 | 1 | 24 | 0.6 | 0.7 |
| tr | 20 | 1 | 0.9474 | 0 | 1 | 36 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 3 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 22, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 66.04 sn, öbek başına 1.94 sn, 325.9 çıktı token/sn, toplam 47253 token, önek cache isabeti 0.5496
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✗, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 2

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 0.9189 | 0.9189 | 0 | 1 | 58 | 0.75 | 0.8125 |
| en | 20 | 0.8889 | 0.8889 | 0 | 1 | 25 | 0.55 | 0.65 |
| tr | 20 | 0.9474 | 0.9474 | 0 | 1 | 34 | 0.95 | 0.975 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 22, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 73.88 sn, öbek başına 2.17 sn, 278.9 çıktı token/sn, toplam 46321 token, önek cache isabeti 0.5501
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✗, step_structure_rate ✓, no_test_violations ✓

## Tekrar karşılaştırması (katman 1)

- all.coverage_rate: 0.9459 → 0.9189
- all.method_exact_match: 0.725 → 0.75
- all.method_jaccard: 0.8 → 0.8125
- all.test_cases: 60 → 58
- by_language.en.method_exact_match: 0.6 → 0.55
- by_language.en.method_jaccard: 0.7 → 0.65
- by_language.en.test_cases: 24 → 25
- by_language.tr.coverage_rate: 1.0 → 0.9474
- by_language.tr.method_exact_match: 0.85 → 0.95
- by_language.tr.method_jaccard: 0.9 → 0.975
- by_language.tr.test_cases: 36 → 34
- traps.test_cases: 3 → 1

