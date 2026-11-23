# d9-chunk300

- Soru: D9 parça boyu: 300 token (taban 400); belge gerektiren denetimlerde check_recall d9-index-base ile karşılaştırılır.
- Değişken: kb.chunk_tokens=300
- Koşu: `20261123-065933-d9-chunk300`, ayar `config/experiments/d9-chunk300.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `14b0czatogi5id`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9912 | 0 | 0 | 1 | 508 | 0.6769 | 0.8035 | 0.0768 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 391 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 117 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 110, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 464.15 sn, öbek başına 11.05 sn, 350 çıktı token/sn, toplam 563487 token, önek cache isabeti 0.2282
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4971
- en: 0.5452
- tr: 0.4118

