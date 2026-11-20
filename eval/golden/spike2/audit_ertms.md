# ERTMS denetim kayıplarının denetimi (Deneme 2, ETC-901..905)

20 Kasım 2026. Paket 1b, aşama 5 kapısı (1): 15 ERTMS referans denetiminin her kaybı sınıflandı. Model çağrısı yapılmadı. Kaynaklar şunlar:

- `items.json`, `generated_with_docs.json`, `results_r1.json`, `results_r2.json`.
- Eşleşmeyen kararların gerekçesi için hakem önbelleği (`eval/cache/judge/`).
- `eval/corpus/etc/probe/` (`srs_clauses.json`, `refs2.json`).

## Okuma notları

- **Örnekler hakem tekrarıdır.** `with_docs#0..#2` aynı tek üretimin üç bağımsız hakem örneğidir; yalnızca bir `generated_with_docs.json` var. "r1 x/3" hakem kararlılığını ölçer, yazarın kararlılığını ölçmez. WRITER_MISS etiketi tek bir üretime dayanır.
- **Eşleşen denetimler kayıp değildir.** Beş denetim iki rubrikte de 6/6 eşleşti: 901 #1-3, 903 #3 ve 905 #1. Bunlar tabloda "eşleşti" durumuyla durur ve kayıp etiketi almaz. Hiçbiri ters yönde hakem hatası değil: her birinde üretilen adım aynı ayırt edici koşulu ve aynı davranış çekirdeğini taşıyor.
- **Etiketlerin ayrımı (bağlayıcı kural).** Bir denetimin sınadığı madde iki koşulu birlikte sağlıyorsa gereksinimin kapsamındadır:
  - gereksinim cümlesinde ya da cümlenin andığı maddede geçiyor;
  - adım gereksinimin kendi senaryosunun bir parçası.

  Bu iki koşulu sağlamayan denetim MANY_TO_MANY olur, maddenin destek parçası olarak eklenmiş olması sonucu değiştirmez. Rubrik, gereksinimin söylemediği içeriği `invented` sayar. Bu yüzden yazar böyle bir denetimi karşılarsa ceza alır.
  - 903 #2 bu kuralla kapsamda kalır. §3.6.4.2.2.2 "this clause 3.6.4.2.2" diyerek SOLR kuralını kendine bağlar, ve adım SOLR'nin geçişten önceki durumunu, yani gereksinimin anlattığı değişimin başlangıcını gösterir.
  - 905 #2 ve #4 kapsam dışında kalır. Zamanlayıcıyla tekrar (§3.8.2.1.5) gereksinim cümlesinde de, TC7'nin "Based on" listesinde de geçmez.
- **Görevdeki bir varsayımın düzeltmesi.** §3.8.2.1.5 derlemde eksik değil: ETC-905 maddesine `ETC-905-P1` olarak eklenmiş. 905 #2 ve #4'ün kaybı derlem eksiğinden gelmiyor, kapsamdan geliyor.

## Tablo

Sayımlar `with_docs` için verildi. "r1" ve "r2" sütunları, o rubrikte üç hakem örneğinden kaçının denetimi eşleşmiş saydığını gösterir.

