# Paket 12 planı: internetsiz kurulum

23 Kasım 2026. Model: Opus. Kullanıcı: "Şirketteki makinede internet bağlantısı yok. Bu makinede çalıştırmak için bir yol bulmamız gerekiyor." Tasarım: Bileşenler (Dağıtım), `docs/pilot.md`.

## Yaklaşım

Kurum makinesi hiçbir şey indiremez. İnternete bağlı bir makinede her şey tek bir pakette toplanır, onaylı bir ortamla (disk) taşınır ve kurum makinesinde yalnızca yerel dosyalardan kurulur.

Paket içeriği:

- **İmajlar** (`docker save`, `linux/amd64`): `vllm/vllm-openai`, `pgvector/pgvector`, `testmentor-app`.
- **Model ağırlıkları:** Hugging Face önbelleği biçiminde, resmî hesaplardan (Qwen, BAAI), test edilen sürüme sabitlenmiş. `refs/main` kaydı yazılır; vLLM çevrimdışı çalışırken modeli bu kayıttan çözer.
- **Compose dosyası:** `build:` yok, her serviste `pull_policy: never`, `config/` dışarıdan bağlanır.
- **Betikler:** ön denetim (`preflight.sh`), kurulum (`install.sh`), doğrulama (`verify.sh`).
- `SHA256SUMS`, kurulum kılavuzu.
- **Gizli bilgi yok:** anahtarlar kurulumda üretilir.

Bileşenler ayrı dosyalardır. Sonraki bir güncelleme yalnızca uygulama imajını taşır. Boyut sınırlı ortamlar için dosyalar bölünebilir.

Kurulum aşamalıdır:

1. Uygulama ve Postgres sahte modelle açılır ve doğrulanır.
2. GPU servisleri açılır.
3. Doğrulama betiği her adımda açık hatayla durur.

vLLM'in boyut bayrakları (`--max-model-len`, `--max-num-seqs`, `--gpu-memory-utilization`) `.env` ile kurulum yerinde değişebilir.

## Çevrimdışı çalışma

GPU servislerine `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `VLLM_NO_USAGE_STATS=1` ve `DO_NOT_TRACK=1` verilir. Bunlar `scripts/infra_render.py`'den üretilir ve test edilir.

## Doğrulama

- **Paket betiği (burada):** uygulama imajı, Postgres imajı ve bge-m3 ağırlıklarıyla bir paket üretilir. Büyük vLLM imajı ve Qwen ağırlıkları burada indirilmez; disk yetmez.
- **Kurulum (burada):**
  - Paket boş bir Docker veri kökü olan ikinci bir daemon'a yüklenir; önbellekteki imajlar eksiği gizlemesin.
  - Kapsayıcı içinden dış adrese isteğin başarısız olduğu, uygulamanın ise ana makineden erişilebildiği gösterilir.
  - Playwright akışı bu kuruluma karşı koşar.
- **GPU yolu (Runpod, çevrimdışı prova):**
  - vLLM ve embedding süreçlerinin bütün HTTP çıkışı ölü bir vekile yönlendirilir. Bekçi vekilsiz kalır, kendini silebilmesi gerekir.
  - Duman testi (`make smoke`) koşar.
  - Volume'daki model sürümleri okunur, paketin sabitlediği sürümlerle karşılaştırılır.

## Doğrulanamayanlar (raporda açıkça)

- Ölü vekil, ham soket bağlantılarını yakalamaz.
- Volume'daki önbellek internetli koşularla dolduruldu. Sıfırdan indirilen paket daha az dosya içerebilir; provadan sonra eksik dosya listesi karşılaştırılır.
- Pod Compose değildir. Şunlar kurum makinesinde ilk kurulumda doğrulanır:
  - iki vLLM kapsayıcısının tek GPU'yu paylaşması;
  - `llm` ağ takma adı;
  - sağlık denetimleri;
  - sürücü ve container toolkit uyumu.

## Kullanıcıdan gereken bilgiler

- Kurum makinesi:
  - GPU modeli ve belleği;
  - işletim sistemi ve işlemci mimarisi;
  - Docker ile Compose eklentisinin kurulu olup olmadığı;
  - NVIDIA sürücüsü ile container toolkit'in kurulu olup olmadığı.
- Paketi hangi internetli makinenin üreteceği.
- Taşıma yolu: dosya boyutu sınırı, tarama.

## Uygulamada netleşenler

- **Paketi üretme:** `make offline-bundle OUT=dizin` (`infra/offline/build.sh`). Derleme makinesinde yalnızca Docker gerekir; Python adımları uygulama imajının içinde koşar.
- **Model sürümleri** `config/` içinde sabit (`revision`): Qwen/Qwen3.8-27B-FP8 `c3a462cc…`, BAAI/bge-m3 `5617a9f6…`. İkisi de onay istemiyor. bge-m3'ün ONNX kopyası pakete girmez.
- **Ağırlıklar tek tar dosyası (`models.tar`):** Hugging Face önbelleği sembolik bağlantılarla çalışır ve FAT/exFAT diskler bunları taşıyamaz. Kurulum dosyayı açar.
- **Kurum vekili:** TLS'i yeniden imzalayan bir vekil varsa kök sertifika `EXTRA_CA` ile verilir. Model indirmede `requests` kütüphanesi için `REQUESTS_CA_BUNDLE` da gerekir; bu ortamda bulundu.
- **Model sunucusunun boyut bayrakları** Compose'ta `.env` değişkenleridir: `LLM_MAX_MODEL_LEN`, `LLM_MAX_NUM_SEQS`, `LLM_GPU_MEMORY_UTILIZATION`, `EMBEDDING_GPU_MEMORY_UTILIZATION`.

### Doğrulama

- **Burada:** paket üretildi (uygulama ve Postgres imajları, bge-m3; vLLM imajı ve Qwen hariç). Ardından:
  - Boş veri köklü Docker'da ve kapsayıcıların dışarı yeni bağlantısı iptables ile kapalıyken (`DOCKER-USER`) paket başka bir dizinden kuruldu.
  - `STAGE=1 bash install.sh` geçti: sağlama, `docker load`, `.env`, ön denetim, sahte modelle küçük proje Postgres'e yazıldı.
  - Pilot ayarıyla (parolalı giriş) Playwright 3/3 geçti.
  - `verify.sh egress`: dışarıya erişim yok. Kontrol koşusunda engel kaldırılınca düz HTTP ile erişim görüldü; yani denetim gerçek.
- **Runpod'da çevrimdışı prova yapılamadı.**
  - 1. deneme: pod açıldı ama makine network volume'u bağlayamadı ve kapsayıcı hiç oluşmadı (0,50 saat, ~1,35 USD). Bu olay kredi korumasında bir açık gösterdi: `wait` artık zaman aşımında pod'u siliyor.
  - 2. deneme: EU-RO-1'de stok yoktu, pod oluşmadı, ücret doğmadı.
  - Prova araçları hazır: `make up OFFLINE=1` ile model ve embedding süreçlerinin çıkışı ölü vekile gider, bekçi bunun dışında kalır.
- **Kalan risk:** vLLM'in çevrimdışı ilk açılışı (çekirdek dosyası ya da telemetri indirmeye çalışıp çalışmadığı) yalnızca kurum makinesinde 2. aşamada, `verify.sh full` ile doğrulanacak. Compose GPU servisleri de orada ilk kez koşacak. Kurulum aşamalı olduğu için uygulama tarafı ondan önce doğrulanmış olur.
