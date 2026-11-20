# d1-sglang

- Soru: D1 Sunum motoru: SGLang. 1, 8, 16, 32 eşzamanlı istekte hız, ilk token süresi, hata, şema.
- Değişken: engine=sglang
- Koşu: `20261119-195446-d1-sglang`, ayar `config/experiments/d1-sglang.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: sglang / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4 | 0 | 1 | 44.9 | 1.013 | 1.237 | 97.71 | 0 |
| 8 | 16 | 0 | 1 | 243.7 | 1.06 | 1.439 | 83.86 | 0 |
| 16 | 32 | 0 | 1 | 434.3 | 0.868 | 1.115 | 91.34 | 0 |
| 32 | 64 | 0 | 1 | 698.2 | 0.916 | 7.862 | 117.1 | 0 |

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 60 | 0.725 | 0.7875 |
| en | 20 | 1 | 1 | 0 | 1 | 29 | 0.6 | 0.675 |
| tr | 20 | 1 | 1 | 0 | 1 | 31 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 65.12 sn, öbek başına 1.92 sn, 310.6 çıktı token/sn, toplam 43457 token, önek cache isabeti 0.675
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.383
- en: 0.4127
- tr: 0.359

