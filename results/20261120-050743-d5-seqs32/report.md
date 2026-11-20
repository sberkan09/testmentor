# d5-seqs32

- Soru: D5 Eşzamanlılık: sunucu dizi sınırı 32, 32 ve 64 eşzamanlı istekte.
- Değişken: max_num_seqs=32
- Koşu: `20261120-050743-d5-seqs32`, ayar `config/experiments/d5-seqs32.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `ib4b8vwnicumxq`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 32 | 64 | 0 | 0.9844 | 395.4 | 1.504 | 2.745 | 215 | 1 |
| 64 | 128 | 0 | 1 | 872.9 | 36.06 | 44.85 | 177.2 | 0 |

