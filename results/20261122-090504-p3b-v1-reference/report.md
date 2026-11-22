# p3b-v1-reference

- Soru: Paket 3b: şablon g4 ile altın set v1 referans; katman 1 eşikleri ve p3-v1-reference'a göre eşleştirilmiş check_recall farkının alt sınırı ≥ −0,05.
- Değişken: test seti şablonu g4 (field_max_chars + kural)
- Koşu: `20261122-090504-p3b-v1-reference`, ayar `config/experiments/p3b-v1-reference.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g4+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `qo96f4iin3ii3s`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9956 | 0 | 0 | 1 | 473 | 0.6769 | 0.8035 | 0.1628 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 380 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9833 | 0 | – | 1 | 93 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 109, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 338.92 sn, öbek başına 8.07 sn, 453.3 çıktı token/sn, toplam 320044 token, önek cache isabeti 0.5799
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4316
- en: 0.4789
- tr: 0.3476

