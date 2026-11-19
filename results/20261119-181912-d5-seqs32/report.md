# d5-seqs32

- Soru: D5 Eşzamanlılık: sunucu dizi sınırı 32 (varsayım), 32 ve 64 eşzamanlı istekte; karşılaştırma tabanı.
- Değişken: max_num_seqs=32
- Koşu: `20261119-181912-d5-seqs32`, ayar `config/experiments/d5-seqs32.yaml`, şablon `t1`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `v71zvphir46gad`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 32 | 64 | 0 | 1 | 827.8 | 0.873 | 1.837 | 96.73 | 0 |
| 64 | 128 | 0 | 1 | 865.7 | 35.76 | 44.78 | 183.3 | 0 |

