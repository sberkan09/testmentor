# d2-gpt-oss

- Soru: D2 Model: gpt-oss-120b (MXFP4). Düşünme kapatılamaz; kapalı kip reasoning_effort=low.
- Değişken: model=gpt-oss-120b
- Koşu: `20261119-194830-d2-gpt-oss`, ayar `config/experiments/d2-gpt-oss.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / gpt-oss-120b (sunulan ad `gpt-oss-120b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 86 | 0.775 | 0.8375 |
| en | 20 | 1 | 1 | 0 | 1 | 36 | 0.7 | 0.775 |
| tr | 20 | 1 | 1 | 0 | 1 | 50 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 2 | 0.5 | 0.625 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 40.72 sn, öbek başına 1.2 sn, 595.6 çıktı token/sn, toplam 48170 token, önek cache isabeti 0.3479
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4255
- en: 0.4444
- tr: 0.4103

