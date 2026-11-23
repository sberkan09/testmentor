# d10-ex2

- Soru: D10: öbek başına 2 örnek (sızıntısız referans havuzu); check_recall ve üslup uyumu d10-base ile karşılaştırılır
- Değişken: kb.examples=2
- Koşu: `20261123-123315-d10-ex2`, ayar `config/experiments/d10-ex2.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `2muhu5folo55ck`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9952 | 0.9912 | 0 | 0 | 1 | 492 | 0.6812 | 0.8079 | 0.1098 |
| en | 169 | 1 | 0.9938 | 1 | 0 | – | 1 | 382 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 110 | 0.3333 | 0.6 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 110, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 412.48 sn, öbek başına 9.82 sn, 374.4 çıktı token/sn, toplam 547189 token, önek cache isabeti 0.3178
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.5222
- en: 0.5542
- tr: 0.4652

