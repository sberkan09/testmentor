# Vatandaş Başvuru Portalı (VBP) — Kavramsal İşletim Belgesi

| Alan | Değer |
|---|---|
| Belge No | KHGM-VBP-KIB-001 |
| Sürüm | 1.0 |
| Tarih | 2026-11-20 |
| Kurum | Kamu Hizmetleri Genel Müdürlüğü (KHGM), Başvuru Hizmetleri Dairesi Başkanlığı |
| Sınıf | Hizmete Özel |
| İlgili belgeler | KHGM-VBP-PYP-001 Proje Yönetim Planı, KHGM-VBP-YTB-001 Yazılım Tasarım Belgesi |

**Revizyon tablosu**

| Sürüm | Tarih | Açıklama | Hazırlayan / Onaylayan |
|---|---|---|---|
| 0.1 | 2026-09-18 | Keşif aşaması ara bulgularından ilk taslak | Hizmet Tasarımcısı |
| 0.9 | 2026-11-06 | İl müdürlükleri ve çağrı merkezi görüşleri; güvence düzeyi analizi eklendi | Ürün Yöneticisi, Güvenlik Mimarı |
| 1.0 | 2026-11-20 | Proje Yönlendirme Kurulu onayı | Hizmet Sahibi |

## 1. Giriş

Bu belge, Kamu Hizmetleri Genel Müdürlüğü'nün (KHGM) Vatandaş Başvuru Portalı'nın (VBP) işletim kavramını tanımlar: hizmetin neden var olduğunu, kimlerin hangi amaçla kullandığını, hangi kanallardan ve hangi hacimde çalışacağını, nasıl destekleneceğini, hangi dış sistemlere bağlı olduğunu ve her kullanıcı grubu için hangi kimlik güvence düzeylerinin seçildiğini. Teknik çözüm KHGM-VBP-YTB-001'de, proje organizasyonu ve takvim KHGM-VBP-PYP-001'de anlatılır. Bu belgede geçen sayısal parametreler (zaman aşımları, sınırlar, saklama süreleri) KHGM-VBP-YTB-001 Bölüm 14'teki parametre tablosundan alınmıştır.

## 2. Mevcut durum ve değişikliğin gerekçesi

KHGM bugün izin, ruhsat ve lisans başvurularını üç yoldan alır: il müdürlüklerindeki kabul bürolarına kâğıt dilekçe, kayıtlı elektronik posta ve 2011'de devreye alınan "e-Başvuru" uygulaması. e-Başvuru yalnızca dört hizmet türünü kapsar, ödemeyi desteklemez ve başvuru sahibine durum bilgisi vermez. Keşif aşamasında (Ağustos-Ekim 2026) yapılan 46 kullanıcı görüşmesi, 3 il müdürlüğünde gözlem ve çağrı merkezi kayıtlarının incelenmesi şu sorunları ortaya koymuştur:

- Başvuruların yaklaşık yüzde 38'i eksik belge nedeniyle en az bir kez geri dönmektedir; sahipler eksikliği çoğu zaman telefonla öğrenmektedir.
- Çağrı merkezine gelen aramaların yüzde 41'i "başvurum ne durumda?" sorusudur.
- Harç bankada yatırılıp dekont elle eşleştirildiğinden ödeme mutabakatı ortalama 2 iş günü sürmektedir.
- Ocak ayındaki lisans yenileme döneminde il müdürlüklerinde bekleme süresi 3 saate çıkmaktadır.
- Şirketler adına işlem yapan vekil müşavirler her başvuru için ayrı vekâletname sunmaktadır.
- Yabancı uyruklu şirket temsilcileri e-Devlet kimlik bilgisine sahip olmadıklarından dijital kanalı hiç kullanamamaktadır.

VBP bu sorunları tek bir dijital hizmetle çözmeyi hedefler: başvurunun baştan sona çevrim içi yapılması, eksikliklerin gönderimden önce yakalanması, ödemenin aynı akışta tamamlanması, durumun her an izlenebilmesi ve personelin başvuruları tek bir arka ofis uygulamasında işlemesi.

## 3. Amaç ve başarı ölçütleri

VBP'nin amacı, KHGM'nin izin ve lisans hizmetlerini herkesin kullanabileceği, güvenli ve kâğıtsız bir dijital hizmete dönüştürmektir. Başarı, GOV.UK Service Standard madde 10 yaklaşımıyla aşağıdaki göstergelerle ölçülür ve göstergeler KHGM'nin internet sitesinde üç ayda bir yayımlanır:

