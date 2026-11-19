# d2-qwen

- Soru: D2 Model: Qwen3.8-27B (FP8). Aynı ayarla iki koşu (tekrarlanabilirlik).
- Değişken: model=qwen3.8-27b
- Koşu: `20261119-182450-d2-qwen`, ayar `config/experiments/d2-qwen.yaml`, şablon `t1`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 0.973 | 0.9189 | 0 | 1 | 61 | 0.75 | 0.8125 |
| en | 20 | 1 | 0.8889 | 0 | 1 | 27 | 0.65 | 0.725 |
| tr | 20 | 0.9474 | 0.9474 | 0 | 1 | 34 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 4 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 22, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 80.59 sn, öbek başına 2.37 sn, 277.7 çıktı token/sn, toplam 48094 token, önek cache isabeti 0.5501
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✗, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 2

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 0.9189 | 0 | 1 | 66 | 0.8 | 0.85 |
| en | 20 | 1 | 0.8889 | 0 | 1 | 30 | 0.65 | 0.725 |
| tr | 20 | 1 | 0.9474 | 0 | 1 | 36 | 0.95 | 0.975 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 2 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 22, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 92.97 sn, öbek başına 2.73 sn, 275.3 çıktı token/sn, toplam 51304 token, önek cache isabeti 0.5501
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Tekrar karşılaştırması (katman 1)

- all.coverage_rate: 0.973 → 1.0
- all.method_exact_match: 0.75 → 0.8
- all.method_jaccard: 0.8125 → 0.85
- all.test_cases: 61 → 66
- by_language.en.test_cases: 27 → 30
- by_language.tr.coverage_rate: 0.9474 → 1.0
- by_language.tr.method_exact_match: 0.85 → 0.95
- by_language.tr.method_jaccard: 0.9 → 0.975
- by_language.tr.test_cases: 34 → 36
- thresholds.coverage_rate: False → True
- traps.test_cases: 4 → 2

