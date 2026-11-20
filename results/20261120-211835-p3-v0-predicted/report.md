# p3-v0-predicted

- Soru: Paket 3 bitti ölçütü: altın set v0 uçtan uca (tahmin edilen öbek ve yöntemler); şema, adım yapısı ve tahmin edilen yöntemlere göre kapsama.
- Değişken: generation_inputs=predicted
- Koşu: `20261120-211835-p3-v0-predicted`, ayar `config/experiments/p3-v0-predicted.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 0.7027 | 1 | 0.7027 | 0 | 0 | 1 | 68 | 0.7 | 0.7625 | 0.1029 |
| en | 20 | 0.5556 | 1 | 0.5556 | 0 | – | 1 | 30 | 0.55 | 0.625 | – |
| tr | 20 | 0.8421 | 1 | 0.8421 | 0 | – | 1 | 38 | 0.85 | 0.9 | – |
| tuzak | 4 | 1 | 1 | 1 | 0 | – | 1 | 3 | 0.75 | 0.875 | – |

- Öbek uyumu (ARI): 0.094
- Çağrı: 26, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 64.49 sn, öbek başına 1.9 sn, 369.8 çıktı token/sn, toplam 53533 token, önek cache isabeti 0.5886
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✗, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4043
- en: 0.3492
- tr: 0.4487

