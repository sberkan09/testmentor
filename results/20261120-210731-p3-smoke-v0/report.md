# p3-smoke-v0

- Soru: Paket 3 duman testi (pod 1): yeni aşamalarla altın set v0 referans, tek koşu.
- Değişken: aşama kodu (duman)
- Koşu: `20261120-210731-p3-smoke-v0`, ayar `config/experiments/p3-smoke-v0.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `gnqzu0saamorfv`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 0 | 1 | 60 | 0.775 | 0.8375 | 0 |
| en | 20 | 1 | 1 | 0 | – | 1 | 28 | 0.6 | 0.7 | – |
| tr | 20 | 1 | 1 | 0 | – | 1 | 32 | 0.95 | 0.975 | – |
| tuzak | 4 | 1 | 1 | 0 | – | 1 | 1 | 0.75 | 0.875 | – |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 59.88 sn, öbek başına 1.76 sn, 340.4 çıktı token/sn, toplam 43613 token, önek cache isabeti 0.3582
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

