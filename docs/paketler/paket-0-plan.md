# Paket 0 planı

Tarih: 19 Kasım 2026. Görev tanımı: [`paket-0-altyapi.md`](paket-0-altyapi.md).

## Doğrulanan fiyat, stok ve bakiye (19 Kasım 2026)

| Kalem | Değer | Kaynak |
| --- | --- | --- |
| GPU | NVIDIA RTX PRO 6000 Blackwell Server Edition, 96 GB | `list-gpu-types` (POD, SECURE, AVAILABILITY) |
| Saatlik fiyat | Secure 2,69 USD, Community 1,69 USD | aynı çıktı |
| Stok | `LOW`; veri merkezleri US-PA-1, US-NC-3, EUR-IS-1; CUDA 13.2 | aynı çıktı |
| Seçilen veri merkezi | US-PA-1 (görev tanımındaki ile aynı) | |
| Network volume | 200 GB, STANDARD, US-PA-1. Ücret: hesaptaki mevcut 20 GB volume günde 0,0467 USD tutuyor, yani yaklaşık 0,07 USD/GB/ay. 200 GB için yaklaşık 14 USD/ay, günde 0,47 USD. Kesin ücret oluştururken okunacak. | `list-billing` |
| Hesap bakiyesi | **13,04 USD** | GraphQL `myself.clientBalance` |
| Harcama sınırı | 80 USD | aynı sorgu |
| Mevcut kaynaklar | pod yok; `neuracraft-models` volume'u (EU-RO-1, başka proje, dokunulmaz) | `list-pods`, `list-network-volumes` |
| HF anahtarı | Runpod Secret `HF_TOKEN` mevcut | `list-secrets` |

## Tahmini GPU saati ve maliyet

| Kalem | Süre | Birim fiyat | Tutar |
| --- | --- | --- | --- |
| CPU pod ile ağırlık indirme (Qwen3.8-27B, Gemma 4 31B, gpt-oss-120b, BGE-M3; yaklaşık 160 GB) | 2 saat | yaklaşık 0,10–0,25 USD/saat | 0,5 USD |
| vLLM: yükleme, smoke, cache ölçümü, yeniden oluşturma süresi | 2,5 saat | 2,69 USD | 6,7 USD |
| SGLang: aynı adımlar | 2 saat | 2,69 USD | 5,4 USD |
| Gemma 4 ve gpt-oss-120b yükleme doğrulaması | 1 saat | 2,69 USD | 2,7 USD |
| Volume (200 GB, paket süresince yaklaşık 3 gün) | | 0,47 USD/gün | 1,4 USD |
| **Toplam** | 5,5 GPU saati | | **yaklaşık 17 USD** |

Tahmin 30 USD üst sınırın ve 24 USD durma eşiğinin içinde. **Ancak bakiye (13,04 USD) bütçeyi karşılamıyor ve tahmini harcamanın da altında.** CLAUDE.md'ye göre bakiye sıfırlanınca pod durur ve çalışan iş kaybolur. Bu yüzden ücret doğuran hiçbir kaynak (volume, CPU pod, GPU pod) bakiye yükseltilene kadar oluşturulmaz. Pod gerektirmeyen işler (aşağıda 1–6) yapılır.

## Adımlar

Pod kapalıyken (ücretsiz):

1. Güncel resmî dokümandan vLLM ve SGLang imaj etiketleri, bayraklar, yapılandırılmış çıktı parametreleri, model depo kimlikleri ve erişim koşulları (gated mi) doğrulanır ve `docs/altyapi.md` içine kaynak bağlantılarıyla yazılır.
2. `services/llm_client.py` arayüzü ve testleri yazılır (sahte OpenAI uyumlu sunucuya karşı; model çağrısı yok): akışlı ve akışsız `chat`, şema, iptal, ölçüm. Sonra uygulama.
3. `services/embedder.py` ve testleri.
4. `config/`: `models.yaml` (adaylar), `engines.yaml` (motor bayrakları), `runtime.yaml` (etkin motor ve model, adresler), `infra.yaml` (Runpod GPU, veri merkezi, volume).
5. `infra/compose.yaml`: `vllm` ve `sglang` profilleri, embedding servisi, Postgres ve pgvector. Üretim sunucusu ve yerel çalışma için.
6. Runpod tarafı: Runpod pod'u bir konteynerdir, içinde Docker Compose çalışmaz (araştırmayla doğrulanacak). `make up` aynı ayar dosyalarından Runpod REST API ile pod oluşturan `scripts/runpod_up.py` betiğini çağırır; motor komut satırı compose ile aynı kaynaktan (`config/engines.yaml`) üretilir. `make down` pod'u siler ve 404 ile doğrular. `scripts/smoke.py`, `Makefile`, `docs/altyapi.md`.

Bakiye yükseltildikten sonra (ücretli):

7. US-PA-1'de 200 GB network volume; ücret okunup bu dosyaya yazılır.
8. Aynı veri merkezinde ucuz CPU pod'u ile ağırlıklar volume'a indirilir; pod silinir.
9. GPU pod'u vLLM profiliyle açılır: `make smoke`, önek cache ölçümü. Pod silinir, aynı volume ile yeniden oluşturulup hazır olma süresi ölçülür (hedef 10 dakika).
10. SGLang profiliyle 9 tekrarlanır.
11. Gemma 4 31B ve gpt-oss-120b'nin yüklendiği doğrulanır.
12. Pod silinir, `get-pod` 404 ve `list-pods` ile doğrulanır; doğrulama defteri doldurulur; PR açılır.

Her GPU oturumundan önce bakiye kontrol edilir; birikimli harcama 24 USD'ye ulaşırsa durulur.
