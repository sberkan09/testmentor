# d7-unit10

- Soru: D7 Üretim birimi: referans öbekler 10 gereksinime kadar birleştirilir (büyükler bölünür); check_recall, tekrar eden test oranı, süre ve çıktı token'ı d7-cluster ile karşılaştırılır.
- Değişken: generation.max_unit_size=10 (unit_packing açık)
- Koşu: `20261120-215028-d7-unit10`, ayar `config/experiments/d7-unit10.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9956 | 0 | 0 | 1 | 361 | 0.6769 | 0.8035 | 0.0776 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 270 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9833 | 0 | – | 1 | 91 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 1 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 40, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 287.77 sn, öbek başına 6.85 sn, 393.2 çıktı token/sn, toplam 190935 token, önek cache isabeti 0.6524
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.3854
- en: 0.4006
- tr: 0.3583

