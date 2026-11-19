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

## Smoke sonuçları (19 Kasım 2026)

16 eşzamanlı, şemaya bağlı istek. Öbek: KK-001…KK-004 (altın setin en büyük referans öbeği). Düşünme kapalı, sıcaklık 0,7. Ölçüm Runpod HTTP vekili üzerinden yapıldı. Ham raporlar `results/smoke/` altında yerelde durur, depoya girmez. Bunlar altyapının çalıştığının kanıtıdır; motor ve model karşılaştırması D1 ve D2'nin işidir.

| Saat (UTC) | Motor | Model | Hata | Şemaya uygun | Tüm gereksinimler kapsanmış | Çıktı token/sn | İlk token medyan / en yüksek (sn) | Cache probu: cache'ten gelen / prompt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16:27 | vllm | qwen3.8-27b | 0 | 16/16 | 16/16 | 516,1 | 1,344 / 1,694 | 0 / 813 (önek 832'lik bloktan kısa) |
| 16:28 | vllm | qwen3.8-27b | 0 | 16/16 | 16/16 | 584,7 | 0,936 / 0,996 | 2.496 / 3.241 |
| 16:42 | vllm (yeniden oluşturulan pod) | qwen3.8-27b | 0 | 16/16 | 16/16 | 448,1 | 0,989 / 1,052 | 2.496 / 3.240 |
| 16:54 | sglang | qwen3.8-27b | 0 | 16/16 | 16/16 | 464,5 | 1,000 / 1,249 | 0 / 3.238 |
| 17:10 | vllm | gemma-4-31b | 0 | 16/16 | 16/16 | 291,4 | 1,081 / 1,086 | 0 / 3.115 |
| 17:15 | vllm | gpt-oss-120b | 0 | 16/16 | 16/16 | 925,3 | 0,842 / 0,869 | 3.136 / 3.181 |

## Paket 1 için

- `LLMClient.from_config()` ve `Embedder.from_config()` kullanın. Adres sırası: `LLM_BASE_URL` ortam değişkeni, sonra `infra/.runpod-state.json` (yalnızca `scripts/smoke.py` okur), sonra `config/runtime.yaml`.
- Motor ve model seçimi: `config/runtime.yaml`, ya da `LLM_ENGINE` ve `LLM_MODEL` ortam değişkenleri. Pod'u aynı değerlerle açın (`ENGINE=... MODEL=... make up`).
- Eşzamanlı dizi sınırı ve bağlam `config/models.yaml` dosyasında, GPU bellek payları `config/infra.yaml` dosyasındadır (D5).
- vLLM `/metrics` ucu anahtarla korunmaz: önek isabet oranı `vllm:prefix_cache_hits / vllm:prefix_cache_queries` ile okunur (D12).
- **Önek cache blok boyu.** Qwen3.8-27B hibrit bir model (linear attention + tam attention). vLLM 0.34 bu modelde cache'i 832 token'lık bloklarla tutuyor (`kv lcm block sizes 832`) ve yalnızca tam blokları yeniden kullanıyor. 832 token'dan kısa bir ortak önek hiç isabet almaz. Ölçüm: 804 token'lık öneklerde `cached_tokens` 0 çıktı; 3.241 token'lık prompt'ta ortak önekin 2.496 token'ı (3 blok) cache'ten geldi. Prompt şablonlarında (paket 3) ortak önek (sistem talimatı, proje kartı, şema ve örnekler) bunu hesaba katmalı.
- **SGLang'da hibrit model cache'i farklı çalışır.** SGLang 0.5.23, Qwen3.8'in Mamba/GDN durumunu yalnızca belirli noktalarda saklıyor ("Unified Radix Cache", FULL + MAMBA). Pod içi ölçümde 3,3 bin token'lık ortak önek farklı kuyrukla hiç isabet almadı, aynı prompt tamamen isabet aldı; 14,9 bin ve 30,9 bin token'da farklı kuyruk da isabet aldı. `max_running_requests` Mamba durum önbelleği yüzünden 30 ile sınırlandı (`--mamba-full-memory-ratio` ya da `--max-mamba-cache-size` ile artırılabilir). D1 ve D12 bunu ölçmeli.
- Pod içi önek cache ölçümü (localhost, 8 token çıktı, ilk token süresi):

  | Prompt | vLLM soğuk | vLLM sıcak (farklı kuyruk) | SGLang soğuk | SGLang sıcak (farklı kuyruk) |
  | --- | --- | --- | --- | --- |
  | 3,3 bin token | 0,314 sn | 0,096 sn (2.496 cache) | 0,313 sn | 0,306 sn (0 cache) |
  | 14,9 bin token | 1,458 sn | 0,126 sn (14.144) | 1,541 sn | 0,043 sn (14.912) |
  | 30,9 bin token | 3,342 sn | 0,083 sn (30.784) | 3,673 sn | 0,143 sn (30.912) |
