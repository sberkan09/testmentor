# p3b-kdh

- Soru: Paket 3b (KDH-030): alan uzunluk sınırı ve uzun girdiyi tarif etme kuralıyla (şablon g4) KDH referans, 3 tekrar; kesilme 0, KDH-030 kapsanmış, şema ≥ 0,99.
- Değişken: test seti şablonu g4 (field_max_chars + kural)
- Koşu: `20261122-085220-p3b-kdh`, ayar `config/experiments/p3b-kdh.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g4+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `qo96f4iin3ii3s`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 120 | 1 | 1 | 1 | 0 | 0 | 1 | 274 | 0.4417 | 0.6667 | 0.0876 |
| en | 60 | 1 | 1 | 1 | 0 | – | 1 | 158 | 0.5667 | 0.75 | – |
| tr | 60 | 1 | 1 | 1 | 0 | – | 1 | 116 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3355
- Çağrı: 71, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 283.47 sn, öbek başına 12.32 sn, 315.5 çıktı token/sn, toplam 194796 token, önek cache isabeti 0.5133
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 2

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 120 | 1 | 1 | 1 | 0 | 0 | 1 | 247 | 0.4417 | 0.6667 | 0.1053 |
| en | 60 | 1 | 1 | 1 | 0 | – | 1 | 156 | 0.5667 | 0.75 | – |
| tr | 60 | 1 | 1 | 1 | 0 | – | 1 | 91 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3355
- Çağrı: 71, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 232.69 sn, öbek başına 10.12 sn, 353.1 çıktı token/sn, toplam 187518 token, önek cache isabeti 0.6633
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 3

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 120 | 1 | 1 | 1 | 0 | 0 | 1 | 258 | 0.4583 | 0.6694 | 0.0853 |
| en | 60 | 1 | 1 | 1 | 0 | – | 1 | 156 | 0.5667 | 0.75 | – |
| tr | 60 | 1 | 1 | 1 | 0 | – | 1 | 102 | 0.35 | 0.5889 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3355
- Çağrı: 71, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 243.35 sn, öbek başına 10.58 sn, 352.6 çıktı token/sn, toplam 191162 token, önek cache isabeti 0.6633
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Tekrar karşılaştırması (katman 1)

- all.duplicate_pairs: 15 → 22
- all.duplicate_test_rate: 0.0876 → 0.1053
- all.test_cases: 274 → 247
- by_language.en.test_cases: 158 → 156
- by_language.tr.test_cases: 116 → 91

## Hakem (katman 2)

- check_recall: 0.4611
- en: 0.5448
- tr: 0.4011

