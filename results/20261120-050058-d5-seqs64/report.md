# d5-seqs64

- Soru: D5 Eşzamanlılık: sunucu dizi sınırı 64 (varsayım 32), 32 ve 64 eşzamanlı istekte.
- Değişken: max_num_seqs=64
- Koşu: `20261120-050058-d5-seqs64`, ayar `config/experiments/d5-seqs64.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `ib4b8vwnicumxq`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 32 | 64 | 0 | 1 | 767.6 | 1.497 | 2.9 | 101.1 | 0 |
| 64 | 128 | 0 | 1 | 1205 | 0.963 | 3.189 | 128.9 | 0 |