| Gösterge | Başlangıç (2026) | Hedef (canlıya geçişten 12 ay sonra) |
|---|---|---|
| Dijital kanal payı | %19 | %70 |
| Başvuruyu başlatıp gönderenlerin oranı (tamamlama) | Ölçülmüyor | %80 |
| Eksik belge nedeniyle iade oranı | %38 | %15 |
| Kullanıcı memnuniyeti (işlem sonu anketi, 5 üzerinden) | Ölçülmüyor | 4,2 |
| İşlem başına maliyet | 212 TL | 95 TL |
| Ortalama sonuçlanma süresi (H-01) | 21 iş günü | 10 iş günü |

## 4. Paydaşlar ve aktörler

| Aktör | Tanım | Erişim yolu | Yaklaşık sayı |
|---|---|---|---|
| Vatandaş | Kendi adına başvuran gerçek kişi | e-Devlet Kapısı | 1,9 milyon kayıtlı hesap (5 yıllık öngörü) |
| Şirket temsilcisi | Şirket adına yetkilendirilmiş çalışan, vekil müşavir ya da yabancı uyruklu yönetici | VBP yerel hesabı (parola ve ikinci faktör) | 38.000 |
| Başvuru Uzmanı | Başvuruyu inceleyen il müdürlüğü personeli | KKS, donanım güvenlik anahtarı | 820 |
| Onay Yetkilisi | Karar önerisini onaylayan şube müdürü ya da il müdürü | KKS, donanım güvenlik anahtarı | 170 |
| Mali İşler Uzmanı | Harç mutabakatı ve iadesi | KKS, donanım güvenlik anahtarı | 60 |
| Yardım Masası Uzmanı | Çağrı merkezi ikinci düzey destek | KKS, donanım güvenlik anahtarı | 70 |
| Birim Yöneticisi ve Denetçi | Atama, raporlama; iç denetim | KKS, donanım güvenlik anahtarı | 18 |
| Sistem Yöneticisi | Altyapı ve uygulama işletimi | PAM, donanım güvenlik anahtarı | 12 |

Kullanıcı olmayan paydaşlar şunlardır: Hizmet Sahibi (Başvuru Hizmetleri Dairesi Başkanı), Bilgi İşlem Dairesi Başkanlığı, KHGM Kurumsal SOME, KHGM Kişisel Verileri Koruma irtibat kişisi, il müdürlükleri, harç tahsilatını yürüten Strateji Geliştirme Daire Başkanlığı, meslek odaları ve engelli hakları dernekleri (kullanıcı araştırmasına katılım), entegrasyon sağlayan kurumlar.

## 5. Hizmet kataloğu

| Kod | Hizmet | Başvuranlar | Harç | Hedef sonuçlanma |
|---|---|---|---|---|
| H-01 | İşyeri Faaliyet İzni | Vatandaş, temsilci | Var | 10 iş günü |
| H-02 | Mesleki Yeterlik Lisansı | Vatandaş | Var | 15 iş günü |
| H-03 | Lisans Yenileme | Vatandaş, temsilci | Var | 3 iş günü |
| H-04 | Geçici Etkinlik İzni | Vatandaş, temsilci | Var | 5 iş günü |
| H-05 | Belge Örneği ve Onaylı Suret Talebi | Vatandaş, temsilci | Var | 2 iş günü |
| H-06 | Bilgi Güncelleme ve Ek Belge Sunma | Vatandaş, temsilci | Yok | 5 iş günü |
| H-07 | Karara İtiraz | Vatandaş, temsilci | Yok | 30 gün |
| H-08 | Harç İadesi | Vatandaş, temsilci | Yok | 15 iş günü |

Ortak işlevler: hesap ve profil yönetimi, şirket temsil yetkisi yönetimi, taslak kaydetme, belge yükleme, harç ödeme, başvuru takibi, bildirim tercihleri, portal gelen kutusu, karar belgesini indirme. Kararlar KBYS'de e-imzalı resmî yazı olarak üretilir ve portalda indirilebilir.

## 6. Kullanım senaryoları

Senaryolar hizmetin nasıl kullanılacağını anlatan işletim öyküleridir; kabul ölçütü ya da test senaryosu değildir.

