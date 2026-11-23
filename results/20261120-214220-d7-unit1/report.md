# d7-unit1

- Soru: D7 Üretim birimi: referans öbekler 1 gereksinime kadar birleştirilir (büyükler bölünür); check_recall, tekrar eden test oranı, süre ve çıktı token'ı d7-cluster ile karşılaştırılır.
- Değişken: generation.max_unit_size=1 (unit_packing açık)
- Koşu: `20261120-214220-d7-unit1`, ayar `config/experiments/d7-unit1.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9952 | 1 | 0 | 0 | 1 | 748 | 0.6769 | 0.8035 | 0.1805 |
| en | 169 | 1 | 0.9938 | 1 | 0 | – | 1 | 535 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 1 | 0 | – | 1 | 213 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 238, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 483.68 sn, öbek başına 11.52 sn, 537.4 çıktı token/sn, toplam 568888 token, önek cache isabeti 0.6759
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4952
- en: 0.509
- tr: 0.4706

