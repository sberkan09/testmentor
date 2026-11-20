# d7-cluster

- Soru: D7 Üretim birimi, çalışma varsayımı: referans öbek başına tek çağrı (birleştirme yok, sınır 25); D7 kollarının karşılaştırma tabanı.
- Değişken: unit_packing=false (öbek başına çağrı)
- Koşu: `20261120-213128-d7-cluster`, ayar `config/experiments/d7-cluster.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 0.9956 | 0.9903 | 0.9956 | 0 | 0 | 1 | 476 | 0.6856 | 0.8079 | 0.1345 |
| en | 169 | 0.994 | 0.9874 | 0.994 | 0 | – | 1 | 367 | 0.8047 | 0.8817 | – |
| tr | 60 | 1 | 1 | 1 | 0 | – | 1 | 109 | 0.35 | 0.6 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 3 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 108, hata 0, şema geçerliliği 0.9907 (üretim 0.9898)
- Süre 648.92 sn, öbek başına 15.45 sn, 267.6 çıktı token/sn, toplam 330190 token, önek cache isabeti 0.707
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✗, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4258
- en: 0.4699
- tr: 0.3476

