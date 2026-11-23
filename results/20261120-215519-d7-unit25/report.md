# d7-unit25

- Soru: D7 Üretim birimi: referans öbekler 25 gereksinime kadar birleştirilir (büyükler bölünür); check_recall, tekrar eden test oranı, süre ve çıktı token'ı d7-cluster ile karşılaştırılır.
- Değişken: generation.max_unit_size=25 (unit_packing açık)
- Koşu: `20261120-215519-d7-unit25`, ayar `config/experiments/d7-unit25.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9956 | 0 | 0 | 1 | 288 | 0.69 | 0.81 | 0.0243 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 205 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9833 | 0 | – | 1 | 83 | 0.3667 | 0.6083 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 1 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 22, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 284.78 sn, öbek başına 6.78 sn, 332.8 çıktı token/sn, toplam 152272 token, önek cache isabeti 0.6366
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.3545
- en: 0.3735
- tr: 0.3209

