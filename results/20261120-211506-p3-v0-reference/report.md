# p3-v0-reference

- Soru: Paket 3 bitti ölçütü: yeni aşama koduyla altın set v0, referans öbek ve yöntemler; katman 1 eşikleri ve paket 1 tabanına (check_recall 0,454) göre gerileme yok.
- Değişken: aşama kodu (generation_inputs=reference)
- Koşu: `20261120-211506-p3-v0-reference`, ayar `config/experiments/p3-v0-reference.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 1 | 0 | 0 | 1 | 61 | 0.775 | 0.8375 | 0.0656 |
| en | 20 | 1 | 1 | 1 | 0 | – | 1 | 28 | 0.6 | 0.7 | – |
| tr | 20 | 1 | 1 | 1 | 0 | – | 1 | 33 | 0.95 | 0.975 | – |
| tuzak | 4 | 1 | 1 | 1 | 0 | – | 1 | 1 | 0.75 | 0.875 | – |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 67.31 sn, öbek başına 1.98 sn, 310.5 çıktı token/sn, toplam 44126 token, önek cache isabeti 0.3582
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 2

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 1 | 0 | 0 | 1 | 64 | 0.7 | 0.7625 | 0.0312 |
| en | 20 | 1 | 1 | 1 | 0 | – | 1 | 30 | 0.55 | 0.625 | – |
| tr | 20 | 1 | 1 | 1 | 0 | – | 1 | 34 | 0.85 | 0.9 | – |
| tuzak | 4 | 1 | 1 | 1 | 0 | – | 1 | 2 | 0.75 | 0.875 | – |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 74.15 sn, öbek başına 2.18 sn, 294.8 çıktı token/sn, toplam 45091 token, önek cache isabeti 0.5373
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 3

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 1 | 0 | 0 | 1 | 64 | 0.775 | 0.8375 | 0.0312 |
| en | 20 | 1 | 1 | 1 | 0 | – | 1 | 28 | 0.65 | 0.725 | – |
| tr | 20 | 1 | 1 | 1 | 0 | – | 1 | 36 | 0.9 | 0.95 | – |
| tuzak | 4 | 1 | 1 | 1 | 0 | – | 1 | 2 | 0.75 | 0.875 | – |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 63.69 sn, öbek başına 1.87 sn, 343.9 çıktı token/sn, toplam 45134 token, önek cache isabeti 0.5373
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Tekrar karşılaştırması (katman 1)

- all.duplicate_pairs: 2 → 1
- all.duplicate_test_rate: 0.0656 → 0.0312
- all.method_exact_match: 0.775 → 0.7
- all.method_jaccard: 0.8375 → 0.7625
- all.test_cases: 61 → 64
- by_language.en.method_exact_match: 0.6 → 0.55
- by_language.en.method_jaccard: 0.7 → 0.625
- by_language.en.test_cases: 28 → 30
- by_language.tr.method_exact_match: 0.95 → 0.85
- by_language.tr.method_jaccard: 0.975 → 0.9
- by_language.tr.test_cases: 33 → 34
- traps.test_cases: 1 → 2

## Hakem (katman 2)

- check_recall: 0.4681
- en: 0.5079
- tr: 0.4359

