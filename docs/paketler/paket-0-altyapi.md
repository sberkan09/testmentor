# Paket 0: altyapı

Model: Sonnet. Önkoşul: yok.

## Amaç

Aday sunum motorlarını, embedding servisini ve veritabanını Runpod'da tek komutla ayağa kaldıran, tekrar edilebilir bir altyapı ve uygulamanın modele eriştiği tek arayüz olan `LLMClient`.

## Ortam

- Runpod, Secure Cloud. GPU: RTX PRO 6000 Blackwell Server Edition 96 GB (üretim kartıyla aynı sınıf).
- 19 Kasım 2026 fiyatları (`list-gpu-types`): Secure 2,69 USD/saat, Community 1,69 USD/saat. Secure stok düşük ve yalnızca US-PA-1 veri merkezinde. Network volume yalnızca Secure Cloud pod'una bağlanabildiği için Secure seçildi.
- Ağırlıklar aynı veri merkezindeki bir network volume'da tutulur (200 GB ile başla; boyut yalnızca büyütülebilir). Pod her oturum sonunda silinir.
- Kart stokta yoksa başka karta geçme; dur ve sor.
- Yalnızca sentetik veri kullanılır.

## Bütçe

- Üst sınır 30 USD. 24 USD'ye ulaşılınca dur ve sor.
- Beklenen: 5–8 GPU saati (13–22 USD) ve volume ücreti. Volume'un GB başına ücretini oluştururken oku ve plana yaz.
- GPU pod'u yalnızca model yükleme ve ölçüm için açılır. Ağırlıklar mümkünse aynı veri merkezindeki ucuz bir CPU pod'uyla indirilir.
- Başlamadan önce hesap bakiyesinin bütçeyi karşıladığını doğrula.

## Çıktılar

- `infra/compose.yaml`: `vllm` ve `sglang` profilleri, embedding servisi, Postgres ve pgvector.
- `config/models.yaml`: aday modeller. Her biri için depo kimliği, hassasiyet, bağlam uzunluğu, eşzamanlı dizi sınırı.
- `services/llm_client.py`: eşzamansız, OpenAI uyumlu istemci.
  - `chat(messages, schema=None, max_tokens, temperature, thinking)`; akışlı ve akışsız.
  - Çalışan isteği iptal edebilme.
  - Her çağrı için ölçüm: girdi ve çıktı token'ı, cache'ten gelen token (motor bildiriyorsa), ilk token süresi, toplam süre.
- `services/embedder.py`: toplu embedding.
- `scripts/smoke.py`: altın setten bir öbekle 16 eşzamanlı, şemaya bağlı istek gönderir ve sonucu doğrular.
- `Makefile`: `make up`, `make down`, `make smoke`, `make test`.
- `docs/altyapi.md`: kurulum, çalıştırma, seçilen GPU ve saatlik maliyet.

## Adımlar

1. Runpod'da GPU seçeneklerini ve fiyatlarını listele; seçimi ve saatlik fiyatı yaz.
2. Qwen3.8-27B ile başla. Depo kimliğini resmî Qwen koleksiyonundan doğrula.
3. vLLM'i kur. Bayrakları ve yapılandırılmış çıktı parametrelerini güncel dokümandan al; sürümler arasında adlar değişti.
4. `LLMClient` arayüzünü ve testlerini yaz, sonra uygulamayı.
5. Embedding servisini ve Postgres'i ekle.
6. `scripts/smoke.py` ile ölç.
7. Aynı adımları SGLang profili için tekrarla.
8. Gemma 4 31B ve gpt-oss-120b ağırlıklarını indir ve her birinin yüklendiğini doğrula; ölçüm paket 1'in işidir.

## Bitti ölçütü

- `make smoke` tek komutla çalışır: 16 eşzamanlı isteğin tümü hatasız ve şemaya uygun döner.
- Aynı önekle gönderilen ikinci istekte cache etkisi ölçülür (cache'ten gelen token ya da ilk token süresindeki düşüş) ve rapora yazılır.
- Pod silinip aynı volume ile yeniden oluşturulduğunda servisler ağırlık indirmeden 10 dakika içinde hazır olur.
- Motor değişimi yalnızca profil ve ayar değişikliğidir; `LLMClient` kullanan kod değişmez.
- Oturum sonunda bu paketin oluşturduğu pod silinmiştir (`get-pod` 404, `list-pods` ile doğrulanmış); geriye yalnızca network volume kalır.
- `docs/altyapi.md` içindeki doğrulama defteri doldurulmuştur: GPU, imaj etiketi, süre, bellek tepe değeri, toplam maliyet, tuzaklar.

## Kapsam dışı

Ölçüm koşucusu, deneyler, prompt şablonları, pipeline mantığı, arayüz.
