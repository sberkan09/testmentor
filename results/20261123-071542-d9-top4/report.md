# d9-top4

- Soru: D9 parça sayısı: ilk 4 parça (taban 8); belge gerektiren denetimlerde check_recall ve uydurma içerik d9-index-base ile karşılaştırılır.
- Değişken: kb.top_k=4
- Koşu: `20261123-071542-d9-top4`, ayar `config/experiments/d9-top4.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `14b0czatogi5id`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9912 | 0 | 0 | 1 | 520 | 0.6769 | 0.8035 | 0.1 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 401 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 119 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 4 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 110, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 403.56 sn, öbek başına 9.61 sn, 408.7 çıktı token/sn, toplam 485132 token, önek cache isabeti 0.2806
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.5183
- en: 0.5572
- tr: 0.4492

