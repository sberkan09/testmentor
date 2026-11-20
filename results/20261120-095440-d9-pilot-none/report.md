# d9-pilot-none

- Soru: D9 pilotu (paket 1b aşama 6): altın set v1, bilgi havuzu parçası olmadan üretim; altın parçalı koşuyla karşılaştırılır.
- Değişken: passages=none
- Koşu: `20261120-095440-d9-pilot-none`, ayar `config/experiments/d9-pilot-none.yaml`, şablon `t2`, altın set `v1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `yc4gv8dwkeq12h`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Kalite koşusu 1

| küme | requirements | coverage_rate | coverage_rate_before_repair | no_test_violations | step_structure_rate | test_cases | method_exact_match | method_jaccard |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tümü | 229 | 1 | 0.9956 | 0 | 1 | 500 | 0.6812 | 0.8049 |
| en | 169 | 1 | 0.994 | 0 | 1 | 383 | 0.8047 | 0.8817 |
| tr | 60 | 1 | 1 | 0 | 1 | 117 | 0.3333 | 0.5889 |
| tuzak | 1 | 1 | 1 | 0 | 1 | 3 | 1 | 1 |

- Öbek uyumu (ARI): 0.3284
- Çağrı: 109, hata 0, şema geçerliliği 0.9908 (üretim 0.9899)
- Süre 411.42 sn, öbek başına 9.8 sn, 408 çıktı token/sn, toplam 325516 token, önek cache isabeti 0.5119
- Katman 1 eşikleri: schema_valid_rate ✓, coverage_rate ✓, step_structure_rate ✓, no_test_violations ✓

