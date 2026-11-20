# d8-add

- Soru: D8 Yeniden üretim, ekleme: her öbekten ayrılan Test üyesi geri eklenir; artımlı çağrı (çalışma varsayımı) ile baştan üretim aynı taban üzerinde karşılaştırılır. Korunma oranı, sabit testlerin korunması ve tekrarı, yeni gereksinimin kapsaması ve recall'ı, süre ve çıktı token'ı.
- Değişken: generation.regeneration (incremental | full)
- Koşu: `20261120-220006-d8-add`, ayar `config/experiments/d8-add.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | – | 0 | 0 | 0 | 1 | 519 | 0 | 0 | 0.1272 |
| en | 169 | 1 | – | 0 | 0 | – | 1 | 397 | 0 | 0 | – |
| tr | 60 | 1 | – | 0 | 0 | – | 1 | 122 | 0 | 0 | – |
| tuzak | 1 | 1 | – | 0 | 0 | – | 1 | 3 | 0 | 0 | – |

- Öbek uyumu (ARI): –
- Çağrı: 151, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 778.97 sn, öbek başına – sn, 288.8 çıktı token/sn, toplam 477854 token, önek cache isabeti 0.6119
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

### Senaryo (add, D8; taban çağrısı 99)

| kol | units | change_calls | change_completion_tokens | change_call_s | change_wall_s | preservation_rate | identical_rate | pinned_kept_rate | pinned_repeats | new_coverage_before_repair | new_coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| incremental | 26 | 26 | 18651 | 529 | 44.46 | 1 | 1 | 1 | 0 | 1 | 1 |
| full | 26 | 26 | 74418 | 1884 | 193.7 | 0.0888 | 0.0047 | 1 | 7 | 1 | 1 |

## Hakem (katman 2)

- check_recall: 0.4508
- en: 0.4535
- tr: 0.4476

