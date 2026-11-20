# d2-gpt-oss-r3

- Soru: D2 tekrar: gpt-oss-120b, güncel ayarlarla 3 koşu.
- Değişken: model=gpt-oss-120b
- Koşu: `20261120-051647-d2-gpt-oss-r3`, ayar `config/experiments/d2-gpt-oss-r3.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / gpt-oss-120b (sunulan ad `gpt-oss-120b`, pod `ib4b8vwnicumxq`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 87 | 0.775 | 0.8375 |
| en | 20 | 1 | 1 | 0 | 1 | 39 | 0.65 | 0.725 |
| tr | 20 | 1 | 1 | 0 | 1 | 48 | 0.9 | 0.95 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 2 | 0.5 | 0.625 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 38.82 sn, öbek başına 1.14 sn, 620.8 çıktı token/sn, toplam 48014 token, önek cache isabeti 0.3479
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 2

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 79 | 0.775 | 0.8375 |
| en | 20 | 1 | 1 | 0 | 1 | 36 | 0.7 | 0.775 |
| tr | 20 | 1 | 1 | 0 | 1 | 43 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 2 | 0.5 | 0.625 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 33.72 sn, öbek başına 0.99 sn, 645.2 çıktı token/sn, toplam 45672 token, önek cache isabeti 0.974
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 3

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 84 | 0.75 | 0.8125 |
| en | 20 | 1 | 1 | 0 | 1 | 41 | 0.65 | 0.725 |
| tr | 20 | 1 | 1 | 0 | 1 | 43 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 2 | 0.5 | 0.625 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 32.83 sn, öbek başına 0.97 sn, 654.4 çıktı token/sn, toplam 45399 token, önek cache isabeti 0.974
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Tekrar karşılaştırması (katman 1)

- all.test_cases: 87 → 79
- by_language.en.method_exact_match: 0.65 → 0.7
- by_language.en.method_jaccard: 0.725 → 0.775
- by_language.en.test_cases: 39 → 36
- by_language.tr.method_exact_match: 0.9 → 0.85
- by_language.tr.method_jaccard: 0.95 → 0.9
- by_language.tr.test_cases: 48 → 43

## Hakem (katman 2)

- check_recall: 0.461
- en: 0.4286
- tr: 0.4872

