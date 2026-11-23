# d10-ex4-r3

- Soru: D10: öbek başına 4 örnek (sızıntısız referans havuzu); check_recall ve üslup uyumu d10-base ile karşılaştırılır (3 tekrar: koşudan koşuya oynamayı ölçmek için)
- Değişken: kb.examples=4
- Koşu: `20261123-132759-d10-ex4-r3`, ayar `config/experiments/d10-ex4-r3.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `ojij9aaejbqad2`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9912 | 0 | 0 | 1 | 495 | 0.6769 | 0.8035 | 0.0869 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 383 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 112 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 110, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 427.98 sn, öbek başına 10.19 sn, 360.2 çıktı token/sn, toplam 611734 token, önek cache isabeti 0.2673
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 2

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9868 | 0 | 0 | 1 | 494 | 0.6856 | 0.8064 | 0.1134 |
| en | 169 | 1 | 0.9937 | 0.994 | 0 | – | 1 | 390 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 104 | 0.35 | 0.5944 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 111, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 428.01 sn, öbek başına 10.19 sn, 363.4 çıktı token/sn, toplam 617732 token, önek cache isabeti 0.2232
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 3

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9868 | 0 | 0 | 1 | 505 | 0.6769 | 0.8035 | 0.1149 |
| en | 169 | 1 | 0.9937 | 0.994 | 0 | – | 1 | 394 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 111 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 111, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 448.65 sn, öbek başına 10.68 sn, 356.6 çıktı token/sn, toplam 623144 token, önek cache isabeti 0.2317
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Tekrar karşılaştırması (katman 1)

- all.coverage_rate_before_repair: 0.9912 → 0.9868
- all.duplicate_pairs: 36 → 51
- all.duplicate_test_rate: 0.0869 → 0.1134
- all.method_exact_match: 0.6769 → 0.6856
- all.method_jaccard: 0.8035 → 0.8064
- all.test_cases: 495 → 494
- by_language.en.coverage_rate_before_repair: 1.0 → 0.994
- by_language.en.test_cases: 383 → 390
- by_language.tr.method_exact_match: 0.3167 → 0.35
- by_language.tr.method_jaccard: 0.5833 → 0.5944
- by_language.tr.test_cases: 112 → 104

## Hakem (katman 2)

- check_recall: 0.5434
- en: 0.5873
- tr: 0.4652

