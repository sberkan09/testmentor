# p3-v1-predicted

- Soru: Paket 3 bitti ölçütü: altın set v1 uçtan uca; şema, adım yapısı ve tahmin edilen yöntemlere göre kapsama.
- Değişken: generation_inputs=predicted
- Koşu: `20261120-212628-p3-v1-predicted`, ayar `config/experiments/p3-v1-predicted.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 0.8991 | 1 | 0.8991 | 1 | 1 | 1 | 335 | 0.6769 | 0.7991 | 0.1104 |
| en | 169 | 0.9524 | 1 | 0.9524 | 1 | – | 1 | 245 | 0.8047 | 0.8817 | – |
| tr | 60 | 0.75 | 1 | 0.75 | 0 | – | 1 | 90 | 0.3167 | 0.5667 | – |
| tuzak | 1 | 1 | 1 | 1 | 0 | – | 1 | 1 | 1 | 1 | – |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 51, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 296.09 sn, öbek başına 7.05 sn, 367.6 çıktı token/sn, toplam 198317 token, önek cache isabeti 0.6044
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✗, step_structure_rate ✓, no_test_violations ✗

## Hakem (katman 2)

- check_recall: 0.4027
- en: 0.4217
- tr: 0.369

