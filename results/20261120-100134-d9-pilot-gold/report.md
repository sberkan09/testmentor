# d9-pilot-gold

- Soru: D9 pilotu (paket 1b aşama 6): altın set v1, öbeğin destek parçaları (kâhin getirme) ile üretim; belge gerektiren denetimlerde parçasız koşudan anlamlı biçimde iyi olmalı.
- Değişken: passages=gold
- Koşu: `20261120-100134-d9-pilot-gold`, ayar `config/experiments/d9-pilot-gold.yaml`, şablon `t2`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `yc4gv8dwkeq12h`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9956 | 0 | 1 | 510 | 0.6769 | 0.8035 |
| en | 169 | 1 | 1 | 0 | 1 | 387 | 0.8047 | 0.8817 |
| tr | 60 | 1 | 0.9833 | 0 | 1 | 123 | 0.3167 | 0.5833 |
| tuzak | 1 | 1 | 1 | 0 | 1 | 3 | 1 | 1 |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 109, hata 0, şema geçerliliği 1 (üretim 1)
- Süre 423.38 sn, öbek başına 10.08 sn, 398.6 çıktı token/sn, toplam 387567 token, önek cache isabeti 0.4639
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

