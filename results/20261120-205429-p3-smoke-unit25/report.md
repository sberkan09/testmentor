# p3-smoke-unit25

- Soru: Paket 3 duman testi (pod 1): en büyük birim (25 gereksinim, max_tokens 20480) kesilmeden ve şemaya uyarak üretiliyor mu.
- Değişken: generation.max_unit_size=25, unit_packing (duman)
- Koşu: `20261120-205429-p3-smoke-unit25`, ayar `config/experiments/p3-smoke-unit25.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `gnqzu0saamorfv`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 120 | 1 | 1 | 0 | 0 | 1 | 141 | 0.4417 | 0.6667 | 0 |
| en | 60 | 1 | 1 | 0 | – | 1 | 62 | 0.5667 | 0.75 | – |
| tr | 60 | 1 | 1 | 0 | – | 1 | 79 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 0 | – | 1 | 1 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3355
- Çağrı: 11, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 243.99 sn, öbek başına 10.61 sn, 191.9 çıktı token/sn, toplam 76320 token, önek cache isabeti 0.1129
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

