# d5-ctx16k

- Soru: D5 Bağlam: 16 bin token (varsayım 32 bin). Kalite ve 16/32 eşzamanlı hız.
- Değişken: context_length=16384
- Koşu: `20261119-191215-d5-ctx16k`, ayar `config/experiments/d5-ctx16k.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | 32 | 0 | 1 | 430.1 | 1.373 | 2.149 | 95.37 | 0 |
| 32 | 64 | 0 | 1 | 757.4 | 0.968 | 2.02 | 104.1 | 0 |

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 0.973 | 0 | 1 | 63 | 0.725 | 0.7875 |
| en | 20 | 1 | 0.9444 | 0 | 1 | 28 | 0.6 | 0.675 |
| tr | 20 | 1 | 1 | 0 | 1 | 35 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 21, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 83.29 sn, öbek başına 2.45 sn, 259.4 çıktı token/sn, toplam 46135 token, önek cache isabeti 0.5428
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4468
- en: 0.4603
- tr: 0.4359

