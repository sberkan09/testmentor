# d9-card-off

- Soru: D9 proje kartı: kart metni yok (yalnızca doğrulama yöntemi listesi kalır; taban kartında proje adı ve alan satırı var). Altın setin kartı yalnızca ad ve alandır, sistem tanımı, sözlük ve yazım kuralları yoktur: bu kol yalnızca o iki satırın etkisini ölçer. Kartın asıl değeri (belgelerden çıkarılan taslak) ayrı bir kol ister.
- Değişken: card=methods_only
- Koşu: `20261123-072933-d9-card-off`, ayar `config/experiments/d9-card-off.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `14b0czatogi5id`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.995 | 0.9912 | 0 | 0 | 1 | 532 | 0.6594 | 0.7817 | 0.109 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 415 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 117 | 0.25 | 0.5 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 5 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 110, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 420.14 sn, öbek başına 10 sn, 382.8 çıktı token/sn, toplam 627802 token, önek cache isabeti 0.1942
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4875
- en: 0.5452
- tr: 0.385

