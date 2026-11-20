# d8-remove

- Soru: D8 Yeniden üretim, çıkarma: her öbekten bir Test üyesi çıkar; artımlı çağrı (tasarımın çağrı sayısı) ile modelsiz budama aynı taban üzerinde karşılaştırılır. Fark ölçülemezse daha basit olan budama seçilir.
- Değişken: generation.prune_removals (false | true)
- Koşu: `20261120-221308-d8-remove`, ayar `config/experiments/d8-remove.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 0.8816 | – | 0 | 0 | 0 | 1 | 428 | 0 | 0 | 0.1332 |
| en | 169 | 0.8869 | – | 0 | 0 | – | 1 | 328 | 0 | 0 | – |
| tr | 60 | 0.8667 | – | 0 | 0 | – | 1 | 100 | 0 | 0 | – |
| tuzak | 1 | 1 | – | 0 | 0 | – | 1 | 3 | 0 | 0 | – |

- Öbek uyumu (ARI): –
- Çağrı: 125, hata 0, şema geçerliliği 0.992 (üretim 0.9899)
- Süre 571.82 sn, öbek başına – sn, 266.1 çıktı token/sn, toplam 353557 token, önek cache isabeti 0.5991
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✗, step_structure_rate ✓, no_test_violations ✓

### Senaryo (remove, D8; taban çağrısı 99)

| kol | units | change_calls | change_completion_tokens | change_call_s | change_wall_s | preservation_rate | identical_rate | pinned_kept_rate | pinned_repeats |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| call | 26 | 26 | 1303 | 91.73 | 22.68 | 1 | 1 | 1 | 0 |
| prune | 26 | 0 | 0 | 0 | 0.02 | 1 | 1 | 1 | 0 |

## Hakem (katman 2)

- check_recall: 0.4045
- en: 0.3882
- tr: 0.4261

