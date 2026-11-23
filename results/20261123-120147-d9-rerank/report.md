# d9-rerank

- Soru: D9 reranker kolu: çapraz kodlayıcı (BAAI/bge-reranker-v2-m3, CPU) ilk 3 x top_k adayı yeniden sıralar; belge gerektiren denetimlerde check_recall d10-base ile karşılaştırılır.
- Değişken: kb.reranker=BAAI/bge-reranker-v2-m3
- Koşu: `20261123-120147-d9-rerank`, ayar `config/experiments/d9-rerank.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `2muhu5folo55ck`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9825 | 0 | 0 | 1 | 520 | 0.6769 | 0.8035 | 0.0788 |
| en | 169 | 1 | 0.9937 | 0.9881 | 0 | – | 1 | 406 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9667 | 0 | – | 1 | 114 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 4 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 111, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 1466.33 sn, öbek başına 34.91 sn, 111.2 çıktı token/sn, toplam 488605 token, önek cache isabeti 0.2812
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

