# d9-top12

- Soru: D9 parça sayısı: ilk 12 parça (taban 8); 12 x 400 token ~4.800 token eder. Belge gerektiren denetimlerde check_recall ve uydurma içerik d9-index-base ile karşılaştırılır.
- Değişken: kb.top_k=12
- Koşu: `20261123-072229-d9-top12`, ayar `config/experiments/d9-top12.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `14b0czatogi5id`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.995 | 0.9956 | 0 | 0 | 1 | 511 | 0.6594 | 0.786 | 0.1272 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 407 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9833 | 0 | – | 1 | 104 | 0.25 | 0.5167 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 109, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 420.98 sn, öbek başına 10.02 sn, 394 çıktı token/sn, toplam 776106 token, önek cache isabeti 0.195
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.5241
- en: 0.5723
- tr: 0.4385

