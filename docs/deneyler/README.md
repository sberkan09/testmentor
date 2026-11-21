# Deney raporları (paket 1)

19 Kasım 2026. Tablolar `python -m eval.summarize` ile `results/` altındaki koşulardan üretilir (`D1.md` … `D12.md`). Bu dosya kararları ve uyarıları özetler; sonuçlar `docs/tasarim.md` Deney planı tablosunun Sonuç sütununa da işlendi.

## Uyarılar

- **D0 koşulmadı.** Test mühendisi yok. Katman 2 puanları (Claude Sonnet 5.5 hakem, rubrik r1) uzman puanıyla doğrulanmadı. Hakem ve referans aynı model ailesinden olduğu için Claude'a benzeyen çıktılar kayırılmış olabilir.
- **Altın set sentetik (v0.1) ve küçük.** 40 gereksinim, 141 referans denetim. Sıcaklık 0,7 iken aynı ayarla iki koşu arasında `check_recall` 0,06 oynadı; sıcaklık 0 ile Qwen'in üç tekrarı 0,03 aralığında kaldı, gpt-oss'unki 0,10. Bundan küçük farklar karar için yeterli değil.
- **Tekrarlanabilirlik.** Aynı ayarla iki koşu katman 1'de birebir aynı çıkmıyor: sıcaklık 0'daki sınıflandırmada bile yöntem doğruluğu 0,725 ile 0,775 arasında, test sayısı 60 ile 70 arasında değişti. Kapsama, ihlal, adım yapısı ve şema iki koşuda da aynı (1,0 / 0 / 1,0 / 1,0). Farklar ilgili raporun "Tekrarlanabilirlik" bölümünde.
- **Ölçüm yöntemi.** Test üretimi referans öbek ve referans yöntemlerle beslendi (`generation_inputs: reference`; bkz. tasarım, Deney planı kuralları). Yöntem doğruluğu ve öbekleme uyumu ayrı ölçüldü.
- **Hız ölçümleri Runpod HTTP vekili üzerinden.** İlk token sürelerine vekilin gidiş-dönüşü dahil.
- `d1-vllm` kalite satırı şablon t1 ve uçtan uca girdiyle koşuldu; diğer kalite koşuları t2 ve referans girdiyle. D1'in kararı yük ölçümüne dayanır.

## Kararlar

| No | Karar | Gerekçe | Ayar |
| --- | --- | --- | --- |
| D1 | vLLM | 32 eşzamanlı istekte 777 token/sn (SGLang 698); ikisinde de hata 0, şema %100. SGLang, Qwen3.8 hibrit modelde 3 bin token'lık ortak öneki farklı kuyrukla cache'lemiyor (paket 0 ölçümü); D12 ve önek düzeni için vLLM daha uygun. SGLang kalite koşusu recall 0,38. | `config/runtime.yaml` `engine: vllm` |
| D2 | Qwen3.8-27B (uzman karşılaştırmasına kadar) | 20 Kasım tekrar koşusu, güncel ayarlarla (sıcaklık 0) 3'er tekrar: check_recall Qwen 0,454 / 0,468 / 0,440 (ort. 0,454), gpt-oss 0,461 / 0,362 / 0,426 (ort. 0,416). Qwen ortalamada yüksek ve kararlı; gpt-oss'un dağılımı geniş. gpt-oss gereksinim başına iki kat uydurma içerik yazıyor (2,3 ve 1,0), daha çok test (83 ve 62) ve daha iyi sınır kapsaması (0,16 ve 0,08) üretiyor. Hız: gpt-oss kalite koşusunda 1,8 kat (35 ve 63 sn), ~12 bin token'lık uzun prompt'ta 16 istekte 708 ve 392 token/sn; ilk token ikisinde ~1,1 sn. Fark gpt-oss'un kendi dağılımı içinde kaldığı için kesin değil; ilk iki aday uzman karşılaştırmasına (karar kuralı adım 3) gider. Gemma 4 31B 0,40 ile elendi. | `config/runtime.yaml` `model: qwen3.8-27b` |
| D3 | Düşünme kapalı, sıcaklık 0 | Düşünme açık 4,8 kat yavaş (297 sn ve 62 sn), recall artmadı (0,43). Sıcaklık 0 / 0,3 / 0,7 arasında ölçülebilir fark yok; daha kararlı olan seçildi. | `config/pipeline.yaml` `generation.thinking: false`, `temperature: 0.0` |
| D4 | FP8 | BF16 ile recall aynı (0,44 ve 0,45 ort.); FP8 32 istekte 828 token/sn, BF16 471. 4 bit: resmî 4 bit depo yok; BF16'dan çalışma anında MXFP4 (`--quantization mxfp4 --linear-backend marlin`) bu modelde yüklenemedi, konteyner yeniden başlama döngüsüne girdi. | `config/models.yaml` `qwen3.8-27b` (FP8) |
| D5 | 64 dizi, 32 bin bağlam | 64 eşzamanlı istekte: 64 dizi 1.205 token/sn ve ilk token 0,96 sn; 32 dizi 873 token/sn ve ilk token 36 sn (kuyruk); 16 dizi 3 hata (~100 sn bekleyen bağlantılar koptu). Yeniden başlatmadan sonraki ilk yük basamağı her iki koşuda da yarı hızda ölçüldü (soğuk CUDA grafikleri); 32 istekteki karşılaştırma bu yüzden güvenilir değil, yük ölçümüne sayılmayan ısınma turu eklendi. 16 bin bağlamın hız faydası yok. | `config/models.yaml` `max_num_seqs: 64` |
| D12 | Bekletmemek | Önek isabeti iki durumda da %54; bekletmeden süre biraz kısa (70 sn ve 76 sn), recall farkı gürültü içinde (0,47 ve 0,45). Daha basit olan seçildi. | `config/pipeline.yaml` `prefix_warmup: false` |