**S-1 Vatandaşın işyeri izni başvurusu.** Ayşe Hanım, açacağı kırtasiye için İşyeri Faaliyet İzni almak istiyor. Telefonundan portala giriyor ve "e-Devlet ile giriş" düğmesine dokunuyor. e-Devlet'te mobil imza ile kimliğini doğruluyor ve portala dönüyor. Ad, adres ve doğum tarihi MNKS'den otomatik geliyor; Ayşe Hanım yalnızca işyeri adresini ve faaliyet türünü giriyor. Kira sözleşmesini telefon kamerasıyla çekip yüklüyor. Portal belgenin okunabilir olup olmadığını denetliyor ve eksik olan yangın uygunluk belgesini gönderimden önce hatırlatıyor. Ayşe Hanım akşam devam etmek üzere çıkıyor; taslağı kaydediliyor. Ertesi gün başvurusunu tamamlıyor, özet sayfasında yanıtlarını gözden geçiriyor, harcı kartıyla ödüyor ve başvuru numarasını SMS ile alıyor. On gün içinde onay bildirimi geliyor ve karar belgesini portaldan indiriyor.

**S-2 Vekil müşavirin çok şirketli lisans yenilemesi.** Mehmet Bey 14 şirketin vekil müşaviri. Ocak'ın ilk haftasında portala yerel hesabıyla giriyor: parolasını parola yöneticisi dolduruyor, ikinci faktör olarak telefonundaki doğrulayıcı uygulamanın kodunu giriyor. Şirket seçicisinden ilk şirketi seçiyor; portal TSBS'den yetkisinin hâlâ geçerli olduğunu doğruluyor. Önceki yılın bilgileriyle dolu yenileme formunda yalnızca değişen çalışan sayısını güncelliyor ve gönderiyor. Öğle arasında 30 dakikadan uzun ara verince portal oturumunu askıya alıyor; dönüşte yalnızca parolasıyla devam edebiliyor, çünkü oturumun 12 saatlik toplam süresi dolmamış.

**S-3 Eksik belge talebi.** Başvuru Uzmanı Elif Hanım, bir H-01 başvurusundaki kira sözleşmesinin imza sayfasının eksik olduğunu görüyor. Arka ofisten "ek belge iste" işlemini seçip gerekçesini yazıyor. Başvuru sahibi e-posta ve SMS ile bilgilendiriliyor; portalda hangi belgenin neden istendiği açıkça yazıyor. Sahip 15 gün içinde belgeyi yüklemezse başvuru, Hizmet Sahibi'nin belirlediği kurala göre bir hatırlatmanın ardından düşer.

**S-4 Karar ve görevler ayrılığı.** Elif Hanım incelemeyi tamamlayıp "olumlu" karar öneriyor. Öneri, aynı birimin Onay Yetkilisi Hasan Bey'in iş listesine düşüyor. Hasan Bey onaylamadan önce donanım anahtarına dokunup PIN'ini girerek yeniden kimlik doğruluyor. Karar KBYS'de e-imzalı yazıya dönüşüyor ve başvuru sahibine bildiriliyor.

**S-5 Ödeme altyapısı kesintisi.** Lisans yenileme döneminde Kamu Ödeme Altyapısı (KÖA) 40 dakika yanıt vermiyor. Portal, başvuruyu "ödeme bekliyor" durumunda saklıyor ve kullanıcıya ödemeyi 72 saat içinde tamamlayabileceğini söylüyor. KÖA geri geldiğinde kullanıcı bildirimdeki bağlantıyla ödemeyi tamamlıyor; mutabakat işi belirsiz kalan işlemleri kendiliğinden sorguluyor.

**S-6 Temsilcinin telefonunu kaybetmesi.** Yabancı uyruklu temsilci Anna Hanım telefonunu kaybediyor ve doğrulayıcı uygulamasına erişemiyor. Etkinleştirmede yazdırdığı kayıtlı kurtarma kodunu ve e-postasına gönderilen kurtarma kodunu kullanarak hesabını kurtarıyor, yeni parola belirliyor ve yeni telefonuna doğrulayıcıyı bağlıyor. Kayıtlı tüm adreslerine kurtarma bildirimi gidiyor; eski kurtarma kodu geçersiz oluyor ve yenisi veriliyor.

