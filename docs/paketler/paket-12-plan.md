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

(doldurulacak)