## Katman 2 ek ölçütleri (ilk koşular)

Sınır ve hata durumlarının kapsanma oranı (`boundary_ok_rate`) düşük: d2-qwen'de 0,19. Gereksinim başına uydurma içerik 1,0–1,2. Belirsizliğin varsayım olarak yazılma oranı 0,46. Bunlar prompt ve örnek havuzu işinin (paket 3, D9–D10) başlangıç noktası.

## Bilgi havuzu ve uzun bağlam (20 Kasım notu)

Stüdyoda projelere tasarım dokümanları, standartlar ve proje yönetim planı gibi belgeler eklenecek; test üretimi bunlardan getirilen parçalarla yapılacak. Bu yüzden istek başına ~12 bin token getirilmiş parça ile yük ölçüldü (`d2-long-*`, parçalar sentetik, öbek başına farklı). İkisi de hatasız: Qwen 16 istekte 392 token/sn, gpt-oss 708; ilk token medyanı ~1,1–1,2 sn. KV kapasitesi 32 bin bağlamda Qwen'de 605 bin token (18,5 eşzamanlı dizi), gpt-oss'ta 254 bin (7,8). Parça boyu, parça sayısı, reranker ve proje kartının kaliteye etkisi D9'un konusu; gerçek belge setiyle ölçülecek.

## D9 pilotu (paket 1b)

Altın set v1 (ERTMS 109, kamu dijital hizmeti 120 gereksinim; 519 resmî kökenli ya da Claude denetimi) üzerinde Qwen3.8-27B ile parçasız ve altın parçalı (kâhin getirme) üretim. Belge gerektiren denetimlerde recall 0,280 → 0,488 (+0,21, %95 aralık [+0,13, +0,28]); belge gerektirmeyenlerde 0,530 → 0,556 (aralık sıfırı içeriyor). Set, D9'u ölçebiliyor. Kâhin parçalarla bile belge gerektiren denetimlerin yarısı karşılanmıyor; uydurma içerik 1,27 → 1,53. Ayrıntı: [D9.md](D9.md).


## Paket 3 kararları (20 Kasım 2026)

| No | Karar | Gerekçe | Ayar |
| --- | --- | --- | --- |
| D6 | BGE-M3, agglomerative average, eşik 0,35 (değişmedi) | Alternatif embedding'ler geçmedi; HDBSCAN ağaç tutmuyor. Eşik 0,30 v1'de iyi ama bootstrap aralığı sıfırı geçmiyor, v0'da kötü: aday. [D6](D6.md) | değişiklik yok |
| D7 | Öbek başına kalır (kullanıcı kararı, 21 Kasım) | Gereksinim başına çağrı recall +0,069 [+0,028, +0,110] (`d7-cluster`'a göre), +0,046 [+0,012, +0,082] (`p3-v1-reference`'a göre) ama artış test sayısından geliyor (test sayısı aynı olan gereksinimlerde +0,011); uydurma %48, token %55 fazla; paketleme iki tabana göre de kötü. [D7](D7.md) | değişiklik yok |
| D8 | Ekleme artımlı; çıkarma budama; birleştirme prompt'u | Artımlı düzeltmeleri ve önceki testleri koruyor, 4 kat ucuz; çıkarmada çağrı ile budama aynı set; birleştirme prompt'u 100 kat ucuz, recall farkı yok. [D8](D8.md) | `config/pipeline.yaml` `generation.prune_removals: true` |

Uyarı: KDH-030 sınır testinde model uzun bir girdi dizisini bitirmeden yazıyor (5 koşunun 3'ünde `max_tokens`'ta kesildi). Açık bulgu; paket 3 planı.
