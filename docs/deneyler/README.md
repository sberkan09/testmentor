# Deney raporları (paket 1)

19 Kasım 2026. Tablolar `python -m eval.summarize` ile `results/` altındaki koşulardan üretilir (`D1.md` … `D12.md`). Bu dosya kararları ve uyarıları özetler; sonuçlar `docs/tasarim.md` Deney planı tablosunun Sonuç sütununa da işlendi.

## Uyarılar

- **D0 koşulmadı.** Test mühendisi yok. Katman 2 puanları (Claude Sonnet 5.5 hakem, rubrik r1) uzman puanıyla doğrulanmadı. Hakem ve referans aynı model ailesinden olduğu için Claude'a benzeyen çıktılar kayırılmış olabilir.
- **Altın set sentetik (v0.1) ve küçük.** 40 gereksinim, 141 referans denetim. Aynı ayarla iki koşu arasında `check_recall` 0,06'ya kadar oynuyor (d2-qwen: 0,48 ve 0,42). Bundan küçük farklar karar için yeterli değil.
- **Tekrarlanabilirlik.** Aynı ayarla iki koşu katman 1'de birebir aynı çıkmıyor: sıcaklık 0'daki sınıflandırmada bile yöntem doğruluğu 0,725 ile 0,775 arasında, test sayısı 60 ile 70 arasında değişti. Kapsama, ihlal, adım yapısı ve şema iki koşuda da aynı (1,0 / 0 / 1,0 / 1,0). Farklar ilgili raporun "Tekrarlanabilirlik" bölümünde.
- **Ölçüm yöntemi.** Test üretimi referans öbek ve referans yöntemlerle beslendi (`generation_inputs: reference`; bkz. tasarım, Deney planı kuralları). Yöntem doğruluğu ve öbekleme uyumu ayrı ölçüldü.
- **Hız ölçümleri Runpod HTTP vekili üzerinden.** İlk token sürelerine vekilin gidiş-dönüşü dahil.
- `d1-vllm` kalite satırı şablon t1 ve uçtan uca girdiyle koşuldu; diğer kalite koşuları t2 ve referans girdiyle. D1'in kararı yük ölçümüne dayanır.

## Kararlar

| No | Karar | Gerekçe | Ayar |
| --- | --- | --- | --- |
| D1 | vLLM | 32 eşzamanlı istekte 777 token/sn (SGLang 698); ikisinde de hata 0, şema %100. SGLang, Qwen3.8 hibrit modelde 3 bin token'lık ortak öneki farklı kuyrukla cache'lemiyor (paket 0 ölçümü); D12 ve önek düzeni için vLLM daha uygun. SGLang kalite koşusu recall 0,38. | `config/runtime.yaml` `engine: vllm` |
| D2 | Qwen3.8-27B (geçici) | check_recall: Qwen 0,48 / 0,42, gpt-oss-120b 0,43, Gemma 4 31B 0,40. Hepsi katman 1 eşiklerini geçti. Qwen ile gpt-oss arasındaki fark tekrar gürültüsünden küçük; karar kuralına göre eşitlikte hızlı olan öne geçer ve gpt-oss 1,9 kat hızlı (40,7 sn ve 75 sn). Öte yandan "ölçülebilir fark yoksa basit olan kalır" kuralı ve D3–D5'in Qwen üzerinde ölçülmüş olması Qwen'den yana. İlk iki aday (Qwen, gpt-oss) uzman karşılaştırmasına (karar kuralı adım 3) gider. | `config/runtime.yaml` `model: qwen3.8-27b` |
| D3 | Düşünme kapalı, sıcaklık 0 | Düşünme açık 4,8 kat yavaş (297 sn ve 62 sn), recall artmadı (0,43). Sıcaklık 0 / 0,3 / 0,7 arasında ölçülebilir fark yok; daha kararlı olan seçildi. | `config/pipeline.yaml` `generation.thinking: false`, `temperature: 0.0` |
| D4 | FP8 | BF16 ile recall aynı (0,44 ve 0,45 ort.); FP8 32 istekte 828 token/sn, BF16 471. 4 bit: resmî 4 bit depo yok; BF16'dan çalışma anında MXFP4 (`--quantization mxfp4 --linear-backend marlin`) bu modelde yüklenemedi, konteyner yeniden başlama döngüsüne girdi. | `config/models.yaml` `qwen3.8-27b` (FP8) |
| D5 | 64 dizi, 32 bin bağlam | Dizi sınırı 32'de 64 istek kuyruğa giriyor (ilk token 35,8 sn); 16'da 64 istekte 3 hata (bağlantı koptu, ReadError; kuyruktaki istekler ilk token için 94–107 sn bekledi, Runpod vekilinin ~100 sn zaman aşımıyla uyumlu). 64 dizide 64 istek 1.183 token/sn, ilk token 1,2 sn. 64 dizi 32 istekte 448 token/sn ölçtü; bu, yeniden başlatmadan hemen sonraki ilk basamak ve ısınma etkisi olabilir, tekrar ölçülmeli. 16 bin bağlam 32 isteği 757 token/sn ile karşıladı (32 bin: 828): fayda yok. | `config/models.yaml` `max_num_seqs: 64` |
| D12 | Bekletmemek | Önek isabeti iki durumda da %54; bekletmeden süre biraz kısa (70 sn ve 76 sn), recall farkı gürültü içinde (0,47 ve 0,45). Daha basit olan seçildi. | `config/pipeline.yaml` `prefix_warmup: false` |

## Katman 2 ek ölçütleri (ilk koşular)

Sınır ve hata durumlarının kapsanma oranı (`boundary_ok_rate`) düşük: d2-qwen'de 0,19. Gereksinim başına uydurma içerik 1,0–1,2. Belirsizliğin varsayım olarak yazılma oranı 0,46. Bunlar prompt ve örnek havuzu işinin (paket 3, D9–D10) başlangıç noktası.
