# d4-bf16

- Soru: D4 Ağırlık hassasiyeti: 16 bit (resmî BF16). Varsayım FP8.
- Değişken: precision=bf16
- Koşu: `20261119-192007-d4-bf16`, ayar `config/experiments/d4-bf16.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b-bf16 (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | 32 | 0 | 1 | 307.1 | 1.724 | 2.67 | 125.7 | 0 |
| 32 | 64 | 0 | 1 | 471 | 1.045 | 2.763 | 158.9 | 0 |

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 58 | 0.75 | 0.825 |
| en | 20 | 1 | 1 | 0 | 1 | 25 | 0.65 | 0.75 |
| tr | 20 | 1 | 1 | 0 | 1 | 33 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 122.12 sn, öbek başına 3.59 sn, 169.5 çıktı token/sn, toplam 43929 token, önek cache isabeti 0.5373
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4397
- en: 0.4127
- tr: 0.4615

