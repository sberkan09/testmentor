# Altyapı

Paket 0 çıktısı. Sunum motorları, embedding servisi ve Postgres; Runpod'da ve yerelde tek komutla.

## Seçilen ortam

| Kalem | Değer |
| --- | --- |
| GPU | NVIDIA RTX PRO 6000 Blackwell Server Edition, 96 GB, Secure Cloud |
| Saatlik fiyat | 2,69 USD (`list-gpu-types`, 19 Kasım 2026) |
| Veri merkezi | EU-RO-1. Kartın stokta olduğu US-PA-1 ve US-NC-3 network volume desteklemiyor (`list-data-centers` → `networkVolumeTypes: []`). Kullanıcı kararıyla EU-RO-1. |
| Network volume | `testmentor-models` (`x5ts7eol5f`), 200 GB, STANDARD, EU-RO-1, `/models` altına bağlanır. Yaklaşık 0,07 USD/GB/ay → 14 USD/ay, günde 0,47 USD. Pod yokken de ücretlenir. |
| İndirme pod'u | CPU `cpu3c`, 4 vCPU, `python:3.12-slim`, 0,12 USD/saat |
| Ağırlıklar | Volume'da Hugging Face önbelleği: `HF_HOME=/models/hf` |
| Günlükler | Her pod başlangıcında `/models/logs/<zaman>-<motor>-<model>/` (volume'da kalır) |

## Mimari

- Üretim ve yerel ortam: `infra/compose.yaml` (Docker Compose). Profiller: `vllm` ve `sglang`. `embedding` ve `postgres` her profilde çalışır.
- Runpod: pod tek bir konteynerdir ve Compose çalıştıramaz ([doküman](https://docs.runpod.io/pods/overview)). Bu yüzden `make up` tek bir GPU pod'u açar. Pod'da motor, embedding servisi (yalnızca vLLM profilinde) ve Postgres ayrı süreçler olarak başlar.
- İki ortam da aynı ayar dosyalarından üretilir: `scripts/infra_render.py`. Compose dosyası üretilmiş bir dosyadır ve elle düzenlenmez. Güncel olduğunu `make test` denetler.
- Pod başlarken `HF_HUB_OFFLINE=1` ayarlıdır. Yeniden oluşturulan pod hiçbir şey indiremez, yalnızca volume'dan yükler.

| Servis | Port | Yol |
| --- | --- | --- |
| vLLM | 8000 | `https://<pod>-8000.proxy.runpod.net/v1` |
| SGLang | 30000 | `https://<pod>-30000.proxy.runpod.net/v1` |
| Embedding (vLLM pooling, BGE-M3) | 8001 | `https://<pod>-8001.proxy.runpod.net/v1` |
| Postgres 18 + pgvector 0.8.7 | 5432/tcp | pod'un genel IP'si ve eşlenmiş port (Runpod konsolu ya da `get-pod`) |

- Her uç nokta `LLM_API_KEY` ile korunur. Anahtar ilk `make up`'ta rastgele üretilir ve `.env` dosyasına yazılır; bu dosya depoya girmez.
- Postgres parolası (`POSTGRES_PASSWORD`) aynı şekilde üretilir.
- Hugging Face anahtarı yalnızca indirme pod'una `{{ RUNPOD_SECRET_HF_TOKEN }}` olarak verilir.

## Komutlar

| Komut | Ne yapar |
| --- | --- |
| `make test` | birim testleri, model çağrısı yok |
| `make balance` | Runpod bakiyesi |
| `make volume` | network volume'u oluşturur (yoksa; ücretli) |
| `make download` / `make download-down` | CPU pod'uyla tüm aday ağırlıkları volume'a indirir / pod'u siler |
| `make up` | GPU pod'unu açar, LLM yanıt verene kadar bekler, hazır olma süresini yazar |
| `ENGINE=sglang MODEL=gemma-4-31b make up` | başka motor ya da model; yalnızca ayar değişir |
| `make smoke` | 16 eşzamanlı, şemaya bağlı istek ve önek cache ölçümü; rapor `results/smoke/` |
| `make down` | pod'u siler, `get-pod` 404 ve `list-pods` ile doğrular, süre çarpı fiyatı yazar |
| `make compose` | `infra/compose.yaml` dosyasını yeniden üretir |
| `make local-up` / `make local-down` | yerel ya da üretim sunucusunda compose |

Runpod kimlik doğrulaması `RUNPOD_API_KEY` ortam değişkeniyle yapılır (`.env`). Betikler yalnızca `infra/.runpod-state.json` içine kendi yazdıkları kaynakları siler.

## Sürümler ve kaynaklar (19 Kasım 2026)

| Bileşen | Sürüm | Kaynak |
| --- | --- | --- |
| vLLM | `vllm/vllm-openai:v0.34.0` (CUDA 13.0) | [sürüm notu](https://github.com/vllm-project/vllm/releases/latest), [Docker Hub](https://hub.docker.com/r/vllm/vllm-openai/tags) |
| SGLang | `lmsysorg/sglang:v0.5.23` (CUDA 13) | [sürüm notu](https://github.com/sgl-project/sglang/releases/latest), [kurulum](https://docs.sglang.io/get_started/install.html) |
| Postgres | `pgvector/pgvector:0.8.7-pg18`; pod'da PGDG deposundan `postgresql-18` + `postgresql-18-pgvector` | [Docker Hub](https://hub.docker.com/r/pgvector/pgvector/tags) |
| Qwen3.8-27B | `Qwen/Qwen3.8-27B-FP8` (resmî, gated değil) | [HF](https://huggingface.co/Qwen/Qwen3.8-27B-FP8), [vLLM tarifi](https://recipes.vllm.ai/Qwen/Qwen3.8-27B) |
| Gemma 4 31B | `google/gemma-4-31B-it` (BF16; resmî FP8 yok; gated değil) | [HF](https://huggingface.co/google/gemma-4-31B-it), [vLLM tarifi](https://recipes.vllm.ai/Google/gemma-4-31B-it) |
| gpt-oss-120b | `openai/gpt-oss-120b` (MXFP4; gated değil) | [HF](https://huggingface.co/openai/gpt-oss-120b), [vLLM tarifi](https://recipes.vllm.ai/openai/gpt-oss-120b) |
| BGE-M3 | `BAAI/bge-m3` | [HF](https://huggingface.co/BAAI/bge-m3) |

Kullanılan bayrak ve parametreler:

- vLLM: `vllm serve <model>`, `--served-model-name`, `--max-model-len`, `--max-num-seqs`, `--gpu-memory-utilization`, `--enable-prefix-caching` (V1'de zaten varsayılan), `--enable-prompt-tokens-details` (cache'ten gelen token sayısını `usage.prompt_tokens_details.cached_tokens` içinde döndürür), `--api-key`, `--reasoning-parser`. Embedding servisi `--runner pooling --convert embed` ile çalışır. Kaynak: [serve CLI](https://docs.vllm.ai/en/latest/cli/serve.html).
- SGLang: `--model-path`, `--served-model-name`, `--context-length`, `--max-running-requests`, `--mem-fraction-static`, `--enable-cache-report`, `--grammar-backend xgrammar`, `--api-key`, `--reasoning-parser`. Kaynak: [sunucu argümanları](https://docs.sglang.io/advanced_features/server_arguments.html).
- Yapılandırılmış çıktı iki motorda da OpenAI'nin `response_format: {"type": "json_schema", "json_schema": {...}}` parametresiyle verilir. Böylece istemci motor değişiminde değişmez. vLLM'in eski `guided_json` parametreleri v0.12.0'da kaldırıldı. Kaynak: [vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs.html), [SGLang structured outputs](https://docs.sglang.io/advanced_features/structured_outputs.html).
- Düşünme istek başına açılıp kapanır: `chat_template_kwargs: {"enable_thinking": ...}`. gpt-oss'ta bunun yerine `reasoning_effort` kullanılır. Hangi alanın gönderileceği `config/models.yaml` dosyasındadır.
- vLLM düşünme metnini artık `reasoning` alanında döndürür; eski ad `reasoning_content`. `LLMClient` iki adı da okur.
- Akışta kullanım bilgisi için `stream_options: {"include_usage": true}` gönderilir. `LLMClient` her isteği akışlı gönderir; ilk token süresi böylece hep ölçülür.

## Paket 1 için

- `LLMClient.from_config()` ve `Embedder.from_config()` kullanın. Adres sırası: `LLM_BASE_URL` ortam değişkeni, sonra `infra/.runpod-state.json` (yalnızca `scripts/smoke.py` okur), sonra `config/runtime.yaml`.
- Motor ve model seçimi: `config/runtime.yaml`, ya da `LLM_ENGINE` ve `LLM_MODEL` ortam değişkenleri. Pod'u aynı değerlerle açın (`ENGINE=... MODEL=... make up`).
- Eşzamanlı dizi sınırı ve bağlam `config/models.yaml` dosyasında, GPU bellek payları `config/infra.yaml` dosyasındadır (D5).
- vLLM `/metrics` ucu anahtarla korunmaz: önek isabet oranı `vllm:prefix_cache_hits / vllm:prefix_cache_queries` ile okunur (D12).

## Doğrulama defteri

Her Runpod koşusundan sonra doldurulur.

| Tarih | Ne | GPU / kaynak | İmaj | Süre | Bellek tepe | Maliyet | Sonuç ve tuzaklar |
| --- | --- | --- | --- | --- | --- | --- | --- |
