# d2-long-qwen

- Soru: D2 uzun bağlam: Qwen3.8-27B, istek başına ~12 bin token getirilmiş parça (bilgi havuzu yükü), 8 ve 16 eşzamanlı istekte hız ve ilk token.
- Değişken: model=qwen3.8-27b, passage_tokens=12000
- Koşu: `20261120-045435-d2-long-qwen`, ayar `config/experiments/d2-long-qwen.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / qwen3.8-27b (sunulan ad `qwen3.8-27b`, pod `ib4b8vwnicumxq`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | 16 | 0 | 1 | 185.8 | 3.675 | 11.64 | 109 | 0 |
| 16 | 32 | 0 | 1 | 391.9 | 1.192 | 1.64 | 100 | 0 |

