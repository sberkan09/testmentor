# p3-v1-reference

- Soru: Paket 3 bitti ölçütü: altın set v1 parçasız, referans öbek ve yöntemler; katman 1 eşikleri ve paket 1 tabanına (check_recall 0,449) göre gerileme yok.
- Değişken: aşama kodu (generation_inputs=reference)
- Koşu: `20261120-211943-p3-v1-reference`, ayar `config/experiments/p3-v1-reference.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9952 | 0.9956 | 0 | 0 | 1 | 497 | 0.6769 | 0.8035 | 0.0966 |
| en | 169 | 1 | 0.9938 | 1 | 0 | – | 1 | 376 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9833 | 0 | – | 1 | 121 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 109, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 401.84 sn, öbek başına 9.57 sn, 393.7 çıktı token/sn, toplam 316120 token, önek cache isabeti 0.5058
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4489
- en: 0.4729
- tr: 0.4064

