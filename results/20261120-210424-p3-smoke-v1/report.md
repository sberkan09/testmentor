# p3-smoke-v1

- Soru: Paket 3 duman testi (pod 1): altın set v1 ETC uçtan uca (gerçek öbekleme ve yöntem aşaması).
- Değişken: generation_inputs=predicted (duman)
- Koşu: `20261120-210424-p3-smoke-v1`, ayar `config/experiments/p3-smoke-v1.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `gnqzu0saamorfv`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 109 | 0.9815 | 0.9815 | 1 | 1 | 1 | 175 | 0.9358 | 0.9541 | 0.1314 |
| en | 109 | 0.9815 | 0.9815 | 1 | – | 1 | 175 | 0.9358 | 0.9541 | – |
| tuzak | 0 | – | – | 0 | – | – | 0 | – | – | – |

- Öbek uyumu (ARI): 0.3213
- Çağrı: 24, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 183.38 sn, öbek başına 9.65 sn, 300.8 çıktı token/sn, toplam 96703 token, önek cache isabeti 0.4006
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✗, step_structure_rate ✓, no_test_violations ✗

