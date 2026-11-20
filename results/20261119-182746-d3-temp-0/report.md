# d3-temp-0

- Soru: D3 Örnekleme: test üretiminde sıcaklık 0 (varsayım 0,7).
- Değişken: generation.temperature=0
- Koşu: `20261119-182746-d3-temp-0`, ayar `config/experiments/d3-temp-0.yaml`, şablon `t1`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 0.973 | 0 | 1 | 60 | 0.75 | 0.8125 |
| en | 20 | 1 | 1 | 0 | 1 | 27 | 0.6 | 0.675 |
| tr | 20 | 1 | 0.9474 | 0 | 1 | 33 | 0.9 | 0.95 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 21, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 63.39 sn, öbek başına 1.86 sn, 323.7 çıktı token/sn, toplam 44957 token, önek cache isabeti 0.5448
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

