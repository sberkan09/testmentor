# d9-index-base

- Soru: D9 karşılaştırma tabanı (paket 7): altın set v1, gerçek hibrit arama (parça 400 token, ilk 8, reranker yok, kart var). Diğer d9-* kolları bunun tek değişkenli sapmalarıdır; d9-pilot-none ve d9-pilot-gold ile de karşılaştırılır (belge gerektiren denetimlerde recall).
- Değişken: passages=index (kb varsayılanları)
- Koşu: `20261123-065138-d9-index-base`, ayar `config/experiments/d9-index-base.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g5+1d644a8e20b3`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `14b0czatogi5id`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9951 | 0.9956 | 0 | 0 | 1 | 539 | 0.6769 | 0.8035 | 0.1132 |
| en | 169 | 1 | 0.9937 | 1 | 0 | – | 1 | 414 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 0.9833 | 0 | – | 1 | 125 | 0.3167 | 0.5833 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 109, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 472.42 sn, öbek başına 11.25 sn, 347.3 çıktı token/sn, toplam 627487 token, önek cache isabeti 0.1795
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.5048
- en: 0.5572
- tr: 0.4118