- **Gemma 4 31B BF16 belleğe zor sığıyor.** Ağırlıklar 59 GB. `gpu_memory_utilization: 0.88` ile KV cache 44.755 token ve 32k bağlamda yalnızca 1,37 eşzamanlı dizi var. Uzun bağlamda 16 eşzamanlı istek bu ayarla mümkün değil. D4 (FP8 anlık nicemleme) ve D5 bunu ele almalı. Ortak önek bu modelde de 3,1 bin token'da farklı kuyrukla isabet almadı (kayan pencere katmanları).
- Bir pod'un başlatma komutu pod silinmeden `PATCH /v2/pods/{id}` (`entrypoint`) ile değiştirilebilir. İmaj aynı host'ta kaldığı için yeniden çekilmez; model değiştirmek dakikalar kazandırır.
- Runpod HTTP vekili üzerinden ölçülen ilk token süresine vekilin gidiş-dönüşü de dahildir. Mutlak değerler sunucu içinden ölçülenden yüksek çıkar; karşılaştırmalar aynı yoldan yapılmalıdır.

## Doğrulama defteri

Her Runpod koşusundan sonra doldurulur.

| Tarih | Ne | GPU / kaynak | İmaj | Süre | Bellek tepe | Maliyet | Sonuç ve tuzaklar |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 19.11 16:00 | Network volume `x5ts7eol5f` | 200 GB STANDARD, EU-RO-1 | | sürüyor | | yaklaşık 0,47 USD/gün | US-PA-1 ve US-NC-3 volume desteklemiyor (`networkVolumeTypes: []`); kullanıcı kararıyla EU-RO-1. |
| 19.11 16:07 | İndirme 1 (`2qwpwbwmhcs2ql`) | CPU cpu3c × 4 | `python:3.12-slim` | 8 dk | | yaklaşık 0,02 USD | BGE-M3 6 sn, Qwen3.8-27B-FP8 27 sn, Gemma 4 31B 58 sn. gpt-oss-120b'de "Disk quota exceeded": depoda aynı ağırlığın `original/` ve `metal/` kopyaları da var (3 × 65 GB). Betik hata verince konteyner yeniden başlayıp indirmeyi döngüye soktu. |
| 19.11 16:16 | İndirme 2 (`zzic3g0tunnrfi`) | CPU cpu3c × 4 | `python:3.12-slim` | 2 dk | | < 0,01 USD | `download_ignore` ve `trap ... sleep infinity` eklendi. Bu `huggingface_hub` sürümü ortak `hub/blobs/` dizini kullanıyor; snapshot dizinini silmek blob'ları silmiyor. 33,7 GB sahipsiz blob `exec-pod` ile temizlendi. Volume'da 153 GB. |
| 19.11 16:21 | vLLM + Qwen3.8-27B-FP8 (`1c4m9kh8xbzovz`) | RTX PRO 6000 Blackwell SE, EU-RO-1, host CUDA 13.2, sürücü 595.112.07 | `vllm/vllm-openai:v0.34.0` | 12 dk | 79,3 / 97,9 GB (LLM 77,2 GB, KV cache 45,35 GiB; embedding 2,1 GB) | yaklaşık 0,55 USD | Pod oluşturmadan 341 sn sonra hazır (imaj çekme yaklaşık 2 dk, ağırlık yükleme ve autotune yaklaşık 3 dk). Smoke geçti. `minCudaVersion: "13.0"` gönderilince API stok varken "no instances available" dedi; alan kaldırıldı, CUDA sonradan denetleniyor. `5432/tcp` da kaldırıldı (genel IP ister). Postgres: volume (MooseFS) `chown`'a izin vermiyor, veri konteyner diskine alındı; `/tmp`'de `protected_regular` parola dosyası yazımını engelledi. |
| 19.11 16:34 | vLLM + Qwen yeniden oluşturma (`vbj0ny9tq5nqxr`) | aynı, farklı host | `vllm/vllm-openai:v0.34.0` | 10 dk | 79 GB | yaklaşık 0,45 USD | **Silinen pod aynı volume ile 438 sn'de hazır, indirme yok** (`HF_HUB_OFFLINE=1`). Döküm: imaj çekme 4 dk (yeni host), ağırlık yükleme 55,6 sn, motor başlatma 104 sn. Stok yoktu, 2 denemeden sonra pod açıldı (`create_retries` eklendi). Smoke geçti. |
| 19.11 16:47 | SGLang + Qwen (`b2m33up6chrylw`) | aynı | `lmsysorg/sglang:v0.5.23` | 9 dk | 84,3 GB | yaklaşık 0,40 USD | 407 sn'de hazır. Smoke geçti. `max_running_requests` Mamba durum önbelleği yüzünden 30'a indirildi. Hibrit modelde kısa ortak önek farklı kuyrukla cache'ten yararlanmıyor (bkz. Paket 1 için). Embedding servisi bu profilde başlamaz. |
| 19.11 16:55 | vLLM + Gemma 4 31B BF16 (`w9jt6oa6wmju8u`) | aynı | `vllm/vllm-openai:v0.34.0` | 17 dk | 86,5 GB | yaklaşık 0,75 USD | İlk açılış döngüye girdi: %80 bellekle KV'ye 15,1 GB kaldı, 32k'lık tek dizi 15,8 GB istiyor ("Engine core initialization failed"; Runpod konteyneri yeniden başlatıyor, pod "RUNNING" görünüyor). Model başına `gpu_memory_utilization: 0.88` eklendi; pod silinmeden başlatma komutu `PATCH /v2/pods/{id}` ile güncellendi, 2 dk'da hazır. KV cache 44.755 token: 32k bağlamda en fazla 1,37 eşzamanlı dizi. Yükleme 6,4 sn, motor başlatma 54 sn. Smoke geçti (291 token/sn). |
| 19.11 17:12 | vLLM + gpt-oss-120b MXFP4 (`b8szi31b3t3gj8`) | aynı | `vllm/vllm-openai:v0.34.0` | 9 dk | 79,9 GB (ağırlık 66,1 GiB, KV 8,35 GiB = 254.323 token) | yaklaşık 0,42 USD | 194 sn'de hazır (imaj host'ta vardı). sm_120'de MARLIN MXFP4 MoE arka ucu ve FlashInfer attention seçildi; ağırlık yükleme 100,6 sn. Smoke geçti (925 token/sn); farklı kuyrukla 3.136 token cache'ten geldi. |
| **Toplam** | | | | GPU yaklaşık 0,95 saat | | **2,34 USD** (bakiye 43,04 → 40,70; volume dahil) | Pod kalmadı (`list-pods` boş, son pod `get-pod` 404). Geriye yalnızca `testmentor-models` volume'u kaldı (günde yaklaşık 0,47 USD). |
