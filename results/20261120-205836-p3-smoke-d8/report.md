# p3-smoke-d8

- Soru: Paket 3 duman testi (pod 1): D8 ekleme senaryosu (artımlı çağrı) bir projede, gerçek modelle.
- Değişken: scenario add (duman)
- Koşu: `20261120-205836-p3-smoke-d8`, ayar `config/experiments/p3-smoke-d8.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `gnqzu0saamorfv`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 109 | 1 | 0 | 0 | 0 | 1 | 247 | 0 | 0 | 0.1498 |
| en | 109 | 1 | 0 | 0 | – | 1 | 247 | 0 | 0 | – |
| tuzak | 0 | – | – | 0 | – | – | 0 | – | – | – |

- Öbek uyumu (ARI): –
- Çağrı: 69, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 345.14 sn, öbek başına – sn, 346.9 çıktı token/sn, toplam 245791 token, önek cache isabeti 0.561
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

### Senaryo (add, D8; taban çağrısı 32)

| kol | units | change_calls | change_completion_tokens | change_call_s | change_wall_s | preservation_rate | identical_rate | pinned_kept_rate | pinned_repeats | new_coverage_before_repair | new_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| incremental | 18 | 18 | 11564 | 347.3 | 32.41 | 1 | 1 | 1 | 7 | 1 | 1 |
| full | 18 | 19 | 49987 | 1304 | 142.5 | 0.0979 | 0.007 | 1 | 10 | 1 | 1 |

