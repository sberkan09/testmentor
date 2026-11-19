# d3-thinking-on

- Soru: D3 Düşünme modu: test üretiminde düşünme açık (sınıflandırmada kapalı kalır).
- Değişken: generation.thinking=true
- Koşu: `20261119-184434-d3-thinking-on`, ayar `config/experiments/d3-thinking-on.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 69 | 0.725 | 0.7875 |
| en | 20 | 1 | 1 | 0 | 1 | 31 | 0.6 | 0.675 |
| tr | 20 | 1 | 1 | 0 | 1 | 38 | 0.85 | 0.9 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 2 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 296.77 sn, öbek başına 8.73 sn, 359.2 çıktı token/sn, toplam 130367 token, önek cache isabeti 0.35
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Hakem (katman 2)

- check_recall: 0.4326
- en: 0.4444
- tr: 0.4231

