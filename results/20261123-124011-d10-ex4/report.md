# d10-ex4

- Soru: D10: öbek başına 4 örnek (sızıntısız referans havuzu); check_recall ve üslup uyumu d10-base ile karşılaştırılır
- Değişken: kb.examples=4
- Koşu: `20261123-124011-d10-ex4`, ayar `config/experiments/d10-ex4.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `2muhu5folo55ck`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9952 | 0.9912 | 0 | 0 | 1 | 498 | 0.6769 | 0.8035 | 0.0904 |
| en | 169 | 1 | 0.9938 | 1 | 0 | – | 1 | 383 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 115 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 110, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 427.38 sn, öbek başına 10.18 sn, 360.8 çıktı token/sn, toplam 611775 token, önek cache isabeti 0.2036
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.5299
- en: 0.5602
- tr: 0.4759

