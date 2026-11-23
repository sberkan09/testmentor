# d8-merge

- Soru: D8 Yeniden üretim, birleştirme: komşu öbek çiftleri birleşir; birleştirme prompt'u (tekrar ayıklama, çalışma varsayımı) ile baştan üretim aynı taban üzerinde karşılaştırılır. Tekrar oranı, kapsama, recall, süre.
- Değişken: merge_sources (true | false)
- Koşu: `20261120-222244-d8-merge`, ayar `config/experiments/d8-merge.yaml`, prompt `method s1.m1+5d9f798bd379, test_set s1.g3+18f7be32bb16`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `j9flebx3g2ibqh`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_predicted | coverage_rate_before_repair | no_test_violations | no_test_violations_raw | step_structure_rate | test_cases | method_exact_match | method_jaccard | duplicate_test_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | – | 0 | 0 | 0 | 1 | 486 | 0 | 0 | 0.1296 |
| en | 169 | 1 | – | 0 | 0 | – | 1 | 374 | 0 | 0 | – |
| tr | 60 | 1 | – | 0 | 0 | – | 1 | 112 | 0 | 0 | – |
| tuzak | 1 | 1 | – | 0 | 0 | – | 1 | 3 | 0 | 0 | – |

- Öbek uyumu (ARI): –
- Çağrı: 201, hata 0, şema geçerliliği 0.995 (üretim 0.9934)
- Süre 947.21 sn, öbek başına – sn, 281.6 çıktı token/sn, toplam 666476 token, önek cache isabeti 0.4683
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

### Senaryo (merge, D8; taban çağrısı 99)

| kol | units | change_calls | change_completion_tokens | change_call_s | change_wall_s | duplicate_pairs | duplicate_test_rate | coverage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prompt | 49 | 50 | 1104 | 247.4 | 25.91 | 46 | 0.1296 | 1 |
| full | 49 | 52 | 112411 | 2909 | 202.2 | 23 | 0.0923 | 1 |

## Hakem (katman 2)

- check_recall: 0.4412
- en: 0.494
- tr: 0.3476

