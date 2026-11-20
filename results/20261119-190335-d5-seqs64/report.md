# d5-seqs64

- Soru: D5 Eşzamanlılık: sunucu dizi sınırı 64 (varsayım 32), 32 ve 64 eşzamanlı istekte.
- Değişken: max_num_seqs=64
- Koşu: `20261119-190335-d5-seqs64`, ayar `config/experiments/d5-seqs64.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 32 | 64 | 0 | 0.9844 | 447.5 | 1.294 | 2.767 | 207.4 | 1 |
| 64 | 128 | 0 | 1 | 1183 | 1.185 | 3.345 | 137.4 | 0 |