**S-7 Ekran okuyucu kullanan başvuru sahibi.** Görme engelli avukat Kerem Bey, Mesleki Yeterlik Lisansı başvurusunu ekran okuyucu ve klavyeyle yapıyor. Formda bir alanı hatalı girince sayfanın üstündeki hata özeti okunuyor ve bağlantıyla doğrudan ilgili alana gidiyor. Hareketsizlik uyarısı açıldığında kalan süre duyuruluyor ve tek tuşla süreyi uzatıyor.

**S-8 İngilizce arayüz.** Bir yabancı yatırım şirketinin genel müdürü olan temsilci, arayüzü İngilizceye çeviriyor. Form alanları, yardım metinleri ve bildirimler İngilizce; resmî belge adları Türkçe özgün adlarıyla birlikte gösteriliyor. Karar yazısı Türkçe üretiliyor, yanında İngilizce bilgi özeti yer alıyor.

## 7. Kanallar

VBP birincil kanaldır ancak tek kanal değildir; tüm kanallar aynı arka ofis ve aynı veri üzerinde çalışır (GOV.UK Service Standard madde 3).

| Kanal | Kullanım | Not |
|---|---|---|
| Web (masaüstü) | Tüm hizmetler | Türkçe ve İngilizce |
| Mobil web | Tüm hizmetler | Ayrı mobil uygulama yoktur; duyarlı tasarım ve 320 piksel genişliğe kadar yeniden akış |
| İl müdürlüğü yardımlı dijital hizmet | Dijital beceri ya da erişimi olmayanlar | Personel, başvuru sahibinin yanında portalı birlikte kullanır; başvuru sahibinin kendi hesabıyla |
| Çağrı merkezi | Bilgi, durum sorgulama, yönlendirme | Başvuru alınmaz; durum bilgisi kimlik doğrulama sonrası verilir |
| Kâğıt başvuru | Kanunen kâğıt gerektiren istisnalar ve geçiş dönemi | Kabul bürosunda taranarak arka ofise aynı iş akışıyla girer |

Kâğıt kanalı canlıya geçişten 6 ay sonra (2028-08-14) yalnızca istisnai durumlar ve yardımlı hizmet için sürdürülecektir.

## 8. Hacimler ve tepe dönemleri

