# d2-qwen

- Soru: D2 Model: Qwen3.8-27B (FP8). Aynı ayarla iki koşu (tekrarlanabilirlik).
- Değişken: model=qwen3.8-27b
- Koşu: `20261119-183725-d2-qwen`, ayar `config/experiments/d2-qwen.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 70 | 0.725 | 0.7875 |
| en | 20 | 1 | 1 | 0 | 1 | 31 | 0.6 | 0.675 |
| tr | 20 | 1 | 1 | 0 | 1 | 39 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 74.49 sn, öbek başına 2.19 sn, 330.1 çıktı token/sn, toplam 47817 token, önek cache isabeti 0.3582
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 2

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 60 | 0.775 | 0.825 |
| en | 20 | 1 | 1 | 0 | 1 | 27 | 0.6 | 0.675 |
| tr | 20 | 1 | 1 | 0 | 1 | 33 | 0.95 | 0.975 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 78.19 sn, öbek başına 2.3 sn, 279.1 çıktı token/sn, toplam 45051 token, önek cache isabeti 0.5373
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Tekrar karşılaştırması (katman 1)

- all.method_exact_match: 0.725 → 0.775
- all.method_jaccard: 0.7875 → 0.825
- all.test_cases: 70 → 60
- by_language.en.test_cases: 31 → 27
- by_language.tr.method_exact_match: 0.85 → 0.95
- by_language.tr.method_jaccard: 0.9 → 0.975
- by_language.tr.test_cases: 39 → 33

## Hakem (katman 2)

- check_recall: 0.4823
- en: 0.4603
- tr: 0.5

