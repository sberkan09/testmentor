# d2-qwen-r3

- Soru: D2 tekrar: Qwen3.8-27B, güncel ayarlarla 3 koşu (gürültüyü ölçmek ve gpt-oss ile aynı koşullarda karşılaştırmak için).
- Değişken: model=qwen3.8-27b
- Koşu: `20261120-044830-d2-qwen-r3`, ayar `config/experiments/d2-qwen-r3.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `ib4b8vwnicumxq`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 62 | 0.775 | 0.8375 |
| en | 20 | 1 | 1 | 0 | 1 | 26 | 0.6 | 0.7 |
| tr | 20 | 1 | 1 | 0 | 1 | 36 | 0.95 | 0.975 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 64.82 sn, öbek başına 1.91 sn, 318.4 çıktı token/sn, toplam 43870 token, önek cache isabeti 0.3582
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 2

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 65 | 0.75 | 0.825 |
| en | 20 | 1 | 1 | 0 | 1 | 27 | 0.6 | 0.7 |
| tr | 20 | 1 | 1 | 0 | 1 | 38 | 0.9 | 0.95 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 64.22 sn, öbek başına 1.89 sn, 327.5 çıktı token/sn, toplam 44259 token, önek cache isabeti 0.5373
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Kalite koşusu 3

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 40 | 1 | 1 | 0 | 1 | 59 | 0.775 | 0.825 |
| en | 20 | 1 | 1 | 0 | 1 | 25 | 0.6 | 0.675 |
| tr | 20 | 1 | 1 | 0 | 1 | 34 | 0.95 | 0.975 |
| tuzak | 4 | 1 | 1 | 0 | 1 | 1 | 0.75 | 0.875 |

- Öbek uyumu (ARI): 0.094
- Çağrı: 20, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 61.51 sn, öbek başına 1.81 sn, 337.8 çıktı token/sn, toplam 44005 token, önek cache isabeti 0.5373
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

## Tekrar karşılaştırması (katman 1)

- all.method_exact_match: 0.775 → 0.75
- all.method_jaccard: 0.8375 → 0.825
- all.test_cases: 62 → 65
- by_language.en.test_cases: 26 → 27
- by_language.tr.method_exact_match: 0.95 → 0.9
- by_language.tr.method_jaccard: 0.975 → 0.95
- by_language.tr.test_cases: 36 → 38

## Hakem (katman 2)

- check_recall: 0.4539
- en: 0.4603
- tr: 0.4487