| Ölçü | Değer |
|---|---|
| Yıllık başvuru | Yaklaşık 480.000 (ilk yıl dijital pay hedefiyle 336.000'i portaldan) |
| Ocak lisans yenileme dönemi (2-31 Ocak) | Yıllık hacmin yaklaşık %22'si |
| Haziran dönem sonu (son iki hafta) | Yıllık hacmin yaklaşık %7'si |
| Tepe eşzamanlı oturum | 9.000 |
| Tepe başvuru gönderimi | Dakikada 45 |
| Tepe istek hızı | Saniyede 650 istek |
| Yüklenen belge | Yılda yaklaşık 2,1 milyon dosya, ortalama 1,4 MB |
| Gönderilen bildirim | Yılda yaklaşık 3,5 milyon SMS ve 4 milyon e-posta |

Kapasite, tepe değerlerin 1,5 katına göre planlanır. Ocak tepe dönemi boyunca yalnızca acil değişiklikler canlıya alınır ve planlı bakım yapılmaz.

## 9. İşletim saatleri ve destek modeli

**İşletim saatleri.** Portal 7 gün 24 saat açıktır; aylık erişilebilirlik hedefi %99,5'tir (GOV.UK Service Standard madde 14). Planlı bakım Pazar 02:00-05:00 arasında yapılır ve en az 3 gün önce portalda duyurulur. Arka ofis personeli hafta içi 08:30-17:30 arasında çalışır; Ocak döneminde il müdürlükleri Cumartesi 09:00-14:00 arasında da açıktır.

**Destek düzeyleri.**

| Düzey | Sağlayan | Kapsam | Saatler |
|---|---|---|---|
| 1. düzey | KHGM Çağrı Merkezi | Bilgi, yönlendirme, durum sorgulama, giriş sorunları | Hafta içi 08:00-20:00; Cumartesi 09:00-17:00; Ocak'ta Pazar 09:00-17:00 |
| 2. düzey | Yardım Masası Uzmanları ve il müdürlüğü yardımlı hizmet | Hesap kurtarma başlatma, başvuru düzeltme talepleri, yardımlı başvuru | Mesai saatleri |
| 3. düzey | Uygulama İşletim Ekibi (KHGM ve yüklenici) | Hata giderme, veri düzeltme, entegrasyon sorunları | 7/24 nöbet (P1 ve P2 için) |
| Güvenlik | KHGM Kurumsal SOME | Güvenlik olayı izleme ve müdahale | 7/24 |

**Olay öncelikleri.**

| Öncelik | Tanım | İlk yanıt | Hedef çözüm |
|---|---|---|---|
| P1 | Hizmet tamamen kullanılamıyor ya da veri ihlali şüphesi | 15 dakika | 4 saat |
| P2 | Bir hizmet türü ya da ödeme kullanılamıyor | 30 dakika | 8 saat |
| P3 | Geçici çözümü olan işlev hatası | 4 iş saati | 5 iş günü |
| P4 | Kozmetik sorun, iyileştirme talebi | 2 iş günü | Sürüm planına göre |

Hizmet durumu, kesinti ve planlı bakım bilgisi ayrı barındırılan bir durum sayfasında yayımlanır. Personel, şüpheli bir güvenlik olayını 1 saat içinde KHGM SOME'ye bildirir.

## 10. Dış arayüzler

| Sistem | Sağlayan | Amaç | Yön | Kritiklik |
|---|---|---|---|---|
| e-Devlet Kapısı | Ulusal e-Devlet işletmecisi | Vatandaş kimlik doğrulaması (OIDC federasyonu) | VBP → IdP → VBP | Yüksek |
| Merkezi Nüfus Kayıt Servisi (MNKS) | Nüfus kayıt idaresi | Kimlik ve adres özniteliklerinin doğrulanması | VBP → MNKS | Yüksek |
| Ticaret Sicil Bilgi Servisi (TSBS) | Ticaret sicili idaresi | Şirket ve temsil yetkisi doğrulaması | VBP → TSBS | Orta |
| Kamu Ödeme Altyapısı (KÖA) | Kamu ödeme hizmet sağlayıcısı | Kartla harç tahsilatı, 3-D Secure, iade | Çift yönlü | Yüksek |
| Bildirim Ağ Geçidi | KHGM (SMS toplayıcı sözleşmesi ve kurumsal e-posta aktarıcısı) | SMS ve e-posta gönderimi | VBP → Ağ geçidi | Orta |
| Kurumsal Belge Yönetim Sistemi (KBYS) | KHGM | Belgelerin arşivlenmesi, e-imzalı karar yazısı | Çift yönlü | Yüksek |
| Kurumsal Kimlik Sağlayıcı (KKS) | KHGM | Personel kimlik doğrulaması | VBP → KKS → VBP | Yüksek |
| Siber Olay Yönetim Sistemi (SIEM) | KHGM SOME | Güvenlik kayıtlarının toplanması ve korelasyonu | VBP → SIEM | Yüksek |
| Çağrı Merkezi CRM | KHGM | Durum sorgulama, kayıt açma | CRM → VBP (salt okuma) | Orta |

Tüm dış arayüzler şifreli kanal ve karşılıklı kimlik doğrulama kullanır; her çağrının girdi parametreleri ve sonuçları kayıt altına alınır. Her arayüz için kesinti davranışı KHGM-VBP-YTB-001 Bölüm 11'de tanımlanmıştır.

## 11. Güvence düzeyi kararları

Güvence düzeyleri NIST SP 800-63-4 §3'teki dijital kimlik risk yönetimi (DIRM) süreciyle belirlenmiştir. Sonuçlar, telafi edici ve tamamlayıcı kontrollerle birlikte VBP Dijital Kimlik Kabul Beyanı'na (DIAS, §3.4.4) işlenmiştir.

### 11.1 Hizmetin tanımı ve etkilenen taraflar

Çevrim içi hizmet; başvuru oluşturma, kişisel veri ve belge görüntüleme, harç ödeme ve iade talebi, şirket adına işlem ve personel tarafında karar verme işlevlerini kapsar (§3.1). Etkilenen taraflar: başvuru sahipleri, adına işlem yapılan şirketler, KHGM, verilen izne güvenen üçüncü kişiler (komşular, etkinlik katılımcıları) ve kamu.

### 11.2 Etki değerlendirmesi

Etki kategorileri §3.2.1'deki beş zorunlu kategoridir. Birleştirme yöntemi olarak en yüksek değer (high-water mark) seçilmiştir; KHGM bu yöntemi tüm çevrim içi hizmetlerinde tutarlı uygular (§3.2.4).

| Kategori | Vatandaş | Şirket temsilcisi | Personel |
|---|---|---|---|
| Görev ifasının bozulması | Düşük | Düşük | Orta |
| Güven ve itibar kaybı | Orta | Orta | Yüksek |
| Bilgiye yetkisiz erişim | Orta (kendi verisi, adres, belgeler) | Orta (şirket ve çalışan verisi) | Yüksek (binlerce kişinin verisi, özel nitelikli veri dahil) |
| Mali kayıp veya yükümlülük | Orta (harç, iade IBAN'ının değiştirilmesi) | Orta | Yüksek (haksız izin, toplu iade) |
| Can güvenliği, sağlık, çevre | Düşük | Düşük | Orta (güvenlik koşulları sağlanmamış etkinliğe izin) |
| **Birleşik etki** | **Orta** | **Orta** | **Yüksek** |

### 11.3 Başlangıç düzeyleri ve uyarlama

| Kullanıcı grubu | Başlangıç (§3.3.3) | Uygulanan | Gerekçe |
|---|---|---|---|
| Vatandaş | IAL2, AAL2, FAL2 | IAL2, AAL2, FAL2 | Orta etki. Kimlik kanıtlama ve kimlik doğrulama e-Devlet tarafından yapılır; VBP, e-Devlet'in güvence beyanını güven anlaşması yoluyla kendi DIAS'ına dahil eder (§3.4.4). AAL2'nin altında doğrulanmış girişler sınırlı kipte açılır. |
| Şirket temsilcisi | IAL2, AAL2 | IAL2, AAL2; federasyon yok | Orta etki. Kimlik bir kez e-Devlet ya da il müdürlüğünde yüz yüze kanıtlanır; doğrulama VBP'nin yerel hesabında parola ve ikinci faktörle yapılır. Tamamlayıcı kontrol olarak oltalamaya dirençli geçiş anahtarı seçeneği sunulur. SMS kısıtlı doğrulayıcı olarak, riskler kullanıcıya bildirilerek kabul edilmiştir (800-63B-4 §3.2.9). |
| Personel | IAL3, AAL3, FAL2 veya FAL3 | IAL2, AAL3, FAL2 | Yüksek etki. IAL3 yerine IAL2 seçilmiş ve telafi edici kontrol olarak işe girişte İnsan Kaynakları'nda yüz yüze kimlik kanıtlaması ile kamu görevlisi güvenlik soruşturması kullanılmıştır (§3.4.2). AAL3 doğrudan uygulanır (donanım güvenlik anahtarı ve PIN). FAL3 yerine FAL2 seçilmiştir; §3.3.3.3'te sayılan değerlendirme etkenlerinden kimlik sağlayıcının (KKS) kurum sınırı içinde bulunması ve personel doğrulayıcısının zaten oltalamaya dirençli AAL3 olması bu kararı destekler. |
| Sistem yöneticisi | IAL3, AAL3 | IAL2, AAL3 | Personelle aynı gerekçe; ek olarak ayrı yönetici hesabı, sabit kaynak IP ve oturum kaydı. |

### 11.4 Kalan riskler

DIAS'ta kayıtlı başlıca kalan riskler şunlardır: SMS'in kısıtlı doğrulayıcı olarak kullanılması; temsilci parolalarına 365 günlük geçerlilik süresi uygulanması nedeniyle NIST SP 800-63B-4 §3.1.1.2(6)'dan sapılması (Bilgi ve İletişim Güvenliği Rehberi 3.2.1.8 gereği); e-Devlet'in kimlik doğrulama bağlamını bildirmediği durumlarda sınırlı kipe düşülmesi. DIAS yılda bir ve güvence düzeyini etkileyen her değişiklikte gözden geçirilir (§3.5).

## 12. Kısıtlar ve varsayımlar

- Kurumsal kritik veriler kamuya açık bulut hizmetlerinde tutulmaz; VBP KHGM'nin Ankara veri merkezinde ve İstanbul Felaket Kurtarma Merkezi'nde barındırılır.
- Geliştirme ve test ortamlarında gerçek kişisel veri kullanılmaz.
- e-Devlet, MNKS, TSBS ve KÖA ile ilişkiler protokol ve güven anlaşmalarına dayanır; bu anlaşmaların imzası Alfa aşamasının bitişine kadar tamamlanacaktır.
- Erişilebilirlik hedefi WCAG 2.2 AA'dır ve hem portal hem arka ofis için geçerlidir.
- Hizmet Türkçe ve İngilizce sunulur; resmî karar yazıları Türkçedir.
