# d10-base-r3

- Soru: D10 tabanı: sızıntısız referans havuzu kurulur, örnek verilmez (kb.examples=0); kollar bununla eşleştirilir (3 tekrar: koşudan koşuya oynamayı ölçmek için)
- Değişken: kb.examples=0
- Koşu: `20261123-130751-d10-base-r3`, ayar `config/experiments/d10-base-r3.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `ojij9aaejbqad2`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9956 | 0 | 0 | 1 | 514 | 0.6856 | 0.8079 | 0.0914 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 398 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9833 | 0 | – | 1 | 116 | 0.35 | 0.6 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 4 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 109, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 411.98 sn, öbek başına 9.81 sn, 391.2 çıktı token/sn, toplam 475976 token, önek cache isabeti 0.2616
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 2

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9912 | 0 | 0 | 1 | 526 | 0.6856 | 0.8079 | 0.1312 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 402 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 124 | 0.35 | 0.6 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 110, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 390.16 sn, öbek başına 9.29 sn, 426.9 çıktı token/sn, toplam 486605 token, önek cache isabeti 0.8865
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 3

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9912 | 0 | 0 | 1 | 519 | 0.6769 | 0.8035 | 0.1349 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 397 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 122 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 4 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 110, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 402.47 sn, öbek başına 9.58 sn, 413.2 çıktı token/sn, toplam 486337 token, önek cache isabeti 0.8865
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Tekrar karşılaştırması (katman 1)

- all.coverage_rate_before_repair: 0.9956 → 0.9912
- all.duplicate_pairs: 35 → 59
- all.duplicate_test_rate: 0.0914 → 0.1312
- all.test_cases: 514 → 526
- by_language.en.test_cases: 398 → 402
- by_language.tr.coverage_rate_before_repair: 0.9833 → 0.9667
- by_language.tr.test_cases: 116 → 124
- traps.test_cases: 4 → 3

