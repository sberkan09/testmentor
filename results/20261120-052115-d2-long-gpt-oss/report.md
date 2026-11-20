# d2-long-gpt-oss

- Soru: D2 uzun bağlam: gpt-oss-120b, istek başına ~12 bin token getirilmiş parça, 8 ve 16 eşzamanlı istekte hız ve ilk token.
- Değişken: model=gpt-oss-120b, passage_tokens=12000
- Koşu: `20261120-052115-d2-long-gpt-oss`, ayar `config/experiments/d2-long-gpt-oss.yaml`, şablon `t2`, altın set `v0.1`
- Sunucu: vllm / gpt-oss-120b (sunulan ad `gpt-oss-120b`, pod `ib4b8vwnicumxq`)
- Hakem (katman 2) bu raporda yok; `python -m eval.judge` ile eklenir.

## Yük ölçümü

| concurrency | requests | errors | schema_valid_rate | output_tokens_per_s | ttft_p50_s | ttft_p95_s | wall_s | finish_length |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | 16 | 0 | 1 | 430.8 | 2.756 | 5.912 | 55.54 | 0 |
| 16 | 32 | 0 | 1 | 707.7 | 1.099 | 1.269 | 64.04 | 0 |

