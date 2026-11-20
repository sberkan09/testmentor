# d3-temp-03

- Soru: D3 Örnekleme: test üretiminde sıcaklık 0,3 (varsayım 0,7).
- Değişken: generation.temperature=0.3
- Koşu: `20261119-184104-d3-temp-03`, ayar `config/experiments/d3-temp-03.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 62 | 0.75 | 0.8125 |
| en | 20 | 1 | 1 | 0 | 1 | 26 | 0.65 | 0.725 |
| tr | 20 | 1 | 1 | 0 | 1 | 36 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 64.19 sn, öbek başına 1.89 sn, 336.4 çıktı token/sn, toplam 44825 token, önek cache isabeti 0.5373
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4539
- en: 0.5079
- tr: 0.4103

