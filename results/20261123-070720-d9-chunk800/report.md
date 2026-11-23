# d9-chunk800

- Soru: D9 parça boyu: 800 token (taban 400); ilk 8 parça ~6.400 token eder, bağlama sığar. Belge gerektiren denetimlerde check_recall d9-index-base ile karşılaştırılır.
- Değişken: kb.chunk_tokens=800
- Koşu: `20261123-070720-d9-chunk800`, ayar `config/experiments/d9-chunk800.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `14b0czatogi5id`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 1 | 0 | 0 | 1 | 519 | 0.6769 | 0.8035 | 0.106 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 398 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 1 | 0 | – | 1 | 121 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 108, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 498.75 sn, öbek başına 11.88 sn, 329.4 çıktı token/sn, toplam 875292 token, önek cache isabeti 0.1474
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.5106
- en: 0.5331
- tr: 0.4706

