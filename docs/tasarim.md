# Gereksinim-test stüdyosu: teknik tasarım

Sürüm tarihi: 19 Kasım 2026 · Sahibi: Sami Berkan Akkaya

Bu dosya, tasarım dokümanının depo kopyasıdır. Canlı sürüm: [tasarım dokümanı](https://claude.ai/artifact/HCsRJ2NvdydgwWeUUyDFYm). Şemalar: [whiteboard](https://claude.ai/artifact/7eG12wzy6pSfg56gjpBmwQ). Altın set: [`eval/golden/altin-set-v0.json`](../eval/golden/altin-set-v0.json) ve [tablo hali](https://claude.ai/artifact/PiN7tF6if6FRVaJVgqy6FP).

## Özet

Her çıktı (öbek, test durumu, matris satırı) girdilerinin hash'iyle adreslenir; bir düzenleme yalnızca ona bağlı çıktıları yeniden ürettirir. Aynı bağımlılık grafiği hem cache'in yapısıdır hem de arayüzde çizilen şeydir.

Temel kararlar:

1. Eski Gradio uygulaması taşınmaz, sistem sıfırdan kurulur. Eski koddan ve eski kurulumdan bir şey taşınmaz; güncel en iyi model ve yöntemle başlanır.
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

- Üretim donanımı tek RTX PRO 6000 96 GB'tir ve gerçek proje verisi bu sunucudan çıkmaz. Geliştirme ve deneyler Runpod'da, yalnızca sentetik altın setle yapılır.
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
| Öbekleme | kümeleme ağacı | tüm embedding'ler, kümeleme parametreleri | algoritma |
| Öbek | üye listesi | gereksinim → öbek ataması (ağaç kesimi ya da kullanıcı taşıması) | algoritma, kullanıcı |
| Öbek adı | ad, bir cümle gerekçe | üye gereksinimlerin kimlik ve metinleri, proje kartı | model |
| Arama sonucu | sıralı parça kimlikleri | üye gereksinimlerin metinleri, indeks sürümü | arama |
| Test durumu seti | öbeğin test durumlarının sıralı listesi | öbek üyelerinin kimlik ve metinleri, üyelerin doğrulama yöntemleri, arama sonucundaki parça kimlikleri, proje kartı | model |
| Test durumu | başlık, adımlar, `covers[req_id]` ve diğer şema alanları | ait olduğu setin girdileri | model ya da kullanıcı |
| Doğrulama yöntemi | bir ya da birden çok yöntem ve bir cümle gerekçe | gereksinim metni, proje kartı | model |
| Matris satırı | gereksinim, yöntem, test durumu kimlikleri, kapsama durumu | gereksinim, doğrulama yöntemi, gereksinimi kapsayan test durumları | SQL birleştirmesi |

Her düğümde ortak alanlar bulunur: `input_hash`, `cache_key`, `status` (`fresh`, `stale`, `running`, `failed`), `pinned`, `origin` (`generated`, `edited`), `version`, `produced_by` (model, prompt sürümü ve üretim biçimi).

Kurallar:

- `input_hash`, düğüm tipinin, sıralı girdi içeriklerinin, prompt sürümünün, model kimliğinin ve üretim parametrelerinin SHA-256 özetidir. Düğüm tipi hash'e girer: aynı girdili ve aynı ayarlı iki aşamanın (örneğin tek üyeli öbeğin adı ile o gereksinimin yöntemi) çıktıları cache'te karışmaz. Girdiler düz JSON'dur; aşağı akış düğümleri ham içerik (örneğin vektör) yerine üst düğümün hash'ini kullanır.
- Prompt sürümü aşama başınadır (paket 3'te netleşti): `prompt_version = <ortak sürüm>.<aşama sürümü>+<parmak izi>`. Ortak sürüm sistem talimatını ve proje kartı çizimini, aşama sürümü o aşamanın şablonunu sayar; ikisi de kodda şablonun yanında durur. Parmak izi, ayarla çizilmiş sabit katmanların (sistem talimatı, aşama talimatı, şema, örnekler) SHA-256 özetinin ilk 12 karakteridir; örnek ya da etiket listesi değişince sürüm kendiliğinden değişir. Ortak katman değişirse tüm model aşamaları, bir aşamanın şablonu değişirse yalnızca o aşama bayatlar. Dinamik çizim (gereksinim bloğu, kuyruk) değişince aşama sürümü elle artırılır; anlık görüntü testi bunu denetler.
- Proje kartı düğümü yöntem listesini ve ölçütlerini yapısal olarak da taşır; kart metni bundan çizilir, yöntem şemasının değer listesi buradan gelir (paket 3).
- Bağımlılık ile bağlam ayrıdır (paket 2'de netleşti). Bağımlılıklar `input_hash`'e girer ve bayatlığı belirler. Bağlam (sabitlenmiş test durumlarının içeriği, kullanıcının ek talimatı) bayatlatmaz, ama çıktı cache'inin anahtarına girer: `cache_key = H(input_hash, bağlam hash'i)`. Üretim biçimi (artımlı, baştan, birleştirme, onarım; önceki set) hiçbir anahtara girmez, `produced_by` içinde kaydedilir; biçimi seçen ayarlar da (D8: `generation.regeneration`, `generation.prune_removals`) girmez, çıktıyı değiştiren üretim ayarları (`generation.max_unit_size`, `generation.repair`, yöntem toplu iş boyu) girer (paket 3). Böylece test durumunu elle düzenlemek model çağırmaz, gereksinimi taşıyıp geri almak cache'ten döner.
- Düğüm bayattır ⇔ kayıtlı `input_hash`, güncel girdilerden hesaplanan beklenen hash'ten farklıdır. Her olaydan sonra beklenen hash'ler projenin tamamı için yeniden hesaplanır. Üretim sonucu yazıldığında yalnızca yazılan düğümün aşağı akışı yeniden hesaplanır; sonucun baştan hesapla aynı olduğu testle doğrulanır. Ters bağımlılık dizini arayüz ve doğrulama listesi için tutulur.
- Bir düğümün üstü taze değilse (bayat, çalışıyor, başarısız ya da kendisi bekliyor) düğüm, kendi girdileri değişmediyse bayat sayılmaz, doğrulanacak listesine girer: durumu `fresh` kalır, üstü taze olana kadar kuyruğa alınmaz. Üst düğüm yeniden üretilir; çıktısı aynıysa aşağısı taze kalır (erken kesme). Arama sonucu bu yolla çalışır. Embedding istisnadır: vektörler bayt düzeyinde kararlı olmadığı için aşağısı embedding'i beklenen hash'iyle görür, girdisi değişen embedding'in aşağısı (öbekleme ağacı) doğrudan bayatlar.
- Üretim sonucu yalnızca üstündeki her düğüm taze ya da sabitlenmişken (bekleyen yokken) yazılır; aksi halde reddedilir.
- `running` düğümün işi şu durumlarda iptal edilir: girdisi (`input_hash`) ya da bağlamı (`cache_key`; örneğin öbekte bir test durumu düzenlendi ya da sabitlendi) değişti, düğüm silindi, elle düzenlendi ya da sabitlendi. İptalden sonra durum normal kuralla belirlenir (kayıtlı hash beklenene eşitse `fresh`, değilse `stale`). Eski girdi ya da bağlamla biten sonuç çıktı cache'ine kendi anahtarıyla yazılır, düğüme yazılmaz.
- Hiç üretilmemiş (içeriksiz) düğüm sabitlenemez ve korunamaz.
- Öbek hash'i üyelerin kimlik ve metinlerine bağlıdır, öbeğin adına ya da ekrandaki konumuna değil. Ad değiştirmek testleri bayatlatmaz.
- Sabitleme düğüm başınadır; test setinde sabitlenen birim tek test durumudur.
- Elle düzenleme düğümü o anki girdilerine göre taze yapar: yeni sürümün `input_hash`'i güncel beklenen hash'tir. Sabitlenmiş düğüm sonradan bayatlarsa kullanıcı fark ekranında "benimkini koru" der (`node_kept`): içerik aynı kalır, yeni sürüm güncel hash'i alır.
- Silinen ya da birleştirilen öbeğin sabitlenmiş test durumları kaybolmaz: kapsadığı ilk gereksinimin şimdiki öbeğinin setine taşınır, orada da sabittir ve o setin bağlamına girer.
- Sürüm içerik değişikliğini ve kullanıcı kararını sayar (üretim, düzenleme, taşıma, koruma, sabitleme ve çözme). Durum değişikliği (`fresh`, `stale`, `running`, `failed`) sürüm yazmaz. Silinip yeniden oluşan düğüm 1. sürümden başlar; geçmiş eklemeli tutulur.
- Üretimi başarısız olan düğüm `failed` olur, kuyruğa kendiliğinden girmez ve aşağısını bekletir. Girdisi değişirse yeniden `stale` olur; kullanıcı yeniden deneyebilir.
- Matris satırı kendi gereksinimine de bağlıdır; böylece iki satır aynı cache anahtarını paylaşmaz. Test durumlarını anahtarlarıyla birlikte görür: aynı içerikli test durumu başka öbeğe geçerse satır bayatlar.
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
- Öbek üyeliği somut durumdur; öbekler ağaca değil üyeliğe bağlıdır. Embedding değişince ağaç bayatlar ve arayüzde gösterilir, ama yeniden kesim yalnızca açık komutla (ayrıntı kaydırıcısı, yeniden öbekle) yapılır. Böylece tek metin değişikliği öbekleri dağıtmaz (paket 2'de netleşti).
- İlk kesim içe almada, embedding'ler hesaplanınca vektörlerden yapılır; proje öbeklerle birlikte kurulur (paket 3).
- Yeniden kesimde yeni öbekler eski öbeklerle kesişim büyüklüğüne göre birebir eşlenir. Eski anahtar yalnızca eski üyelerin yarısından fazlası yeni öbekteyse yeniden kullanılır, aksi halde öbek yeni kimlik alır; var olan anahtar tamamen başka üyelerle kullanılmaz. Böylece sabitlenmiş test durumları çoğunlukla kendi gereksinimleriyle aynı sette kalır (paket 3).
- Son üyesi taşınan öbek silinir; adı, seti ve arama sonucu kaldırılır.
- Model her öbek için 3–6 kelimelik ad ve bir cümle gerekçe yazar. Kullanıcının elle yazdığı ad sabittir.

### 3. Test durumu üretimi

- Birim öbektir: bir çağrı, öbeğin gereksinimlerini, proje kartını ve bilgi havuzundan gelen parçaları alır.
- Çıktı şeması: `test_cases[]`, her biri `id`, `title`, `covers[req_id]`, `steps[{no, action, expected}]`, `type` (normal, sınır, hata), `priority` ve duruma göre doldurulan `preconditions`, `test_inputs`, `assumptions`.
- Metin alanlarının model çıktı şemasında üst uzunluğu vardır (`maxLength`, `config/pipeline.yaml` `generation.field_max_chars`; gözlenen en uzun değerlerin rahatça üstünde). Uzun ya da tekrarlı girdi değerleri yazılmaz, tarif edilir ("129 karakterlik parola"). Neden: paket 3'te bir sınır testinde model bitmeyen bir girdi dizisi yazdı ve çıktı `max_tokens`'ta kesildi (KDH-030, [paket 3b](paketler/paket-3b-plan.md)). Kullanıcının düzenlediği test durumu sınırsızdır.
- Her adımın kendi beklenen sonucu vardır; test geneli için tek bir beklenen sonuç yazılmaz.
- Ön koşul, test girdisi ve varsayım alanları gerekmediğinde boş bırakılır; model bunları doldurmak için içerik uydurmaz. Gereksinimin tanımlamadığı bir değer seçildiyse bu, varsayım olarak yazılır.
- Sunucu her gereksinimin en az bir `covers` listesinde geçtiğini doğrular. Eksik kalanlar için yalnızca onları isteyen ek çağrı yapılır.
- 25'ten fazla gereksinimli öbek alt parçalara bölünerek üretilir.
- Öbeğe gereksinim eklenince set baştan yazılmaz. Artımlı prompt mevcut test durumlarını ve yeni gereksinimi alır, yalnızca ekleme ya da güncelleme döner.
- Sabitlenmiş test durumları prompt'a değiştirilemez olarak verilir.

Paket 3'te netleşenler:

- Tüm üretim biçimleri (baştan, artımlı, birleştirme, onarım, şema yeniden denemesi) prompt'un 1–5. katmanlarını bayt bayt aynı kullanır. Biçime özgü malzeme (sabit test durumları, mevcut testler, değişiklik bildirimi, biçimin çıktı şeması, onarım talimatı) prompt'un sonuna eklenir; artımlı ve onarım çağrıları böylece baştan üretimin önek cache'ini kullanır.
- Her üretilen set `produced_by` içinde dayanağını kaydeder: aşama ayarı, kart hash'i, parça kimlikleri, üye başına metin hash'i ve yöntemler. Artımlı biçim yalnızca kart, aşama ayarı ve parça kimlikleri dayanakla aynıyken kullanılır; aksi halde set baştan üretilir. Çekirdeğin üretim ipucu (`Hint`) nedene bakmadığı için kararı üretici verir.
- Artımlı ve birleştirme sonucu tam set olarak yazılır: değişmeyen testler aynı kimlik ve içerikle döner, düğümleri ve matris satırları taze kalır. Sabit teste gelen güncelleme yok sayılır.
- Artımlı prompt'ta değişen ya da çıkan gereksinimi kapsayan testler tam metinle, diğerleri başlık ve kapsama özetiyle verilir (D8 ölçer). Yalnızca çıkan gereksinimi kapsayan testler kodla düşer; karışık kapsamlı testlerin kapsaması kırpılır.
- Birleştirmede model yalnızca düşürülecek tekrarların kimliklerini döner.
- Sunucu `covers` listesini öbeğin yöntemi Test içeren üyelerine süzer; geçersiz ya da Test olmayan kimlik atılır, boş kalan test düşer. Tek onarım çağrısından sonra da kapsanmamış kalan gereksinim düğümü `failed` yapmaz: set yazılır, gereksinim matriste kapsanmamış görünür. Şema hatasında çağrı bir kez yeniden denenir (hata sona eklenir), sonra düğüm `failed` olur.
- İki ayrı 25 sınırı vardır: `clustering.max_cluster_size` kesimde öbekleri, `generation.max_unit_size` üretimde birimi sınırlar (kullanıcının oluşturduğu ya da birleştirdiği büyük öbekler). D7 ikincisini değiştirir.

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

### Sunum motoru adayları

- vLLM aynı anda gelen istekleri tek batch'te işler, ortak prompt önekini bir kez hesaplar ([prefix caching](https://www.mintlify.com/vllm-project/vllm/features/prefix-caching)) ve çıktıyı JSON şemasına zorlar ([structured outputs](https://docs.vllm.ai/features/structured_outputs.html)).
- Ocak 2026 tarihli bir kıyaslamada, RTX PRO 6000 Blackwell üzerinde Llama 3.1 8B ile vLLM en yüksek 8.033 token/sn, SGLang 6.395, Ollama 484 verdi; Ollama 128 eşzamanlı istekte çöktü ([kaynak](https://joshua8.ai/llm-inference-benchmark/)).
- Aynı kartta Gemma 4 31B (FP8, vLLM 0.20) ortalama 823 token/sn toplam, 380 token/sn çıktı verdi; ortalama 13,7 istek aynı anda işlendi, ilk token medyanı 0,73 sn ([kaynak](https://huggingface.co/blog/hexgridcloud/gemma-4-31b-vllm-on-rtx-6000-pro)).
- SGLang aynı altın sette vLLM ile karşılaştırılır (D1).
- Uygulama modele yalnızca OpenAI uyumlu API üzerinden, tek bir `LLMClient` arayüzüyle erişir. Motor ya da model değiştirmek ayar değişikliğidir.
- Başlangıç ayarları: FP8 ağırlıklar, prefix caching açık, 16–32 eşzamanlı dizi, 16–32 bin token bağlam, GPU belleğinin %80'i. Kesin değerler ölçümle belirlenir.

### Ölçüm ortamı (Runpod) ve üretim dağıtımı

Paket 0'da eklendi (19 Kasım 2026).

- Üretim sunucusu ve yerel çalışma Docker Compose kullanır (`infra/compose.yaml`). Runpod pod'u tek bir konteynerdir ve içinde Compose çalışmaz ([Runpod dokümanı](https://docs.runpod.io/pods/overview)). Bu yüzden ölçüm pod'unda motor, embedding servisi ve Postgres aynı konteynerde ayrı süreçler olarak başlar.
- İki dağıtım aynı ayar dosyalarından üretilir (`scripts/infra_render.py`): motor komut satırı tek kaynaktan gelir, iki ortam birbirinden kopamaz.
- Embedding servisi vLLM imajında pooling kipinde çalışır. TEI'nin Blackwell imajı deneysel olarak işaretli, BGE-M3 desteği de belgelenmemiş. SGLang profilinde embedding servisi pod'da başlamaz: embedding motor seçiminden bağımsızdır ve vLLM profilinde ölçülür.
- Veri merkezi EU-RO-1'dir. Kartın stokta olduğu US-PA-1 ve US-NC-3 network volume desteklemez (19 Kasım 2026, `list-data-centers`). Ağırlıklar aynı veri merkezindeki ucuz bir CPU pod'uyla volume'a indirilir. Postgres GPU pod'unda ayrı bir süreç olarak çalışır, verisi volume'da durur.

### Model adayları

| Model | Yapı | Lisans | 96 GB'ta durum | Neden aday |
| --- | --- | --- | --- | --- |
| [Qwen3.8-27B](https://github.com/QwenLM/Qwen3.8) | 27B yoğun | Apache 2.0 | 8 bitte yaklaşık 29 GB, kalanı eşzamanlılığa kalır | Ağustos 2026 çıkışlı, tek GPU için en sık önerilen model; 201 dil ve lehçe desteği beyan ediyor |
| [Gemma 4 31B](https://ai.google.dev/gemma/docs/core/model_card_4) | 31B yoğun | Apache 2.0 | FP8 ile bu kartta ölçülmüş; Google'ın resmî FP8 sürümü olmadığından BF16 (yaklaşık 63 GB) ile başlanır | Google'ın güncel açık modeli; bu kartta ölçülmüş hızı biliniyor |
| gpt-oss-120b | 120B MoE | Apache 2.0 | 4 bitte yaklaşık 61 GB, eşzamanlılık payı daralır | Büyük modelin kalite farkı var mı sorusunun cevabı |

Bu üçlü, tek GPU'lu kurumsal sunucu için yayımlanmış bir [kısa listeyle](https://sysart.consulting/insights/best-open-weight-llms-2026/) örtüşüyor. Boyut rakamları [buradan](https://www.modemguides.com/blogs/ai-infrastructure/best-local-ai-models-by-vram) ve [buradan](https://www.databasemart.com/blog/vllm-gpu-benchmark-pro6000). Yayımlanmış kıyaslamaların çoğu kodlama odaklıdır ve Türkçe test durumu yazma kalitesi hakkında bir şey söylemez.

### Seçim yöntemi: altın set

Altın set, doğru cevabı önceden bilinen küçük bir sınav kâğıdıdır: 30–50 gereksinim ve bunlar için bir test mühendisinin yazdığı ya da onayladığı test durumları ile doğrulama yöntemleri. Her model, prompt ve ayar aynı kâğıtla sınanır; böylece "daha iyi oldu mu" sorusu izlenimle değil sayıyla cevaplanır.

İlk sürüm depodadır: [`eval/golden/altin-set-v0.json`](../eval/golden/altin-set-v0.json). Altın set v1 (paket 1b, [`docs/paketler/paket-1b-altin-set-v1.md`](paketler/paket-1b-altin-set-v1.md)) iki proje ekler: kamu dijital hizmeti ve ERTMS/ETCS araç üstü birimi. Her biri kamuya açık bir belge derlemi ve ondan türetilen en az 100 gereksinim içerir; referans testlerin bir kısmı resmî test spesifikasyonlarından gelir. D9 bu setle ölçülür. Beş sentetik proje (kamu, komuta kontrol, yapay zekâ, savunma-sağlık, yazılım teknolojileri), 40 gereksinim (20 Türkçe, 20 İngilizce), 15 referans öbek ve 49 referans test durumu (135 adım, her adımın kendi beklenen sonucuyla) içerir. Gereksinimleri ve referans cevapları Claude yazdı; set kurumun gerçek projelerini ve test şablonunu yansıtmaz. Bir test mühendisi gözden geçirmeli, gerçek projelerden örnek eklendikçe set v1'e yükseltilmelidir.

- Set Türkçe ve İngilizce gereksinimleri, kolay ve zor örnekleri birlikte içerir.
- Ölçülenler: şema geçerliliği, kapsama (her gereksinim bir `covers` listesinde), doğrulama yöntemi doğruluğu, uzmanın kör karşılaştırmada verdiği 1–5 puan, öbek başına süre, 16 eşzamanlı istekte token/sn.
- Qwen3.8-27B'de düşünme modu varsayılan olarak açıktır ve istek başına kapatılabilir ([haber](https://www.eweek.com/news/alibaba-qwen3-8-27b-license-apac-china/)). Sınıflandırmada kapalı, test üretiminde iki hali de ölçülür.
- Altın set kalıcıdır: her prompt ve model değişikliği aynı setle yeniden ölçülür.

### Puanlama

Test kalitesi üç katmanda ölçülür; ucuz olan her koşuda, pahalı olan yalnızca finalde çalışır. Ölçüt tanımları `docs/paketler/paket-1-olcum.md` içindedir.

| Katman | Ne ölçer | Nasıl | Ne zaman |
| --- | --- | --- | --- |
| 1. Kural denetimi | şema geçerliliği; her adımda işlem ve beklenen sonuç; kapsama; yöntemi Test olmayana test yazılmaması; yöntem kümesinin referansla eşleşmesi; öbek uyumu | kod, model çağrısı yok | her koşu |
| 2. Hakem model | referans testteki her denetimin (adım ve beklenen sonuç çifti) üretilen testlerde karşılığı var mı; gereksinimde olmayan uydurma içerik var mı; sınır ve hata durumları yakalanmış mı; belirsizlik varsayım olarak yazılmış mı | sabit hakem model, sabit rubrik, sıcaklık 0 | her deney |
| 3. Uzman | kör ikili karşılaştırma, 1–5 puan | test mühendisi, 10 öbeklik örneklem | yalnızca en iyi iki aday için ve hakemi ayarlarken |

- Hakem, sentetik altın sette Claude Sonnet'tir: adaylardan bağımsızdır ve veri hassas değildir. Gerçek proje verisi sete girdiğinde hakem yerel modele ya da uzmana geçer.
- Hakem çağrıları `LLMClient` üzerinden değil, resmî Anthropic SDK'sıyla `services/judge_client.py` içinden yapılır; yerel modeller için konan "yalnızca OpenAI uyumlu API" kuralı hakemi kapsamaz. Model `claude-sonnet-5-5`'tir. Bu model sıcaklık parametresini kabul etmez; tekrarlanabilirliği hakem çıktılarının girdi hash'iyle cache'lenmesi sağlar (paket 1'de eklendi).
- Hakemin ana ölçütü denetim yakalama oranıdır: referanstaki denetimlerin yüzde kaçı üretilen testlerde var. Üslup puanlanmaz.
- Referansı da hakemi de Claude yazdığı için Claude'a benzeyen çıktılar kayırılabilir. D0 deneyi hakem puanını uzman puanıyla karşılaştırır; uyum düşükse rubrik düzeltilir.
- Karar kuralı: aday önce katman 1 eşiklerini geçer (şema %99, onarım sonrası kapsama %100, adım yapısı %100). Geçenler denetim yakalama oranına göre sıralanır, eşitlikte hızlı olan öne geçer. İlk iki adayı uzman karşılaştırır.
- Tek bir toplam puan üretilmez; rapor ölçütleri ayrı sütunlarda verir.

### Embedding modeli

Varsayılan BGE-M3'tür: çok dillidir, tek modelden hem yoğun hem seyrek vektör verir ve Türkçe embedding kıyaslamalarında taban model olarak kullanılır ([örnek](https://arxiv.org/pdf/2601.16018)). Ayrı küçük bir servis olarak aynı GPU'da çalışır ve 3–5 GB yer tutar. Model sürümü embedding'in hash'ine girer.

## Deney planı

Aşağıdaki kararların hiçbiri tahminle verilmez; her biri altın set üzerinde denenir ve kazanan seçilir. Son sütun, ölçüm gelene kadar geliştirmenin dayandığı varsayımdır.

| No | Soru | Denenenler | Ölçüt | Çalışma varsayımı | Sonuç (paket 1, 19 Kasım 2026) |
| --- | --- | --- | --- | --- | --- |
| D0 | Otomatik hakem puanı uzman puanıyla uyuşuyor mu | hakem modelin puanı ile test mühendisinin puanı, 10 öbeklik örneklemde | sıra uyumu ve puan farkı | hakem güvenilir sayılır | Koşulmadı: test mühendisi yok. Hakemle devam edildi; hakem puanı uzmanla doğrulanmadı. |
| D1 | Sunum motoru | vLLM, SGLang | 1, 8, 16 ve 32 eşzamanlı istekte token/sn, ilk token süresi, hata oranı, şema geçerliliği | vLLM | **vLLM.** 32 eşzamanlı istekte 777 token/sn (SGLang 698), ikisinde de hata 0 ve şema %100. SGLang hibrit modelde kısa ortak öneki cache'lemiyor. [D1](deneyler/D1.md) |
| D2 | Model | Qwen3.8-27B, Gemma 4 31B, gpt-oss-120b | denetim yakalama oranı, kapsama, yöntem doğruluğu; Türkçe ve İngilizce ayrı raporlanır | Qwen3.8-27B | **Qwen3.8-27B (uzman karşılaştırmasına kadar).** Güncel ayarlarla 3'er tekrar: check_recall Qwen ort. 0,454 (0,44–0,47), gpt-oss ort. 0,416 (0,36–0,46), Gemma 0,40. gpt-oss 1,8 kat hızlı ama iki kat uydurma içerik yazıyor. Fark kesin değil; ilk iki aday uzman karşılaştırmasına gider. [D2](deneyler/D2.md) |
| D3 | Düşünme modu ve örnekleme | düşünme açık ve kapalı; sıcaklık 0 ile 0,7 arası | kalite farkı ve süre | sınıflandırmada kapalı | **Düşünme kapalı, sıcaklık 0.** Düşünme açık 4,8 kat yavaş, recall 0,43. Sıcaklıklar arasında ölçülebilir fark yok (0,48 / 0,45 / 0,42–0,48). [D3](deneyler/D3.md) |
| D4 | Ağırlık hassasiyeti | 16 bit, FP8, 4 bit (resmî 4 bit depo olmadığı için BF16'dan çalışma anında nicemleme) | kalite kaybı ve eşzamanlılık kazancı | FP8 | **FP8.** BF16 ile recall farkı yok (0,44), FP8 1,8 kat hızlı. 4 bit (çalışma anında MXFP4) bu modelde yüklenemedi. [D4](deneyler/D4.md) |
| D5 | Eşzamanlılık ve bağlam | dizi sınırı 8 ile 64 arası; bağlam 8, 16, 32 bin token | toplam token/sn ve öncelikli işin ilk token süresi | 16–32 dizi | **64 dizi, 32 bin bağlam.** Dizi sınırı 32'de 64 istek kuyruğa giriyor (ilk token 35,8 sn); 16'da 64 istekte 3 hata (kuyrukta ~100 sn bekleyen bağlantılar koptu). 64 dizi 64 istekte 1.183 token/sn, ilk token 1,2 sn. 16 bin bağlamın hız faydası yok. [D5](deneyler/D5.md) |
| D6 | Embedding ve kümeleme | BGE-M3 ve iki alternatif; agglomerative ve HDBSCAN | uzmanın elle öbeklemesiyle uyum, kullanıcının yapmak zorunda kaldığı taşıma sayısı | BGE-M3, agglomerative | **BGE-M3, agglomerative average, eşik 0,35 (değişmedi)** (paket 3). Alternatif modeller geçmedi; HDBSCAN v1'de iyi ama ağaç tutmuyor, v0'da öbekleri dağıtıyor. Eşik 0,30 v1'de taşımayı azalttı (54 → 45, 70 → 66) ama gereksinim bootstrap aralıkları sıfırı geçmiyor ve v0'da kötü: aday olarak kaldı. Referans belge bölümleri (uzman değil), iki proje: uzman öbeklemesiyle yeniden ölçülmeli. [D6](deneyler/D6.md) |
| D7 | Üretim birimi | öbek başına tek çağrı ve gereksinim başına çağrı; birim sınırı 10 ve 25 (50 çıkarıldı: Test gereksinimi başına ~624 çıktı token'ıyla ~31 bin token eder, 32 bin bağlama sığmaz; paket 3) | kalite, tekrar eden test oranı, süre | öbek başına, sınır 25 | **Öbek başına kalır** (paket 3; kullanıcı kararı, 21 Kasım 2026). Artış test sayısından geliyor: test sayısı iki kolda aynı olan 80 gereksinimde fark +0,011, gereksinim başına kolun daha çok test yazdığı 133 gereksinimde +0,110. Daha çok kapsama istenirse öbek bağlamını koruyan prompt deneyi (gereksinim başına daha çok sınır ve hata testi) daha ucuz yoldur. Hakem recall'ı: gereksinim başına çağrı 0,495, öbek başına 0,426, 10'luk paket 0,385, 25'lik paket 0,355. Gereksinim başına çağrı öbek başınadan ölçülebilir biçimde iyi (+0,069 [+0,028, +0,110]; ikinci öbek başına koşuya göre +0,046 [+0,012, +0,082]) ama uydurma içerik %48 (1,26 → 1,87), test sayısı %57, çıktı token'ı %55 artıyor; öbekleri paketlemek ölçülebilir biçimde kötü. [D7](deneyler/D7.md) |
| D8 | Yeniden üretim biçimi | artımlı ve baştan (ekleme), artımlı çağrı ve modelsiz budama (çıkarma), birleştirme prompt'u ve baştan (birleştirme); kollar aynı taban üzerinde | tutarlılık, kullanıcı düzeltmelerinin korunması, süre | artımlı | **Ekleme: artımlı; çıkarma: modelsiz budama; birleştirme: birleştirme prompt'u** (paket 3). Eklemede artımlı önceki testlerin %100'ünü korudu (baştan %9), düzeltmeleri tekrarlamadı (baştan 7), token'ın dörtte birini harcadı; recall farkı yok (+0,029 [−0,020, +0,079]). Çıkarmada çağrı ile budama aynı seti verdi (fark +0,008 [0, +0,024]): daha basit olan budama (`generation.prune_removals: true`). Birleştirmede prompt 100 kat az token, 8 kat kısa; recall farkı yok. [D8](deneyler/D8.md) |
| D9 | Bilgi havuzu | parça boyu 300, 500, 800 token; ilk 4, 8, 12 parça; reranker var ve yok; proje kartı var ve yok | altın set puanı | 300–500 token, ilk 6–8, reranker yok | pilot (paket 1b): altın set v1 belgenin etkisini ölçebiliyor; kâhin parçalarla belge gerektiren denetimlerde recall 0,28 → 0,49 ([`D9`](deneyler/D9.md)). Parça boyu, sayı ve reranker paket 7'de |
| D10 | Örnek havuzu | 0, 2, 4 örnek | uzman puanı ve üslup uyumu | 2–3 örnek | bu paketin kapsamı dışında |
| D11 | Kuyruk ayarları | bekleme 0,5, 1,5, 3 sn; otomatik işlerin yuva payı | boşa giden çağrı oranı ve algılanan gecikme | 1,5 sn, %70 | bu paketin kapsamı dışında |
| D12 | Önek ısıtma | paralel çağrıları ilk çağrı öneki işleyene kadar bekletmek ve bekletmemek | ilk üretimin toplam süresi ve önek cache isabet oranı | bekletmek | **Bekletmemek.** Önek isabeti aynı (%54), süre biraz kısa, recall farkı gürültü içinde. [D12](deneyler/D12.md) |

Kurallar:

- Her deney `eval/` koşucusunda tek komutla tekrar edilebilir ve sonucu bu tabloya Sonuç sütunu olarak işlenir.
- Paket 1 deneylerinde (D1–D5, D12) test üretimi referans öbek ve referans doğrulama yöntemleriyle beslenir. Böylece üretim kalitesi öbekleme ve sınıflandırma hatalarından ayrılır. Öbekleme uyumu (ARI, D6) ve yöntem doğruluğu aynı koşuda ayrı ölçütler olarak raporlanır. Uçtan uca ölçüm için `generation_inputs: predicted` ayarı vardır.
- Bir deneyde tek değişken değişir; diğerleri çalışma varsayımında kalır.
- Ölçülebilir fark yoksa daha basit olan seçenek kalır.
- Sıra: D1, D2, sonra D3–D5 ve D12. D0 test mühendisi hazır olduğunda koşulur. D6–D10 ilgili aşama yazıldığında, D11 arayüz kullanılır hale geldiğinde koşulur.
- Kod, çalışma varsayımlarını ayar dosyasından okur; deney sonucu bir satırlık değişiklikle uygulanır.

## Cache, geçersiz kılma ve iş kuyruğu

Bir düzenlemenin maliyeti, bayatlattığı düğüm sayısı kadardır; çoğu düzenleme sıfır ile iki model çağrısı arasında kalır.

### Üç cache katmanı

| Katman | Ne saklar | Anahtar | Nerede |
| --- | --- | --- | --- |
| Çıktı cache'i | üretilmiş düğüm içerikleri | `cache_key` (`input_hash` ve bağlam) | Postgres |
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

Sayılar büyük model çağrısıdır; embedding ayrı sayılır. Matris satırları kapsanan gereksinimler için bayatlar ve model çağırmaz. Tablo paket 2'de veri modeliyle tutarlı hale getirildi: öbek adı üye metinlerine bağlı olduğu için silme, birleştirme ve metin değişikliği satırlarına ad çağrısı eklendi; son iki satır yeni.

| Olay | Bayatlayan | Model çağrısı |
| --- | --- | --- |
| Gereksinim A öbeğinden B'ye taşındı | A ve B'nin test setleri ve adları | 1 artımlı test (B; A'nın seti çağrısız budanır, D8), 2 ad |
| Öbek yeniden adlandırıldı | hiçbir şey | 0 |
| Öbek silindi, üyeleri dağıtıldı | üye alan öbeklerin setleri ve adları | üye alan öbek başına 1 test, 1 ad |
| İki öbek birleştirildi | yeni öbeğin seti ve adı | 1 test (iki set birleştirilir, model yalnızca tekrarları ayıklar), 1 ad |
| Gereksinim metni değişti | embedding, doğrulama yöntemi, öbeğin test seti ve adı | 3 (yöntem, test, ad) |
| Test durumu elle düzenlendi | yalnızca matris satırları | 0 |
| Bilgi havuzuna belge eklendi | getirilen parçaları değişen öbeklerin setleri | değişen öbek başına 1 |
| Prompt ya da model sürümü değişti | o aşamanın tüm çıktıları, kullanıcı onayıyla | toplu, arka planda |
| Doğrulama yöntemi elle değişti | öbeğin test seti | 1 |
| Proje kartı değişti | projedeki tüm model çıktıları, kullanıcı onayıyla | toplu, arka planda |

D8 (paket 3) sonrası: yalnızca üye çıkan set modelsiz budanır (`generation.prune_removals: true`): yalnızca çıkan gereksinimi kapsayan sabit olmayan testler düşer, karışık testlerin `covers` listesi kırpılır. Çekirdeğin `llm_calls` tahmini budamayı bilmez, bu seti hâlâ bir çağrı sayar (kuyruk ve tahmin paket 5).

İki ayrıntı önemlidir. Test setinin hash'ine indeks sürümü değil, getirilen parçaların kimlikleri girer; belge eklemek, arama sonucu değişmeyen öbekleri bayatlatmaz. Bayatlayan sabitlenmiş düğüm kendiliğinden yeniden üretilmez, çağrı sayısına girmez, kullanıcıya uyarı olarak gösterilir.

### İş kuyruğu

- Üç öncelik sınıfı vardır: P0 kullanıcının seçili ya da ekranda görünen öğesi, P1 kullanıcının tetiklediği diğer işler, P2 otomatik ilerleme.
- Düzenlemeden sonra 1,5 saniye beklenir; art arda gelen sürüklemeler tek işe indirgenir.
- Aynı düğüm için bekleyen iş varsa yenisi onun yerine geçer. Çalışan işin girdisi değiştiyse akış kesilerek iptal edilir.
- Eşzamanlılık sınırı vLLM'in dizi sınırına eşittir; P2 işleri yuvaların en çok %70'ini kullanır.
- Şema doğrulaması başarısız olursa bir kez yeniden denenir, sonra düğüm `failed` olur. Çıktı `max_tokens`'ta kesildiyse (`finish_reason: length`) yeniden denenmez: yeniden deneme en pahalı çağrıyı ikiye katlar ve dejenerasyonu büyük olasılıkla tekrarlar (paket 3, KDH-030: aynı prompt 5 koşunun 3'ünde kesildi, 2'sinde geçti).
- İlk sürümde kuyruk, iş kayıtları Postgres'te duran bir asyncio işçi havuzudur. Tek GPU için Redis ya da Celery gerekmez.

### Beklenen süreler (tahmin, ölçülecek)

200 gereksinim ve 20 öbek için ilk üretim yaklaşık 20 test çağrısı, 8 doğrulama çağrısı ve 20 ad çağrısıdır. Çağrı başına 1.200 çıktı token'ı ve yukarıdaki 380 token/sn ölçümüyle test üretimi 1–2 dakika sürer. Tek bir taşıma, sonucu birkaç saniyede akmaya başlayan bir artımlı çağrıdır (çıkılan set çağrısız budanır, D8).

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
- Arama birimi öbektir. Sorgu üye gereksinimlerin metnidir; gereksinim başına değil öbek başına bir arama yapılır. Öbek adı sorguya girmez: girseydi yeniden adlandırma arama sonucunu ve test setini bayatlatabilirdi (paket 2'de netleşti). Adın faydası D9'da ölçülebilir.
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

## Claude Code'dan alınan yöntemler

Claude Code'un verimliliği üç fikre dayanır ve üçü de yerel modelle çalışan bu uygulamaya taşınabilir: önek cache'ini bozmamak, bağlamı küçük tutmak ve her üretimi doğrulamak. Ayrıntılı not: [`docs/arastirma/claude-code-yontemleri.md`](arastirma/claude-code-yontemleri.md).

| Yöntem | Claude Code'da | Bu uygulamada | Durum |
| --- | --- | --- | --- |
| Kararlıdan değişkene önek sırası | sistem prompt'u, proje bağlamı, konuşma | sistem talimatı, proje kartı, şema, parçalar, gereksinimler | tasarımda vardı |
| Durum değişikliğini öneke değil sona yazmak | güncellemeler sistem prompt'una değil sonraki mesaja eklenir | kullanıcı düzeltmeleri, sabit testler ve ek talimatlar prompt'un sonuna eklenir; önek değişmez | eklendi |
| Oturum ortasında model değiştirmemek | cache model başınadır; değişim tüm cache'i yeniden kurar | tüm aşamalar tek modelle çalışır; küçük yardımcı model kullanılmaz | eklendi |
| Yan işlemler ana öneki paylaşır | özetleme çağrısı ana konuşmanın önekini aynen kullanır | öbek adı, doğrulama yöntemi ve onarım çağrıları test üretimiyle aynı sistem talimatını ve proje kartını kullanır | eklendi |
| Yelpaze açılırken ısıtma | aynı önekli ajanların ilki cache'i yazana kadar diğerleri kısa süre bekletilir | bir projenin ilk çağrısı öneki işleyene kadar paralel çağrılar bekletilir | D12 deneyi |
| Cache isabet oranını izlemek | oran düşüşü olay sayılır, olası neden gösterilir | sunum motorunun önek cache ölçümleri proje ve aşama bazında izlenir; düşüş uyarı üretir | eklendi |
| Bağlamı küçük tutmak | fazla token hatırlamayı zayıflatır; eski araç çıktıları önce temizlenir | öbek sınırı ve parça sayısı sınırlıdır; artımlı prompt'ta mevcut testler tam metin yerine başlık ve kapsama özetiyle verilir | D7, D8, D9 |
| Ayrı bağlamda çalışıp özet döndürmek | alt ajanlar kendi bağlamında çalışır, yalnızca özet döner | her öbek ayrı çağrıdır ve yalnızca yapılandırılmış sonuç döner | tasarımda vardı |
| Gerektiğinde yükleme | beceriler ve araç şemaları yalnızca kullanılınca yüklenir | aşama talimatları yalnızca o aşamanın prompt'una girer; belge içeriği aramayla gelir | tasarımda vardı |
| Ön işlemeyi koda bırakmak | kancalar veriyi model görmeden önce süzer | içe almada tekrar eden kalıp metin ve biçim artıkları kodla temizlenir | eklendi |
| Topla, uygula, doğrula döngüsü | her işin sonunda sonucu sınayacak bir hedef verilir | her üretimi kod doğrular (şema, kapsama, adım yapısı); yalnızca hatalı kısım için onarım çağrısı yapılır | tasarımda vardı |
| Pahalı işten önce plan | plan kipi yanlış yöne giden pahalı işi önler | onaylı modda öbekler görülmeden test üretimi başlamaz | tasarımda vardı |
| Geri sarma cache'e döner | önceki tura dönüş zaten cache'lenmiş öneke döner | geri alma içerik adresli cache'ten anında gelir | tasarımda vardı |
| Kullanım dökümü | token kullanımı kaynağa göre dökülür | aşama ve proje başına token, iptal edilen çağrı ve cache isabeti kaydedilir | eklendi |

Aynı yöntemlerin geliştirme sürecine uygulanışı deponun `CLAUDE.md` dosyasında kurala bağlandı: paket başına tek oturum ve tek model, kısa `CLAUDE.md`, gürültülü çıktılar alt ajana, karmaşık paketlerde önce plan.

## Geliştirme planı

İş on pakete bölünür; tasarım kararı içeren paketleri Opus, tanımı net uygulama işlerini Sonnet yapar. Paket görev tanımları `docs/paketler/` altındadır.

| No | Paket | Model | Bitti ölçütü |
| --- | --- | --- | --- |
| 0 | Altyapı: aday sunum motorları, embedding servisi, Postgres, Docker Compose, `LLMClient` | Sonnet | 16 eşzamanlı istek hatasız ve şemaya uygun dönüyor |
| 1 | Altın set ve ölçüm koşucusu | Opus tasarlar, Sonnet yazar | D0–D5 deneyleri koşuldu; motor, model ve ayarlar ölçümle seçildi |
| 2 | Çekirdek: veri modeli, hash, bağımlılık grafiği, geçersiz kılma ([plan](paketler/paket-2-plan.md)) | Opus | Bayatlama tablosundaki her satırın birim testi geçiyor |
| 3 | Aşamalar ve prompt'lar: öbekleme, test üretimi (artımlı dahil), doğrulama yöntemi ([plan](paketler/paket-3-plan.md); ek iş [3b](paketler/paket-3b-plan.md)) | Opus | Altın sette belirlenen eşikler aşılıyor. Yorum (kullanıcı kararı, 20 Kasım 2026): yeni aşama koduyla, referans öbek ve yöntemlerle v0 ve v1'de katman 1 eşikleri geçer; check_recall paket 1 tabanından gürültüden fazla düşmez (aynı gereksinimler üzerinde yeni − taban farkının eşleştirilmiş bootstrap %95 aralığının alt sınırı ≥ −0,05; kullanıcı onayı, 21 Kasım 2026); uçtan uca koşu raporlanır ve orada kapsama tahmin edilen yöntemlere göre %100'dür |
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
| Eski kurulum (Ollama, Gemma 4) incelenecek mi? | Hayır; geçmiş bırakıldı, güncel en iyi seçenek deneyle bulunacak | D1 ve D2 deneyleri |
| Test durumu şablonu sabit mi? | Sabit, ayrıntısı sonra | Şema ayar dosyasından okunur |
| Bir gereksinime birden çok doğrulama yöntemi atanabilir mi? | Evet; liste proje bazında değişebilir ve proje belgelerinde tanımlıdır | Yöntem listesi proje kartında, çıktı çoklu değer |
| Kaç kullanıcı, aynı projede aynı anda mı? | Sayı belirsiz; eşzamanlı çalışma planlanmalı | Çok kullanıcılı çalışma bölümü |
| Sunucu paylaşılacak mı? | Yalnızca bu uygulama; sonradan birkaç modül eklenecek | Aşamalar eklenti olarak tasarlandı |
| Test durumlarının yapısı? | Her adımın ayrı beklenen sonucu; ön koşul, test girdisi ve varsayım duruma göre | Çıktı şeması ve altın set buna göre |

Açık kalan:

- [ ] Altın set v0'ı hangi test mühendisi gözden geçirecek ve gerçek projelerden örnek ekleyecek?
