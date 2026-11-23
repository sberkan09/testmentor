# d10-base

- Soru: D10 tabanı: sızıntısız referans havuzu kurulur, örnek verilmez (kb.examples=0); kollar bununla eşleştirilir
- Değişken: kb.examples=0
- Koşu: `20261123-122629-d10-base`, ayar `config/experiments/d10-base.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `2muhu5folo55ck`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9956 | 0 | 0 | 1 | 524 | 0.6769 | 0.8035 | 0.1126 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 402 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9833 | 0 | – | 1 | 122 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 109, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 403.1 sn, öbek başına 9.6 sn, 409 çıktı token/sn, toplam 479678 token, önek cache isabeti 0.3436
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4836
- en: 0.5331
- tr: 0.3957

