# d1-vllm

- Soru: D1 Sunum motoru: vLLM. 1, 8, 16, 32 eşzamanlı istekte hız, ilk token süresi, hata, şema.
- Değişken: engine=vllm
- Koşu: `20261119-181117-d1-vllm`, ayar `config/experiments/d1-vllm.yaml`, şablon `t1`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4 | 0 | 1 | 44.1 | 1.024 | 1.685 | 95.96 | 0 |
| 8 | 16 | 0 | 1 | 262.7 | 1.068 | 1.305 | 80.3 | 0 |
| 16 | 32 | 0 | 1 | 454.1 | 0.954 | 1.43 | 82.68 | 0 |
| 32 | 64 | 0 | 1 | 777.4 | 0.96 | 1.853 | 104.4 | 0 |

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 0.7838 | 0.7838 | 0 | 1 | 76 | 0.775 | 0.825 |
| en | 20 | 0.6111 | 0.6111 | 0 | 1 | 34 | 0.6 | 0.675 |
| tr | 20 | 0.9474 | 0.9474 | 0 | 1 | 42 | 0.95 | 0.975 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 3 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 29, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 69.68 sn, öbek başına 2.05 sn, 367.4 çıktı token/sn, toplam 58809 token, önek cache isabeti 0.6012
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✗, step_structure_rate ✓, no_test_violations ✓