| Madde | No | Denetim (kısa) | Etiket | r1 | r2 | Kanıt | Düzeltme |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ETC-901 | 1 | BG1 (Q_LINK=1, linking'de) → konum raporu BG1'e atıf | eşleşti | 3/3 | 3/3 | TC01 adım 1: "The position report to the RBC uses BG1 as LRBG." JRU kısmı göz ardı edildi, davranış çekirdeği aynı. | yok |
| ETC-901 | 2 | BG2 (Q_LINK=0) → rapor hâlâ BG1 | eşleşti | 3/3 | 3/3 | TC02 adım 2 (Scenario B, Q_LINK = 0): "The position report still uses BG1 as LRBG". | yok |
| ETC-901 | 3 | BG3 (Q_LINK=1, linking'de yok) → rapor hâlâ BG1 | eşleşti | 3/3 | 3/3 | TC02 adım 1 (Scenario A, "linked ... but not contained in the previously received linking information"): rapor BG1'de kalıyor. | yok |
| ETC-902 | 1 | CES (msg 15), Q_DIR ters → JRU kaydı, DMI'da acil durdurma yok | SCENARIO_SPECIFIC | 0/3 | 3/3 | TC02 adım 2: radyo mesajı, Q_DIR = 01, tren yönü LRBG'nin tersi; beklenen sonuç "The information is ignored." r1 hakemi şunu yazdı: "does not use Conditional Emergency Stop, JRU recording or the absence of a DMI reaction". Kanal toleranslı r2 bunu üç örnekte de eşleşmiş saydı. | Denetimi davranış düzeyinde yeniden yaz ("ters yönlü radyo bilgisi yok sayılır; tren tepki vermez"). JRU kısmını kanal notuna indir. |
| ETC-902 | 2 | TAF Request (msg 34), Q_DIR = Q_DIRLRBG → DMI'da TAF simgesi, JRU Bit82 | SCENARIO_SPECIFIC | 0/3 | 1/3 | TC02 adım 1 genel kalıyor: "The information is taken into account, since its validity direction ... matches". Hakem (`with_docs`, r1): "has no Track Ahead Free Request, no DMI symbol and no JRU records". Mesaj 34'ün etkisi ve TAF simgesi derlemde yok. **Yazarın ikincil zaafı:** "taken into account" gözlemlenebilir bir sonuç değil. | Denetimi "geçerli yönlü bilgi uygulanır, gözlemlenebilir etkisi oluşur" diye yeniden yaz. Somut mesaj korunacaksa SUBSET-026-8 mesaj listesini ve TAF maddesini parçaya ekle. |
| ETC-902 | 3 | CES, Q_DIR = 2 (iki yön) → DMI ST01 (fren müdahalesi), JRU Bit38 | SCENARIO_SPECIFIC | 0/3 | 1/3 | Üretilen testte iki yön yalnızca balise üzerinden var. TC01 adım 2: "Q_DIR = 10 ... The information is taken into account." Hakem: "the radio test has no Q_DIR=2 case. There is no Conditional Emergency Stop, ST01 symbol". **Yazarın ikincil zaafı:** radyo ile iki yön birleşimi yok. Gereksinim "any transmission medium" diyor ve P1 §3.6.3.1.1 a) radyoyu LRBG yönüne bağlıyor. | Davranış düzeyinde yeniden yaz ("iki yön geçerli radyo bilgisi uygulanır"). ST01 ve Bit38 için ERA DMI belgesi gerekir; kanal notuna indir. |
| ETC-903 | 1 | General message (24) + paket 5 (FRBG'ye atıflı), L2 geçiş emri kayıtlı → yalnızca JRU "MESSAGE FROM RBC" | CORPUS_GAP | 0/3 | 0/3 | Beklenen sonucun tamamı bir JRU kaydı (`NID_MESSAGE_JRU=9`, SUBSET-027). Davranışın kendisi (linking'in geçiş tamponuna alınması) TC02'de ön koşul olarak duruyor: "linking information held in the transition buffer". Geçiş tamponu (§4.8) da parçalarda yok. | Denetimi ön koşula taşı (uyaran adımı). SUBSET-027 eklemek bu satırı kurtarır ama değerlendirmeye bir şey katmaz. |
| ETC-903 | 2 | BGx (Q_LINK=1, kayıtlı linking'de duyurulmuş) geçilir → NID_SOLR = BGx | WRITER_MISS (güven: orta-düşük) | 0/3 | 0/3 | P1 §3.6.4.2.2 a) ve Not §3.6.4.2.2.3 değişimi anlatıyor: "provokes the change of SOLR to a former LRBG". TC02 serbest bırakmadan önceki SOLR'yi hiç gözlemiyor; yalnızca ön koşul var ("balise groups in rear of the border have been passed") ve adım 2 sonrayı ölçüyor. Gözlem kanalı engel değil: yazar zaten "test interface or log" varsayıyor. | yok (gerçek sinyal). Yazar istemine "değişimi göstermek için önceki durumu da doğrula" ilkesi eklenebilir. |
| ETC-903 | 3 | L2'ye geçiş → tampon serbest kalır; BGx LRBG kalır, FRBG yeni SOLR olur | eşleşti | 3/3 | 3/3 | TC02 adım 2: "this may be a former LRBG rather than the last passed balise group". DMI'daki "Level 2" simgesi karşılanmadı, hakem bunu tolere etti. | yok |
| ETC-904 | 1 | OS'te sürücü hız/mesafe gösterimini ister → JRU DRIVER'S ACTIONS | MANY_TO_MANY | 0/3 | 0/3 | Eylem, OS kipinde istek üzerine gösterim; beklenen sonuç sürücü eyleminin JRU kaydı (SUBSET-027). İkisi de SSP değiştirme kuralı (§3.7.3.1 a)) değil. TC14'ün "Based on" listesi (3.7.3.1, 3.7.3.1 a)) bu adımı dışlamıyor. | Denetimi çıkar ya da ön koşula taşı. |
| ETC-904 | 2 | Yeni SSP (paket 27, balise ya da RBC), hemen geçerli → DMI yeni SSP'yi gösterir, JRU kayıtları | JUDGE_ERROR (tartışmalı) | 1/3 | 0/3 | TC01 adım 3: "Inspect the stored SSP between B and C." Beklenen sonuç "The new profile values apply." Adım 4 de eskinin silindiğini doğruluyor. Eşleşmeyen `with_docs` kararlarının çoğunda kanıt alanı boş; gerekçe yalnızca `invented` içinde: "Abstract 'transmit' and 'inspect stored SSP' steps without a specified channel (balise/RBC, DMI, JRU)". Kanıtı dolu olan bir karar: "Generated tests check internal stored SSP replacement but do not involve receiving packet 27 via balise/RBC, JRU recording of the message, DMI display of the new SSP". r2 eki "another equivalent input ... another channel" kabul ediyor, buna rağmen 0/3. 902 #1'den farkı şu: burada aynı girdide karar değişiyor (r1 1/3) ve r2 kendi kanal maddesine aykırı biçimde reddediyor; 902 #1'de ise r2 kararlı biçimde eşleştirdi, kayıp yalnızca r1'in somut senaryo istemesinden geliyor. Altı kararın beşi aksi yönde; etiket benim okumam. | Denetimi davranış düzeyinde yaz ("yeni SSP başlangıç konumundan itibaren yürürlükte"). Hakemde çoğunluk oyu ya da daha çok örnek kullan. |
| ETC-905 | 1 | Tren pertürbasyon konumuna T_MAR kala noktayı geçer → MA Request, Q_MARQSTREASON = xxx1x | eşleşti | 3/3 | 3/3 | TC01 adım 2-3: "An MA request is sent to the RBC" ve ardından "Bit ... (xxx1x) is set." | yok |
| ETC-905 | 2 | T_CYCRQST dolar → MA Request tekrarlanır (xxx1x) | MANY_TO_MANY | 0/3 | 0/3 | Tekrar §3.8.2.1.5'ten geliyor: "shall repeat the MA requests as indicated by the RBC". Madde P1'de var, ama gereksinim cümlesinde ve TC7 "Based on" listesinde (3.8.2.1.7, 3.8.2.2.2) yok. Yazar hiç tekrar testi yazmadı. Yazsaydı rubrik bunu `invented` sayabilirdi. | Ya gereksinim metnine §3.8.2.1.5'i ekle (o zaman adil bir WRITER_MISS hedefi olur) ya da denetimi çıkar. |
| ETC-905 | 3 | Tren EoA'da durur → Train Position Report (msg 136) | MANY_TO_MANY | 0/3 | 0/3 | Duruşta konum raporu büyük olasılıkla §3.6.5.1.4'teki konum raporu olaylarına dayanıyor (doğrulanmadı: derlemde yalnızca maddenin ilk satırı var, "as requested by the RBC"); madde notu da diyor ki: "gereksinimle ilgisiz bir ara adım". | Denetimi çıkar. |
| ETC-905 | 4 | Duruşta T_CYCRQST dolar → "Override EoA" basılana dek MA Request tekrarı | MANY_TO_MANY | 0/3 | 0/3 | #2 ile aynı madde (§3.8.2.1.5), üstüne ayrıca somut bir duruş ve Override senaryosu. Gereksinim cümlesinde karşılığı yok. | Denetimi çıkar (ya da #2 ile birlikte gereksinim metni genişletilirse tut). |

## Etiket sayıları

| Durum | Sayı | Satırlar |
| --- | --- | --- |
| Eşleşti (kayıp değil) | 5 | 901 #1-3, 903 #3, 905 #1 |
| MANY_TO_MANY | 4 | 904 #1, 905 #2-4 |
| SCENARIO_SPECIFIC | 3 | 902 #1-3 |
| CORPUS_GAP | 1 | 903 #1 |
| JUDGE_ERROR | 1 | 904 #2 (tartışmalı) |
| WRITER_MISS | 1 | 903 #2 (güven orta-düşük) |
| **Kayıp toplamı** | **10** | |

## Değerlendirme ve aşama 5 önerileri

**Sinyal mi, yapay kayıp mı?** On kaybın yalnızca biri (%10) gerçek yazar sinyali, o da orta-düşük güvenle ve tek bir üretime dayanarak: 903 #2. Kalan dokuzu yapay kayıptır.

- Dördü denetimin gereksinim dışı madde sınamasından geliyor (MANY_TO_MANY).
- Üçü somut senaryo ya da gözlem kanalından geliyor (SCENARIO_SPECIFIC).
- Biri yalnızca JRU kaydı olan bir uyaran adımı (CORPUS_GAP).
- Biri hakem hatası (JUDGE_ERROR).

MANY_TO_MANY ve CORPUS_GAP satırları çıkarılırsa geriye 10 denetim kalır. Bunların 5'i bugün de eşleşiyor. Davranış düzeyinde yeniden yazımın etkisi şöyle tahmin ediliyor:

- 904 #2 ve 902 #1 büyük olasılıkla eşleşir.
- 902 #2 belirsiz kalır: r2'de bile 1/3 eşleşti ve "taken into account" gözlemlenebilir değil.
- 902 #3, "iki yön geçerli radyo bilgisi uygulanır" diye yazılırsa üretilen testlerde karşılığı yok; o zaman gerçek bir yazar kaçırmasına dönüşür.

Bu durumda belgeli ERTMS recall'u 0,40-0,47'den yaklaşık 0,7-0,8'e çıkar. Gerçek sinyal bugün 1/10, denetimler yeniden yazıldıktan sonra 2-3/10 olabilir. Bu tahmin aynı 10 maddeye bakılarak yapıldı ve doğrulanmadı.

İkincil bir yazar zaafı da 902'de görülüyor: bazı beklenen sonuçlar gözlemlenemez ("taken into account"), ve radyo ile iki yön birleşimi atlanmış. Bu zaaflar etiketi değiştirmiyor ama yazar istemi için not edilmeli.

**Derleme eklenecek belgeler**, kurtardıkları satırlarla:

1. **SUBSET-026-8 (mesaj listesi) ve SUBSET-026-7 §7.4 (paket listesi).** Mesaj 15, 24, 34, 132 ve 136'yı, paket 5 ve 27'yi adlandırır. Yazarın somut senaryo seçmesine yardım eder (902 #1-3, 904 #2), ama tek başına hiçbir satırı kararlı biçimde çevirmez. Ucuzdur ve aynı belge ailesindendir.
2. **SRS'ten eksik maddeler:**
   - §3.10.2: koşullu acil durdurmanın etkisi (902 #1 ve #3);
   - TAF maddesi: 902 #2;
   - §4.8: geçiş tamponu (903 #1 ve #3);
   - §3.6.5.1.4: duruşta konum raporu (madde numarası doğrulanmadı). Bu madde yalnızca 905 #3 tutulacaksa gerekir.
3. **SUBSET-027 (JRU) ve ERA DMI belgesi (belge kimliği ERA_ERTMS_015560 olarak hatırlanıyor, doğrulanmadı).** Yalnızca denetimler JRU ya da DMI'dan başka sonuç taşımıyorsa gerekir. Bu belgelerle kararlı biçimde kurtulacak bir satır görünmüyor: kanal farkını r2 zaten tolere ediyor (902 #1 bu belgeler olmadan r2'de 3/3 eşleşti), kalan kayıplar ise kanaldan değil senaryodan ya da kapsamdan geliyor. Önerim: bu iki belgeyi eklemek yerine denetimden JRU ve DMI kısmını ayırmak. Bu belgeler de ERTMS ailesindendir; kullanıcı onayının kapsamı onlar için ayrıca teyit edilmeli.

**Somut öneriler:**

1. **Denetim cümlesi davranış çekirdeğiyle yazılsın.** Beklenen sonuçta önce arayüzden bağımsız bir davranış cümlesi dursun ("rapor BG1'e atıf yapar", "bilgi yok sayılır, tren tepki vermez"). RTM, JRU ve DMI ayrıntısı ayrı bir `channel` notuna gitsin.
   - Bu çalışmadaki gözlem bunu destekliyor, ama kesin değil. Davranış çekirdeği RTM mesajında açıkça duran denetimler (901 #1-3, 905 #1) r1'de her örnekte 3/3 eşleşti. DMI ya da JRU sonucu taşıyanlar çoğunlukla 0-1/3 kaldı (902 #2-3, 904 #2).
   - İki karşı örnek var. 903 #3'ün beklenen sonucu yalnızca DMI ve JRU, ama açıklayıcı yorumu ("FRBG becomes the new SOLR since the clause 3.7.3.1 m) is applied before...") sayesinde 3/3 eşleşti. 902 #1 ise bir davranış yorumu taşıyor ("The train does not react"), buna rağmen r1'de 0/3 kaldı; bu satırın kaybı somut senaryodan geliyor.
   - Beklenen sonucu yalnızca uyaranın JRU kaydı olan adımlar ön koşula taşınsın (903 #1, 904 #1).
2. **Değerlendirme birimi adım düzeyinde atansın.** Paket tanımındaki iki seçenek ("tek maddeli test vakası" ya da "'Based on' listesi küme içinde") bu örnekte yetmezdi. TC14'ün ve TC7'nin "Based on" listesi tamamen gereksinimin içinde, buna rağmen 904 #1 ve 905 #2-4 başka davranış sınıyor. Önerilen yol şu:
   - Her denetim, sınadığı SRS maddesiyle etiketlensin (`verifies: [...]`).
   - Bu etiketlemeyi Claude yaparsa `reference_origin` bunu göstersin.
   - Gereksinim cümlesinin ve andığı maddenin dışında kalan denetimler ya çıkarılsın ya da ilgili maddeler gereksinim metnine katılıp madde grubu olarak değerlendirilsin.
   - Böylece yazar, rubriğin `invented` cezasıyla karşılaşmadan bu denetimleri karşılayabilir.
3. **Hakem ve yazar gürültüsü ayrılsın.**
   - Aşama 5'te her madde için en az üç bağımsız üretim alınsın; bugünkü üç örnek yalnızca hakem tekrarıdır.
   - Hakem kararı çoğunluk oyuyla verilsin. 904 #2 gibi bölünen satırlar ayrıca listelensin.
   - Destek parçaları denetim başına bağlansın. Derlemde karşılığı olmayan kısım "derlemde yok" diye işaretlensin ve bu denetimler ayrı raporlansın.
