# d2-gemma

- Soru: D2 Model: Gemma 4 31B (BF16).
- Değişken: model=gemma-4-31b
- Koşu: `20261119-194437-d2-gemma`, ayar `config/experiments/d2-gemma.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / gemma-4-31b (sunulan ad `gemma-4-31b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 47 | 0.7 | 0.7625 |
| en | 20 | 1 | 1 | 0 | 1 | 22 | 0.6 | 0.675 |
| tr | 20 | 1 | 1 | 0 | 1 | 25 | 0.8 | 0.85 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 78.22 sn, öbek başına 2.3 sn, 130.7 çıktı token/sn, toplam 33424 token, önek cache isabeti 0.3475
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.3972
- en: 0.3968
- tr: 0.3974

