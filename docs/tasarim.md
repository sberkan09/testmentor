# Gereksinim-test stüdyosu: teknik tasarım

Sürüm tarihi: 19 Kasım 2026 · Sahibi: Sami Berkan Akkaya

Bu dosya, tasarım dokümanının depo kopyasıdır. Canlı sürüm: [tasarım dokümanı](https://claude.ai/artifact/HCsRJ2NvdydgwWeUUyDFYm). Şemalar: [whiteboard](https://claude.ai/artifact/7eG12wzy6pSfg56gjpBmwQ). Altın set: [`eval/golden/altin-set-v0.json`](../eval/golden/altin-set-v0.json) ve [tablo hali](https://claude.ai/artifact/PiN7tF6if6FRVaJVgqy6FP).

## Özet

Her çıktı (öbek, test durumu, matris satırı) girdilerinin hash'iyle adreslenir; bir düzenleme yalnızca ona bağlı çıktıları yeniden ürettirir. Aynı bağımlılık grafiği hem cache'in yapısıdır hem de arayüzde çizilen şeydir.

Temel kararlar:

1. Eski Gradio uygulaması taşınmaz, sistem sıfırdan kurulur. Eski koddan yalnızca prompt'lar ve alan bilgisi alınır.
2. Öbekleme embedding ve kümeleme ile yapılır. Model yalnızca öbeğe ad ve kısa gerekçe yazar.
3. Test durumları öbek başına paralel üretilir ve JSON şemasına bağlı çıktı verir.
4. Doğrulama yöntemi gereksinim başına ayrı sınıflandırılır, öbek düzenlemelerinden etkilenmez.
5. Matris model çağrısı olmadan, test durumlarının kapsadığı gereksinim kimliklerinden türetilir.
6. Sunum motoru, model ve ayarlar baştan sabit karar değildir; hepsi deney planındaki ölçümlerle seçilir. Ölçüm bitene kadar çalışma varsayımı vLLM ve Qwen3.8-27B'dir.
7. Sunucu FastAPI ve Postgres, ön yüz React ve three.js, aralarındaki iletişim WebSocket olay akışıdır.
8. Kullanıcının elle düzelttiği çıktı sabitlenir ve yeniden üretimde ezilmez.

## Kapsam ve varsayımlar

İlk sürüm, gereksinim setinden matrise giden pipeline'ı, stüdyo arayüzünü ve proje bilgi havuzunu tek GPU'lu yerel sunucuda çalıştırır.

Kapsam dışı: gereksinim yönetim araçlarıyla entegrasyon ve model ince ayarı. Test durumu şablonunun ayrıntısı ve sonradan eklenecek modüller sonraki sürümlerin konusudur.

Varsayımlar ve teyit edilenler:

- Donanım tek RTX PRO 6000 96 GB'tir, bulut kullanılmaz ve veri sunucudan çıkmaz.
- Sunucu yalnızca bu uygulamaya ayrılmıştır (teyit edildi). İleride eklenecek modüller için aşamalar eklenti olarak tasarlanır.
- Gereksinimler Türkçe ya da İngilizce olabilir (teyit edildi). Modeller ve embedding çok dilli seçilir, altın set iki dili de içerir.
- Set büyüklüğü ve biçimi projeden projeye değişir (teyit edildi). İçe alma, kolon eşleme adımıyla esnek tutulur; tasarım 2.000 gereksinime kadar ölçeklenir.
- Kullanıcı sayısı belirsizdir; aynı projede aynı anda birden çok kullanıcı çalışabilmelidir (teyit edildi).
- Test durumu şablonu kurumda sabittir, alanları sonra netleşecektir. Şema bu yüzden koddan değil ayar dosyasından okunur.
- Doğrulama yöntemleri proje bazında değişebilir ve proje belgelerinde tanımlıdır; bir gereksinime birden çok yöntem atanabilir (teyit edildi). Varsayılan liste Test, Analiz, İnceleme, Gösterim'dir.
- Kodu Opus ve Sonnet modelleri yazar; bu doküman onların ana bağlamıdır.

## Veri modeli

Sistemdeki her şey Postgres'te tutulan bir çıktı düğümüdür ve hangi girdilere bağlı olduğunu bilir.

| Düğüm | İçerik | Bağlı olduğu girdiler | Üreten |
| --- | --- | --- | --- |
| Gereksinim | kimlik, metin, kaynak belge | yüklenen set | ayrıştırıcı |
| Embedding | vektör | gereksinim metni, embedding modeli sürümü | embedding modeli |
| Öbekleme | gereksinim → öbek ataması | tüm embedding'ler, kümeleme parametreleri, kullanıcı atamaları | algoritma |
| Öbek | ad, gerekçe, üye listesi | üye gereksinimlerin kimlik ve metinleri | model (yalnızca ad) |
| Test durumu seti | öbeğin test durumları, her biri kapsadığı gereksinim kimlikleriyle | öbek üyeleri, bilgi havuzu parçaları, proje kartı | model |
| Doğrulama yöntemi | bir ya da birden çok yöntem ve bir cümle gerekçe | gereksinim metni, proje kartı | model |
| Matris satırı | gereksinim, yöntem, test durumu kimlikleri, kapsama durumu | doğrulama yöntemi, test durumu setleri | SQL birleştirmesi |

Her düğümde ortak alanlar bulunur: `input_hash`, `status` (`fresh`, `stale`, `running`, `failed`), `pinned`, `origin` (`generated`, `edited`), `version`, `produced_by` (model ve prompt sürümü).

Kurallar:

- `input_hash`, sıralı girdi içeriklerinin, prompt sürümünün, model kimliğinin ve üretim parametrelerinin SHA-256 özetidir.
- Öbek hash'i üyelerin kimlik ve metinlerine bağlıdır, öbeğin adına ya da ekrandaki konumuna değil. Ad değiştirmek testleri bayatlatmaz.
- Kullanıcı düzenlemesi yeni bir sürüm yazar (`origin=edited`, `pinned=true`). Eski sürümler silinmez, geri alma sürüm değiştirmektir.
- Her düzenleme olay günlüğüne yazılır (`requirement_moved`, `cluster_created`, `test_case_edited`). Arayüz bu olayları dinler, denetim izi de buradan çıkar.

## Pipeline aşamaları

Dört aşamanın yalnızca ikisi büyük modeli çağırır: test durumu üretimi ve doğrulama yöntemi.

### 1. İçe alma

Yüklenen set gereksinim kayıtlarına ayrıştırılır. Kimliği olmayan gereksinime sistem kimlik verir. Embedding'ler bu aşamada toplu hesaplanır.

### 2. Öbekleme

- Kosinüs uzaklığıyla hiyerarşik (agglomerative) kümeleme yapılır ve ağaç saklanır.
- Arayüzdeki ayrıntı kaydırıcısı ağacı farklı seviyeden keser. Öbek sayısı model çağrısı olmadan anında değişir.
- Kullanıcının taşıdığı gereksinim sabit atama olur. Yeniden kümeleme sabit atamaları bozmaz.
- Model her öbek için 3–6 kelimelik ad ve bir cümle gerekçe yazar. Kullanıcının elle yazdığı ad sabittir.

### 3. Test durumu üretimi

- Birim öbektir: bir çağrı, öbeğin gereksinimlerini, proje kartını ve bilgi havuzundan gelen parçaları alır.
- Çıktı şeması: `test_cases[]`, her biri `id`, `title`, `covers[req_id]`, `steps[{no, action, expected}]`, `type` (normal, sınır, hata), `priority` ve duruma göre doldurulan `preconditions`, `test_inputs`, `assumptions`.
- Her adımın kendi beklenen sonucu vardır; test geneli için tek bir beklenen sonuç yazılmaz.
- Ön koşul, test girdisi ve varsayım alanları gerekmediğinde boş bırakılır; model bunları doldurmak için içerik uydurmaz. Gereksinimin tanımlamadığı bir değer seçildiyse bu, varsayım olarak yazılır.
- Sunucu her gereksinimin en az bir `covers` listesinde geçtiğini doğrular. Eksik kalanlar için yalnızca onları isteyen ek çağrı yapılır.
- 25'ten fazla gereksinimli öbek alt parçalara bölünerek üretilir.
- Öbeğe gereksinim eklenince set baştan yazılmaz. Artımlı prompt mevcut test durumlarını ve yeni gereksinimi alır, yalnızca ekleme ya da güncelleme döner.
- Sabitlenmiş test durumları prompt'a değiştirilemez olarak verilir.

### 4. Doğrulama yöntemi

- Gereksinimler 20–30'luk gruplar halinde tek çağrıda sınıflandırılır. Çıktı, projenin yöntem listesinden seçilen bir ya da birden çok değerdir. Liste ve ölçütler proje belgelerinden çıkarılıp proje kartında tutulur; varsayılan Test, Analiz, İnceleme, Gösterim'dir.
- Sonuç gereksinim metni değişmedikçe geçerlidir, öbek düzenlemeleri onu bayatlatmaz.

### 5. Matris

- Matris bir veritabanı görünümüdür: gereksinim, öbek, doğrulama yöntemi, test durumları, kapsama durumu.
- İki tutarlılık uyarısı üretilir: yöntemi Test olup kapsayan testi olmayan gereksinim, ve yöntemi Test olmayıp test yazılmış gereksinim.
- Dışa aktarım xlsx'tir.

### Aşama kapıları

Her aşama otomatik ya da onaylı modda çalışır. Onaylı modda alt aşamanın işleri kullanıcı devam deyince kuyruğa girer. Otomatik modda hemen başlar; kullanıcı araya düzenleme sokarsa etkilenen işler iptal edilip yeniden kuyruğa alınır.

## Model ve sunum katmanı

Sunum motoru, model ve ayarların hiçbiri baştan sabit değildir; hepsi deney planıyla, kendi gereksinimlerinizden kurulan altın set üzerinde ölçülerek seçilir. Ölçüm bitene kadar çalışma varsayımı vLLM ve Qwen3.8-27B'dir.

### Önce teşhis: Gemma 4 neden yetersiz kaldı

Yetersizliğin bir kısmı modelden değil kurulumdan geliyor olabilir. Hangisi olduğu varsayılmaz; D0 deneyinde şu iki değişken ölçülür:

- **Hangi boyut çalışıyor.** Gemma 4 ailesi E2B'den 31B'ye uzanıyor ([model kartı](https://ai.google.dev/gemma/docs/core/model_card_4)). `ollama list` küçük bir varyant gösteriyorsa şikâyetin kaynağı büyük ölçüde budur.
- **Bağlam penceresi.** Ollama'nın varsayılan bağlamı küçüktür ve aşan prompt'u hata vermeden keser ([açıklama](https://particula.tech/blog/ollama-num-ctx-silent-prompt-truncation)). Bir öbeğin gereksinimleri ve bilgi havuzu parçaları bu sınırı kolayca aşar; model prompt'un bir kısmını hiç görmemiş olabilir.

### Sunum motoru adayları

- vLLM aynı anda gelen istekleri tek batch'te işler, ortak prompt önekini bir kez hesaplar ([prefix caching](https://www.mintlify.com/vllm-project/vllm/features/prefix-caching)) ve çıktıyı JSON şemasına zorlar ([structured outputs](https://docs.vllm.ai/features/structured_outputs.html)).
- Ocak 2026 tarihli bir kıyaslamada, RTX PRO 6000 Blackwell üzerinde Llama 3.1 8B ile vLLM en yüksek 8.033 token/sn, SGLang 6.395, Ollama 484 verdi; Ollama 128 eşzamanlı istekte çöktü ([kaynak](https://joshua8.ai/llm-inference-benchmark/)).
- Aynı kartta Gemma 4 31B (FP8, vLLM 0.20) ortalama 823 token/sn toplam, 380 token/sn çıktı verdi; ortalama 13,7 istek aynı anda işlendi, ilk token medyanı 0,73 sn ([kaynak](https://huggingface.co/blog/hexgridcloud/gemma-4-31b-vllm-on-rtx-6000-pro)).
- SGLang ve doğru ayarlanmış Ollama aynı altın sette vLLM ile karşılaştırılır (D1).
- Uygulama modele yalnızca OpenAI uyumlu API üzerinden, tek bir `LLMClient` arayüzüyle erişir. Motor ya da model değiştirmek ayar değişikliğidir.
- Başlangıç ayarları: FP8 ağırlıklar, prefix caching açık, 16–32 eşzamanlı dizi, 16–32 bin token bağlam, GPU belleğinin %80'i. Kesin değerler ölçümle belirlenir.

### Model adayları

| Model | Yapı | Lisans | 96 GB'ta durum | Neden aday |
| --- | --- | --- | --- | --- |
| [Qwen3.8-27B](https://github.com/QwenLM/Qwen3.8) | 27B yoğun | Apache 2.0 | 8 bitte yaklaşık 29 GB, kalanı eşzamanlılığa kalır | Ağustos 2026 çıkışlı, tek GPU için en sık önerilen model; 201 dil ve lehçe desteği beyan ediyor |
| [Gemma 4 31B](https://ai.google.dev/gemma/docs/core/model_card_4) | 31B yoğun | Apache 2.0 | FP8 ile bu kartta ölçülmüş | Mevcut modelin doğru kurulumla taban çizgisi |
| gpt-oss-120b | 120B MoE | Apache 2.0 | 4 bitte yaklaşık 61 GB, eşzamanlılık payı daralır | Büyük modelin kalite farkı var mı sorusunun cevabı |

Bu üçlü, tek GPU'lu kurumsal sunucu için yayımlanmış bir [kısa listeyle](https://sysart.consulting/insights/best-open-weight-llms-2026/) örtüşüyor. Boyut rakamları [buradan](https://www.modemguides.com/blogs/ai-infrastructure/best-local-ai-models-by-vram) ve [buradan](https://www.databasemart.com/blog/vllm-gpu-benchmark-pro6000). Yayımlanmış kıyaslamaların çoğu kodlama odaklıdır ve Türkçe test durumu yazma kalitesi hakkında bir şey söylemez.

### Seçim yöntemi: altın set

Altın set, doğru cevabı önceden bilinen küçük bir sınav kâğıdıdır: 30–50 gereksinim ve bunlar için bir test mühendisinin yazdığı ya da onayladığı test durumları ile doğrulama yöntemleri. Her model, prompt ve ayar aynı kâğıtla sınanır; böylece "daha iyi oldu mu" sorusu izlenimle değil sayıyla cevaplanır.

İlk sürüm depodadır: [`eval/golden/altin-set-v0.json`](../eval/golden/altin-set-v0.json). Beş sentetik proje (kamu, komuta kontrol, yapay zekâ, savunma-sağlık, yazılım teknolojileri), 40 gereksinim (20 Türkçe, 20 İngilizce), 15 referans öbek ve 49 referans test durumu (135 adım, her adımın kendi beklenen sonucuyla) içerir. Gereksinimleri ve referans cevapları Claude yazdı; set kurumun gerçek projelerini ve test şablonunu yansıtmaz. Bir test mühendisi gözden geçirmeli, gerçek projelerden örnek eklendikçe set v1'e yükseltilmelidir.

- Set Türkçe ve İngilizce gereksinimleri, kolay ve zor örnekleri birlikte içerir.
- Ölçülenler: şema geçerliliği, kapsama (her gereksinim bir `covers` listesinde), doğrulama yöntemi doğruluğu, uzmanın kör karşılaştırmada verdiği 1–5 puan, öbek başına süre, 16 eşzamanlı istekte token/sn.
- Qwen3.8-27B'de düşünme modu varsayılan olarak açıktır ve istek başına kapatılabilir ([haber](https://www.eweek.com/news/alibaba-qwen3-8-27b-license-apac-china/)). Sınıflandırmada kapalı, test üretiminde iki hali de ölçülür.
- Altın set kalıcıdır: her prompt ve model değişikliği aynı setle yeniden ölçülür.

### Embedding modeli

Varsayılan BGE-M3'tür: çok dillidir, tek modelden hem yoğun hem seyrek vektör verir ve Türkçe embedding kıyaslamalarında taban model olarak kullanılır ([örnek](https://arxiv.org/pdf/2601.16018)). Ayrı küçük bir servis olarak aynı GPU'da çalışır ve 3–5 GB yer tutar. Model sürümü embedding'in hash'ine girer.

## Deney planı

Aşağıdaki kararların hiçbiri tahminle verilmez; her biri altın set üzerinde denenir ve kazanan seçilir. Son sütun, ölçüm gelene kadar geliştirmenin dayandığı varsayımdır.

| No | Soru | Denenenler | Ölçüt | Çalışma varsayımı |
| --- | --- | --- | --- | --- |
| D0 | Gemma 4 şikâyeti modelden mi kurulumdan mı | mevcut kurulum olduğu gibi; aynı model tam bağlamla; Gemma 4 31B | altın set puanı | bilinmiyor |
| D1 | Sunum motoru | vLLM, SGLang, doğru ayarlı Ollama | 1, 8, 16 ve 32 eşzamanlı istekte token/sn, ilk token süresi, hata oranı, şema geçerliliği | vLLM |
| D2 | Model | Qwen3.8-27B, Gemma 4 31B, gpt-oss-120b | uzman puanı, kapsama, yöntem doğruluğu; Türkçe ve İngilizce ayrı raporlanır | Qwen3.8-27B |
| D3 | Düşünme modu ve örnekleme | düşünme açık ve kapalı; sıcaklık 0 ile 0,7 arası | kalite farkı ve süre | sınıflandırmada kapalı |
| D4 | Ağırlık hassasiyeti | 16 bit, FP8, 4 bit | kalite kaybı ve eşzamanlılık kazancı | FP8 |
| D5 | Eşzamanlılık ve bağlam | dizi sınırı 8 ile 64 arası; bağlam 8, 16, 32 bin token | toplam token/sn ve öncelikli işin ilk token süresi | 16–32 dizi |
| D6 | Embedding ve kümeleme | BGE-M3 ve iki alternatif; agglomerative ve HDBSCAN | uzmanın elle öbeklemesiyle uyum, kullanıcının yapmak zorunda kaldığı taşıma sayısı | BGE-M3, agglomerative |
| D7 | Üretim birimi | öbek başına tek çağrı ve gereksinim başına çağrı; öbek sınırı 10, 25, 50 | kalite, tekrar eden test oranı, süre | öbek başına, sınır 25 |
| D8 | Yeniden üretim biçimi | artımlı ve baştan | tutarlılık, kullanıcı düzeltmelerinin korunması, süre | artımlı |
| D9 | Bilgi havuzu | parça boyu 300, 500, 800 token; ilk 4, 8, 12 parça; reranker var ve yok; proje kartı var ve yok | altın set puanı | 300–500 token, ilk 6–8, reranker yok |
| D10 | Örnek havuzu | 0, 2, 4 örnek | uzman puanı ve üslup uyumu | 2–3 örnek |
| D11 | Kuyruk ayarları | bekleme 0,5, 1,5, 3 sn; otomatik işlerin yuva payı | boşa giden çağrı oranı ve algılanan gecikme | 1,5 sn, %70 |

Kurallar:

- Her deney `eval/` koşucusunda tek komutla tekrar edilebilir ve sonucu bu tabloya Sonuç sütunu olarak işlenir.
- Bir deneyde tek değişken değişir; diğerleri çalışma varsayımında kalır.
- Ölçülebilir fark yoksa daha basit olan seçenek kalır.
- Sıra: D0, D1, D2, sonra D3–D5. D6–D10 ilgili aşama yazıldığında, D11 arayüz kullanılır hale geldiğinde koşulur.
- Kod, çalışma varsayımlarını ayar dosyasından okur; deney sonucu bir satırlık değişiklikle uygulanır.

## Cache, geçersiz kılma ve iş kuyruğu

Bir düzenlemenin maliyeti, bayatlattığı düğüm sayısı kadardır; çoğu düzenleme sıfır ile iki model çağrısı arasında kalır.

### Üç cache katmanı

| Katman | Ne saklar | Anahtar | Nerede |
| --- | --- | --- | --- |
| Çıktı cache'i | üretilmiş düğüm içerikleri | `input_hash` | Postgres |
| Prefix cache | prompt önekinin model içi durumu | ortak önek token'ları | vLLM, GPU belleği |
| Arama cache'i | öbek için getirilen bilgi parçaları | öbek hash'i ve indeks sürümü | Postgres |

### Prompt düzeni

Prefix cache'in işlemesi için her prompt en kararlı parçadan en değişkene doğru dizilir:

1. Sistem talimatı (tüm projelerde aynı)
2. Proje kartı (proje başına sabit)
3. Çıktı şeması ve örnekler (aşama başına sabit)
4. Getirilen bilgi parçaları (öbek başına)
5. Gereksinimler (öbek başına)

Aynı projenin tüm istekleri ilk üç parçayı paylaşır. İlk üç parçaya tarih, sayaç ya da kullanıcı adı gibi değişken hiçbir şey yazılmaz.

### Hangi düzenleme neyi bayatlatır

| Olay | Bayatlayan | Model çağrısı |
| --- | --- | --- |
| Gereksinim A öbeğinden B'ye taşındı | A ve B'nin test setleri ve adları | 2 artımlı test çağrısı, 2 ad çağrısı |
| Öbek yeniden adlandırıldı | hiçbir şey | 0 |
| Öbek silindi, üyeleri dağıtıldı | üye alan öbeklerin setleri | üye alan öbek başına 1 |
| İki öbek birleştirildi | yeni öbeğin seti | 1: iki set birleştirilir, model yalnızca tekrarları ayıklar |
| Gereksinim metni değişti | embedding, doğrulama yöntemi, öbeğinin test seti | 2 |
| Test durumu elle düzenlendi | yalnızca matris satırı | 0 |
| Bilgi havuzuna belge eklendi | getirilen parçaları değişen öbeklerin setleri | değişen öbek başına 1 |
| Prompt ya da model sürümü değişti | o aşamanın tüm çıktıları, kullanıcı onayıyla | toplu, arka planda |

İki ayrıntı önemlidir. Test setinin hash'ine indeks sürümü değil, getirilen parçaların kimlikleri girer; belge eklemek, arama sonucu değişmeyen öbekleri bayatlatmaz. Bayatlayan sabitlenmiş düğüm kendiliğinden yeniden üretilmez, kullanıcıya uyarı olarak gösterilir.

### İş kuyruğu

- Üç öncelik sınıfı vardır: P0 kullanıcının seçili ya da ekranda görünen öğesi, P1 kullanıcının tetiklediği diğer işler, P2 otomatik ilerleme.
- Düzenlemeden sonra 1,5 saniye beklenir; art arda gelen sürüklemeler tek işe indirgenir.
- Aynı düğüm için bekleyen iş varsa yenisi onun yerine geçer. Çalışan işin girdisi değiştiyse akış kesilerek iptal edilir.
- Eşzamanlılık sınırı vLLM'in dizi sınırına eşittir; P2 işleri yuvaların en çok %70'ini kullanır.
- Şema doğrulaması başarısız olursa bir kez yeniden denenir, sonra düğüm `failed` olur.
- İlk sürümde kuyruk, iş kayıtları Postgres'te duran bir asyncio işçi havuzudur. Tek GPU için Redis ya da Celery gerekmez.

### Beklenen süreler (tahmin, ölçülecek)

200 gereksinim ve 20 öbek için ilk üretim yaklaşık 20 test çağrısı, 8 doğrulama çağrısı ve 20 ad çağrısıdır. Çağrı başına 1.200 çıktı token'ı ve yukarıdaki 380 token/sn ölçümüyle test üretimi 1–2 dakika sürer. Tek bir taşıma, sonucu birkaç saniyede akmaya başlayan iki artımlı çağrıdır.

## Proje bilgi havuzu

Her projenin bilgisi iki katmanda tutulur: her prompt'a giren kısa bir proje kartı ve yalnızca gerektiğinde aranan bir indeks.

### Proje kartı

- En çok 1.500 token: sistemin tanımı, sözlük ve kısaltmalar, test yazım kuralları, doğrulama yöntemi listesi ve ölçütleri.
- İlk taslağı model yüklenen belgelerden çıkarır, kullanıcı düzenler ve onaylar.
- Kart her prompt'un önekinde durduğu için prefix cache'ten yararlanır.
- Kart değişirse projedeki tüm model çıktıları bayatlar. Bu yüzden kısa ve kararlı tutulur, değişiklikte kullanıcı uyarılır.

### İndeks

- Belgeler başlık yolu korunarak 300–500 token'lık parçalara bölünür ve yüklemede bir kez embed edilir.
- Depo Postgres ve pgvector'dür; projeler `project_id` ile ayrılır. Ayrı bir vektör veritabanı kurulmaz.
- Arama hibrittir: yoğun vektör ve anahtar kelime sonuçları sıra birleştirmeyle (RRF) tek listeye iner, ilk 6–8 parça alınır.
- Arama birimi öbektir. Sorgu, öbek adı ile üye gereksinimlerin metnidir; gereksinim başına değil öbek başına bir arama yapılır.
- Yeniden sıralayıcı (reranker) ilk sürümde yoktur; altın set ölçümü gerektirirse eklenir.

### Örnek havuzu

Kullanıcının onayladığı ya da düzelttiği test durumları projeye özel örnek havuzuna yazılır. Yeni bir öbek için en benzer 2–3 örnek prompt'a eklenir. Sistem böylece ince ayar yapılmadan projenin üslubunu öğrenir.

### Yalıtım

Her sorgu `project_id` filtresi taşır. Bir projenin parçasının başka projenin prompt'una girmediği otomatik testle doğrulanır.

## Sunucu mimarisi ve API

Durumun tek sahibi sunucudur: ön yüz komut gönderir, sonuçları olay akışından dinler.

### Bileşenler

| Bileşen | Teknoloji | Sorumluluk |
| --- | --- | --- |
| Ön yüz | React, TypeScript, three.js (react-three-fiber) | tuval, paneller, olay dinleme |
| API ve orkestratör | Python, FastAPI, asyncio | komutlar, bağımlılık grafiği, kuyruk, olay yayını |
| Veritabanı | Postgres, pgvector | düğümler, sürümler, olay günlüğü, indeks |
| Model sunucusu | vLLM (çalışma varsayımı) | metin üretimi |
| Embedding servisi | BGE-M3 (çalışma varsayımı) | vektörler |
| Dağıtım | Docker Compose | beş servis, tek sunucu |

### Kod düzeni

- `core/`: grafik, hash, aşamalar ve prompt'lar. HTTP'den ve arayüzden habersiz saf Python'dur, birim testleri model çağırmadan çalışır.
- `services/`: `LLMClient`, embedding ve arama istemcileri.
- `worker/`: iş kuyruğu.
- `api/`: REST ve WebSocket.
- `web/`: React uygulaması.
- `eval/`: altın set ve ölçüm koşucusu.

Aşamalar `core/stages/` altında kayıtlı eklentilerdir: her biri ürettiği düğüm tipini, girdilerini ve üretim fonksiyonunu bildirir. Sonradan eklenecek modüller yeni bir aşama kaydıyla gelir; orkestratör, kuyruk ve arayüzün durum dili değişmez.

### API

Komutlar REST ile gider:

- `POST /projects`, `POST /projects/{id}/requirements:import`, `POST /projects/{id}/kb/documents`
- `POST /projects/{id}/commands`: gövdedeki `type` alanı komutu belirler: `move_requirement`, `create_cluster`, `delete_cluster`, `merge_clusters`, `rename_cluster`, `set_granularity`, `edit_test_case`, `pin`, `unpin`, `set_stage_mode`, `approve_stage`, `regenerate`, `undo`.
- `GET /projects/{id}/snapshot`: projenin tam durumu; ilk yükleme ve yeniden bağlanma için.
- `GET /projects/{id}/matrix.xlsx`

Sonuçlar `WS /projects/{id}/events` üzerinden gelir: `node_created`, `node_updated`, `node_stale`, `job_started`, `job_progress` (token akışı), `job_done`, `job_failed`, `stage_waiting_approval`.

### Kurallar

- Her olay sıra numarası taşır. Yeniden bağlanan istemci son numarayı gönderir, sunucu eksikleri tekrar oynatır ya da snapshot verir.
- Komut tek veritabanı işleminde işlenir: olay günlüğe yazılır, grafik güncellenir, bayatlayanlar işaretlenir, aşama otomatik moddaysa işler kuyruğa girer, olaylar yayınlanır.
- Ön yüz iyimser güncelleme yapar ve olayla teyit eder; çelişkide sunucu kazanır.
- Sekme kapansa da pipeline çalışmaya devam eder.
- İlk sürümde erişim şirket içi ağ, kullanıcı girişi ve proje bazlı yetkiyle sınırlıdır.

### Çok kullanıcılı çalışma

Aynı projede birden çok kullanıcı aynı anda çalışabilir; tutarlılığı sürüm denetimi ve düğüm kilidi sağlar.

- Projeye bağlı tüm istemciler aynı olay akışını dinler. Bir kullanıcının düzenlemesi diğerlerinin ekranına olay olarak düşer.
- Her komut değiştirdiği düğümün `version` değerini taşır. Sürüm eskiyse sunucu komutu reddeder ve güncel durumu döner; son yazan sessizce kazanmaz.
- Metin düzenlenirken düğüm o kullanıcıya kilitlenir ve 60 saniye hareketsizlikte kilit düşer. Taşıma gibi anlık komutlar kilit gerektirmez.
- Olay günlüğü her komutun sahibini tutar. Geri alma kullanıcı başınadır: herkes kendi son komutunu geri alır.
- Aşama onayı ve mod değişikliği proje rolüne bağlıdır.
- Karakter düzeyinde ortak yazım ilk sürümde yoktur; düğüm düzeyinde kilit yeterlidir.

## Stüdyo arayüzü

Arayüz tek bir çalışma alanıdır: ortada canlı tuval, yanlarda paneller, altta pipeline'ı yöneten aşama çubuğu.

### Düzen

- **Üst çubuk:** proje adı ve görünüm seçici.
- **Sol panel:** kaynaklar: gereksinim seti, bilgi havuzu belgeleri, proje kartı.
- **Tuval:** seçili görünüm.
- **Sağ panel (denetçi):** seçili öğenin ayrıntısı, düzenleme alanları, sürüm geçmişi.
- **Aşama çubuğu:** oynat, duraklat, adım; her aşamanın durumu, modu (otomatik ya da onaylı) ve kuyruk ilerlemesi.

### Üç görünüm

| Görünüm | Ne gösterir | Ne yapılır |
| --- | --- | --- |
| Öbek görünümü (2B) | öbekler ada, gereksinimler çip olarak | sürükle bırak taşıma, öbek oluşturma, silme, birleştirme, ayrıntı kaydırıcısı |
| Matris görünümü | gereksinim-test tablosu ve tutarlılık uyarıları | filtre, hücreden düzenleme, dışa aktarım |
| Katman görünümü (3B) | üst üste üç düzlem (öbekler, test durumları, matris) ve aralarındaki izlenebilirlik ipleri | gezinme ve seçim; düzenleme yapılmaz |

Katman görünümünde derinlik pipeline aşamasını gösterir. Yukarı ipi çıkmayan gereksinim test edilmemiş gereksinimdir; bir öğe seçilince kamera ilgili 2B görünüme iner.

### Durum dili

| Durum | Görünüm |
| --- | --- |
| Taze | normal |
| Bayat | soluk, kesikli çerçeve |
| Üretiliyor | metin yerinde akar |
| Sabit | iğne simgesi |
| Hata | kırmızı çerçeve ve yeniden dene düğmesi |
| Kapsanmamış gereksinim | uyarı rozeti |

### Etkileşim kuralları

- Metin her zaman HTML katmanında çizilir, WebGL içinde değil.
- Her düzenleme geri alınabilir; geri alma çoğunlukla cache'ten anında döner.
- Sabitlenmiş öğe bayatladığında fark ekranı açılır: yenisini al, benimkini koru ya da birleştir.
- Taşıma klavyeyle de yapılabilir.
- Büyük projede ayrıntı yakınlaştırma seviyesine bağlıdır: uzaktan öbek adı ve sayılar, yakından tek tek gereksinimler.
- Test durumu denetçide adım adım düzenlenir: her adımın işlemi ve beklenen sonucu ayrı alandır.

Aynı projedeki diğer kullanıcıların seçimi ve düzenlediği öğeler ekranda adlarıyla görünür. Kilitli öğe düzenlenemez, reddedilen komut güncel durumu gösterir.

### Yapım sırası

Önce öbek görünümü, denetçi ve aşama çubuğu; sonra matris görünümü; en son katman görünümü. İlk iki görünüm 3B olmadan da eksiksiz kullanılabilir olmalıdır.

## Geliştirme planı

İş on pakete bölünür; tasarım kararı içeren paketleri Opus, tanımı net uygulama işlerini Sonnet yapar.

| No | Paket | Model | Bitti ölçütü |
| --- | --- | --- | --- |
| 0 | Altyapı: aday sunum motorları, embedding servisi, Postgres, Docker Compose, `LLMClient` | Sonnet | 16 eşzamanlı istek hatasız ve şemaya uygun dönüyor |
| 1 | Altın set ve ölçüm koşucusu | Opus tasarlar, Sonnet yazar | D0–D5 deneyleri koşuldu; motor, model ve ayarlar ölçümle seçildi |
| 2 | Çekirdek: veri modeli, hash, bağımlılık grafiği, geçersiz kılma | Opus | Bayatlama tablosundaki her satırın birim testi geçiyor |
| 3 | Aşamalar ve prompt'lar: öbekleme, test üretimi (artımlı dahil), doğrulama yöntemi | Opus | Altın sette belirlenen eşikler aşılıyor |
| 4 | İçe alma, matris görünümü, xlsx dışa aktarım | Sonnet | Örnek set uçtan uca matrise dönüşüyor |
| 5 | Orkestratör ve kuyruk: komut işleme, öncelik, bekleme, iptal, aşama kapıları | Opus | Taşıma senaryosu iki çağrıyla bitiyor, diğer öbekler cache'ten geliyor |
| 6 | API ve olay akışı: REST komutları, WebSocket, snapshot ve tekrar oynatma | Sonnet | Bağlantı kopup gelince istemci durumu sunucuyla aynı; iki kullanıcının çakışan komutu doğru reddediliyor |
| 7 | Bilgi havuzu: parçalama, indeks, hibrit arama, proje kartı, örnek havuzu | Sonnet; kart çıkarımı ve örnek seçimi Opus | Yalıtım testi geçiyor, altın sette kalite düşmüyor |
| 8 | Ön yüz: öbek görünümü, denetçi, aşama çubuğu, matris görünümü, fark ekranı, geri alma | Sonnet; tuval etkileşimi Opus | Kullanıcı bir seti yükleyip düzenleyerek matrisi dışa aktarabiliyor |
| 9 | Ön yüz: 3B katman görünümü | Opus | 2.000 gereksinimde akıcı gezinme |

Sıra bağımlılığı izler: 0 → 1 → 2 → 3 → 5 → 6 → 8 → 9. Paket 4 ve 7, paket 2 bittikten sonra paralel yürür.

Modellerle çalışma kuralları:

- Her paket ayrı oturumdur. Girdi bu doküman, ilgili bölüm ve önceki paketlerin arayüz dosyalarıdır.
- Önce arayüz ve testler, sonra uygulama. Opus paketin tiplerini ve fonksiyon imzalarını yazar, Sonnet içini doldurur.
- Paket 2 ve 5'in kodu ayrı bir Opus oturumunda incelenir; sistemin doğruluğu bu ikisine bağlıdır.
- Paket 1 bitmeden prompt ayarı yapılmaz. Ölçüm yoksa iyileşme görülemez.
- Tasarımdan sapma gerekiyorsa model önce bu dokümanı günceller, karar burada kayda geçer.

## Riskler ve açık sorular

En büyük risk elle düzenleme ile yeniden üretimin çakışmasıdır; fark ekranı senaryosu paket 5'te ilk prototiplenen şey olmalıdır.

| Risk | Karşı önlem |
| --- | --- |
| Elle düzeltilen çıktı yeniden üretimde kaybolur ya da tutarsız kalır | Sabitleme, sürümleme ve fark ekranı; sabit düğüm kendiliğinden ezilmez |
| Seçilen model test yazımında yine yetersiz kalır | Altın set paket 1'de; yetmezse büyük MoE ya da taslak ve eleştiri olarak iki geçişli üretim |
| Kısa ve kalıp cümleli gereksinimlerde embedding öbekleri iyi ayıramaz | Kullanıcı düzenlemesi birinci sınıf; gerekirse gereksinim metnine bölüm başlığı eklenerek embed edilir |
| Proje kartı değişikliği tüm çıktıları bayatlatır | Kart kısa tutulur, değişiklik onay ister, yeniden üretim arka planda ve isteğe bağlıdır |
| Aynı anda çok proje çalışırsa prefix cache dağılır, tek GPU darboğaz olur | Öncelik kuyruğu; ölçüm eşzamanlı proje sayısıyla tekrarlanır |
| 3B görünüm maliyetine değmez | En sona bırakıldı; ilk iki görünüm ondan bağımsız |
| İki kullanıcı aynı öğeyi aynı anda değiştirir | Sürüm denetimi ve düğüm kilidi; reddedilen komut güncel durumu gösterir |
| Altın set sentetik olduğu için gerçek projelerdeki kaliteyi yanlış gösterir | v0 ilk deneyleri başlatmak içindir; bir test mühendisi gözden geçirir, gerçek örneklerle v1 kurulur ve deneyler v1 ile tekrarlanır |

Cevaplanan sorular:

| Soru | Cevap | Tasarıma etkisi |
| --- | --- | --- |
| Gereksinimler hangi dilde? | Türkçe ya da İngilizce | Çok dilli modeller; altın set iki dilde |
| Tipik set büyüklüğü ve biçimi? | Değişebilir | Kolon eşlemeli esnek içe alma |
| Ollama'daki Gemma 4 hangi boyut ve bağlamla çalışıyor? | Bilinmiyor, deneyle bulunacak | D0 deneyi |
| Test durumu şablonu sabit mi? | Sabit, ayrıntısı sonra | Şema ayar dosyasından okunur |
| Bir gereksinime birden çok doğrulama yöntemi atanabilir mi? | Evet; liste proje bazında değişebilir ve proje belgelerinde tanımlıdır | Yöntem listesi proje kartında, çıktı çoklu değer |
| Kaç kullanıcı, aynı projede aynı anda mı? | Sayı belirsiz; eşzamanlı çalışma planlanmalı | Çok kullanıcılı çalışma bölümü |
| Sunucu paylaşılacak mı? | Yalnızca bu uygulama; sonradan birkaç modül eklenecek | Aşamalar eklenti olarak tasarlandı |
| Test durumlarının yapısı? | Her adımın ayrı beklenen sonucu; ön koşul, test girdisi ve varsayım duruma göre | Çıktı şeması ve altın set buna göre |

Açık kalan:

- [ ] Altın set v0'ı hangi test mühendisi gözden geçirecek ve gerçek projelerden örnek ekleyecek?
