# d5-seqs16

- Soru: D5 Eşzamanlılık: sunucu dizi sınırı 16 (varsayım 32), 32 ve 64 eşzamanlı istekte.
- Değişken: max_num_seqs=16
- Koşu: `20261119-185244-d5-seqs16`, ayar `config/experiments/d5-seqs16.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 32 | 64 | 0 | 1 | 477.1 | 33.94 | 44.88 | 181.2 | 0 |
| 64 | 128 | 3 | 0.9766 | 533.4 | 94.4 | 107.3 | 293.5 | 0 |

