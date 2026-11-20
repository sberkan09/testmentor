# d3-temp-03

- Soru: D3 Örnekleme: test üretiminde sıcaklık 0,3 (varsayım 0,7).
- Değişken: generation.temperature=0.3
- Koşu: `20261119-182851-d3-temp-03`, ayar `config/experiments/d3-temp-03.yaml`, şablon `t1`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 0.973 | 0 | 1 | 59 | 0.775 | 0.825 |
| en | 20 | 1 | 1 | 0 | 1 | 25 | 0.6 | 0.675 |
| tr | 20 | 1 | 0.9474 | 0 | 1 | 34 | 0.95 | 0.975 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 21, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 68.48 sn, öbek başına 2.01 sn, 326.4 çıktı token/sn, toplam 46789 token, önek cache isabeti 0.5448
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

