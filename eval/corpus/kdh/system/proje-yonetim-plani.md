# Vatandaş Başvuru Portalı (VBP) — Proje Yönetim Planı

| Alan | Değer |
|---|---|
| Belge No | KHGM-VBP-PYP-001 |
| Sürüm | 1.0 |
| Tarih | 2026-11-20 |
| Kurum | Kamu Hizmetleri Genel Müdürlüğü (KHGM), Bilgi İşlem Dairesi Başkanlığı |
| Sınıf | Hizmete Özel |
| İlgili belgeler | KHGM-VBP-KIB-001 Kavramsal İşletim Belgesi, KHGM-VBP-YTB-001 Yazılım Tasarım Belgesi |

**Revizyon tablosu**

| Sürüm | Tarih | Açıklama | Hazırlayan / Onaylayan |
|---|---|---|---|
| 0.1 | 2026-09-18 | Keşif ara bulgularından ilk taslak | Proje Yöneticisi |
| 0.9 | 2026-11-06 | Bütçe, risk kaydı ve tedarik planı güncellendi | Proje Yöneticisi, Strateji Geliştirme Daire Başkanlığı |
| 1.0 | 2026-11-20 | Proje Yönlendirme Kurulu onayı (2026/4 sayılı toplantı) | Proje Sponsoru |

## 1. Giriş

Bu plan, Vatandaş Başvuru Portalı (VBP) projesinin nasıl yönetileceğini tanımlar: kapsam, aşamalar ve kilometre taşları, organizasyon ve roller, iletişim, bütçe, risk yönetimi, kalite ve test yaklaşımı, yapılandırma ve değişiklik yönetimi, tedarikçi yönetimi, eğitim ve takvim. Hizmetin işletim kavramı KHGM-VBP-KIB-001'de, teknik tasarım KHGM-VBP-YTB-001'de yer alır. Plan, Proje Yönlendirme Kurulu'nun onayıyla yürürlüğe girer ve her aşama sonunda gözden geçirilir.

## 2. Kapsam

### 2.1 Kapsamda olanlar

- Vatandaş ve şirket temsilcisi portalı (Türkçe ve İngilizce, masaüstü ve mobil web), KHGM-VBP-KIB-001'deki H-01 ile H-08 arasındaki sekiz hizmet.
- Personel arka ofis uygulaması: iş listesi, atama, inceleme, karar, ödeme mutabakatı, raporlama.
- e-Devlet Kapısı, MNKS, TSBS, KÖA, Bildirim Ağ Geçidi, KBYS, KKS ve SIEM entegrasyonları.
- Eski e-Başvuru uygulamasındaki açık başvuruların ve son 5 yılın kapanmış dosya üst verisinin taşınması.
- Personel için 2.300 adet FIDO2 donanım güvenlik anahtarının (her personele iki adet) temini ve dağıtımı.
- Birincil veri merkezi ve Felaket Kurtarma Merkezi'nde altyapı kurulumu.
- Personel, çağrı merkezi ve il müdürlüğü yardımlı hizmet görevlilerinin eğitimi; kullanıcı rehberleri.
- Erişilebilirlik beyanı, kişisel veri aydınlatma metinleri, hizmet performans göstergelerinin yayımlanması.

### 2.2 Kapsam dışında olanlar

- Yerel mobil uygulama (iOS ve Android); 2028 sonrasında kullanım verisine göre değerlendirilecektir.
- KBYS'nin kendisindeki değişiklikler (yalnızca entegrasyon arayüzü kapsamdadır).
- Harç tarifesi ve hizmet mevzuatındaki değişiklikler.
- Kurum iş istasyonlarının işletim sistemi yapılandırması ve ağ altyapısının yenilenmesi.
- Diğer KHGM hizmetlerinin (denetim, ceza işlemleri) portala alınması.

## 3. Yaşam döngüsü, aşamalar ve kilometre taşları

Proje, KHGM'nin keşif, alfa, beta ve canlı aşamalarından oluşan çevik yaşam döngüsüyle yürütülür; çevik çalışma ve sık yineleme ilkeleri GOV.UK Service Standard madde 7 ve 8'e dayanır. Her aşama iki haftalık sprintlerden oluşur. Bir aşamadan diğerine geçiş, KHGM Hizmet Değerlendirme Kurulu'nun aşama değerlendirmesinden sonra Proje Yönlendirme Kurulu kararıyla olur.

| Aşama | Tarih | Amaç | Başlıca çıktılar |
|---|---|---|---|
| Keşif | 2026-08-03 – 2026-10-30 (tamamlandı) | Kullanıcı ihtiyaçlarını ve mevcut süreci anlamak | Kullanıcı araştırması raporu, süreç haritaları, KIB taslağı |
| Alfa | 2026-12-07 – 2027-03-26 | Riskli varsayımları prototiplerle denemek | Tıklanabilir prototipler, mimari kararlar, güven anlaşması taslakları, DIAS ilk sürümü |
| Özel beta | 2027-04-05 – 2027-08-27 | Gerçek kullanıcılarla sınırlı canlı hizmet | 3 pilot il (Ankara, Eskişehir, Kayseri), H-01, H-03, H-05 |
| Kamuya açık beta | 2027-09-13 – 2028-02-11 | Tüm iller ve tüm hizmetler; eski sistemle paralel | Tüm hizmetler, ölçeklendirme, Ocak 2028 tepesinde isteğe bağlı kullanım |
| Canlı | 2028-02-14'ten itibaren | Birincil kanal | Eski e-Başvuru'nun yeni başvuruya kapatılması |
| Eski sistemin kapatılması | 2028-06-30 | Veri taşıma sonrası kapatma | Kapatma tutanağı, arşiv |

Canlıya geçiş, Ocak 2028 lisans yenileme tepesinin bilinçli olarak ardına konmuştur; Ocak 2028'de eski sistem birincil kanal olarak çalışır, VBP kamuya açık beta olarak isteğe bağlı sunulur.

| No | Kilometre taşı | Tarih |
|---|---|---|
| M0 | Keşif aşaması değerlendirmesi | 2026-10-30 (tamamlandı) |
| M1 | Proje Yönetim Planı ve KIB onayı | 2026-11-20 |
| M2 | Yüklenici sözleşmesinin imzası | 2026-12-04 |
| M3 | Alfa değerlendirmesi; e-Devlet, MNKS, KÖA güven anlaşmalarının imzası | 2027-03-26 |
| M4 | Özel beta başlangıcı (3 pilot il) | 2027-04-05 |
| M5 | Bağımsız sızma testi ve erişilebilirlik değerlendirmesi tamam (beta öncesi) | 2027-08-20 |
| M6 | Kamuya açık beta başlangıcı | 2027-09-13 |
| M7 | FKM tatbikatı ve yük testi raporu | 2027-11-26 |
| M8 | Canlı değerlendirmesi ve canlıya geçiş | 2028-02-14 |
| M9 | Eski sistemin kapatılması ve proje kapanış raporu | 2028-06-30 |

## 4. Organizasyon ve roller

### 4.1 Yönetişim

- **Proje Sponsoru:** KHGM Genel Müdür Yardımcısı (Hizmetlerden Sorumlu). Bütçe ve kapsamın son onay mercii.
- **Proje Yönlendirme Kurulu:** Sponsor (başkan), Başvuru Hizmetleri Dairesi Başkanı, Bilgi İşlem Dairesi Başkanı, Strateji Geliştirme Daire Başkanı, iki il müdürü (dönüşümlü), Bilgi Güvenliği Yöneticisi. Ayda bir toplanır.
- **Hizmet Değerlendirme Kurulu:** Proje ekibi dışından kullanıcı araştırması, teknoloji, erişilebilirlik ve güvenlik uzmanlarından oluşur; aşama geçişlerinde hizmeti değerlendirir.

### 4.2 Çok disiplinli ekip

Ekip, GOV.UK Service Standard madde 6 gereği hizmetin tamamından sorumlu, kalıcı ve çok disiplinlidir. KHGM personeli ürün ve hizmet kararlarını, yüklenici ekibi ağırlıklı olarak geliştirmeyi üstlenir.

| Rol | Sağlayan | Kişi sayısı | Sorumluluk |
|---|---|---|---|
| Hizmet Sahibi | KHGM (Başvuru Hizmetleri Dairesi Başkanı) | 1 | Hizmetin sonuçlarından ve politika uyumundan hesap verir |
| Proje Yöneticisi | KHGM Bilgi İşlem | 1 | Plan, bütçe, risk, raporlama, tedarikçi koordinasyonu |
| Ürün Yöneticisi | KHGM | 1 | İş listesi önceliklendirme, kapsam kararları |
| Teslimat Yöneticisi | Yüklenici | 1 | Sprint yönetimi, engellerin kaldırılması |
| Kullanıcı Araştırmacısı | KHGM ve yüklenici | 2 | Araştırma planı, görüşmeler, kullanılabilirlik oturumları |
| Hizmet Tasarımcısı ve Etkileşim Tasarımcısı | Yüklenici | 2 | Uçtan uca akış, ekran tasarımı |
| İçerik Tasarımcısı | KHGM | 2 | Türkçe ve İngilizce içerik, sade dil, bildirim metinleri |
| Erişilebilirlik Uzmanı | KHGM | 1 | WCAG 2.2 AA uyumu, yardımcı teknoloji araştırmaları |
| Teknik Mimar | KHGM | 1 | Mimari kararlar, entegrasyon tasarımı |
| Güvenlik Mimarı | KHGM | 1 | Kimlik ve güvenlik tasarımı, DIAS |
| Yazılım Geliştiriciler | Yüklenici | 9 | Ön yüz, arka uç, entegrasyon |
| Test Yöneticisi ve Test Mühendisleri | Yüklenici (yönetici KHGM) | 1 + 3 | Test stratejisi ve yürütme |
| DevOps ve Platform Mühendisleri | KHGM ve yüklenici | 3 | Ortamlar, sürekli teslim, izleme |
| Veri Taşıma Uzmanı | Yüklenici | 1 | e-Başvuru verisinin taşınması |
| İş Analistleri (il müdürlüğü uzmanları) | KHGM | 3 (yarı zamanlı) | Mevzuat ve süreç bilgisi |
| KVKK irtibat kişisi | KHGM Hukuk Müşavirliği | 1 (yarı zamanlı) | Aydınlatma, envanter, saklama-imha uyumu |
| Bilgi Güvenliği Yöneticisi ve SOME temsilcisi | KHGM | 1 + 1 (yarı zamanlı) | Rehber uyumu, olay yönetimi entegrasyonu |

Ekip Ankara'daki Genel Müdürlük binasının 4. katında ortak çalışma alanında çalışır; hafta içi iki gün uzaktan çalışma, KHGM uzaktan çalışma yönergesine göre serbesttir.

## 5. İletişim planı

| İletişim | Sıklık | Katılımcılar | Çıktı |
|---|---|---|---|
| Günlük kısa toplantı | Her iş günü 09:30, 15 dakika | Çekirdek ekip | Engeller listesi |
| Sprint planlama ve sprint gösterimi | İki haftada bir | Ekip, Hizmet Sahibi, ilgilenen paydaşlar | Sprint hedefi, gösterim kaydı |
| Sprint geriye bakış | İki haftada bir | Ekip | İyileştirme eylemleri |
| Haftalık durum raporu | Her Cuma | Proje Yöneticisi → Sponsor, daire başkanları | Kırmızı-sarı-yeşil durum, riskler, harcama |
| Proje Yönlendirme Kurulu | Ayda bir | Kurul üyeleri | Karar tutanağı |
| İl müdürlükleri bilgilendirme | Ayda bir çevrim içi oturum | İl müdür yardımcıları, kabul bürosu sorumluları | Soru-cevap kaydı, duyuru |
| Çağrı merkezi bilgilendirmesi | Her sürümden önce | Çağrı merkezi ekip liderleri | Sık sorulan sorular güncellemesi |
| Meslek odaları ve engelli hakları dernekleri | Üç ayda bir | Dernek ve oda temsilcileri | Geri bildirim raporu |
| Kamuoyu duyuruları | Beta ve canlı geçişlerinde | Basın ve Halkla İlişkiler Müşavirliği | Basın bülteni, sosyal medya içeriği |
| Hizmet performans verisi | Üç ayda bir | Kamuya açık | Yayımlanmış gösterge panosu |

Proje belgeleri KHGM ortak doküman yönetim alanında tutulur; iş listesi ve hata kayıtları proje iş takip aracındadır. Yüklenici ile resmî yazışmalar KBYS üzerinden yapılır.

## 6. Bütçe

Toplam bütçe 64,8 milyon TL'dir (KDV hariç; 2026 fiyatlarıyla). Bütçe, 2026 ve 2027 yatırım programındaki "Dijital Kamu Hizmetleri Dönüşümü" projesinden karşılanır.

| Kalem | Tutar (milyon TL) |
|---|---|
| Yazılım geliştirme hizmet alımı (yüklenici, 19 ay) | 31,4 |
| Sunucu, depolama ve ağ donanımı (birincil merkez ve FKM) | 9,6 |
| Yazılım lisansları ve destek (3 yıl) | 4,2 |
| FIDO2 donanım güvenlik anahtarları (2.300 adet) | 1,9 |
| Bağımsız sızma testi ve erişilebilirlik değerlendirmesi | 1,6 |
| SMS gönderim kapasitesi (ilk 12 ay) | 2,1 |
| Kullanıcı araştırması ve katılımcı ödenekleri | 0,8 |
| Eğitim ve iletişim | 1,5 |
| KHGM personel maliyeti payı (proje süresince) | 5,8 |
| Yedek (risk payı, %10) | 5,9 |
| **Toplam** | **64,8** |

Yedek ödenek yalnızca Yönlendirme Kurulu kararıyla kullanılır. Harcamalar aylık olarak Strateji Geliştirme Daire Başkanlığı'na raporlanır; sapma yüzde 5'i aşarsa Kurul olağanüstü toplanır.

## 7. Risk kaydı

Olasılık ve etki 1 (çok düşük) ile 5 (çok yüksek) arasında puanlanır; skor çarpımdır. Risk kaydı iki haftada bir güncellenir; 15 ve üzeri skorlu riskler Yönlendirme Kurulu gündemine alınır.

| No | Risk | O | E | Skor | Önlem | Sahip |
|---|---|---|---|---|---|---|
| R-01 | e-Devlet güven anlaşmasının gecikmesi ya da `acr` bilgisinin sağlanmaması | 3 | 5 | 15 | Alfa'nın ilk ayında resmî başvuru; sınırlı kip tasarımı; haftalık takip | Teknik Mimar |
| R-02 | Ocak 2028 tepesinde kapasite yetersizliği | 2 | 5 | 10 | Eski sistemin paralel çalışması; tepe değerin 1,5 katında yük testi; Ocak'ta değişiklik dondurma | Platform Lideri |
| R-03 | Yüklenicide kilit personel değişimi | 3 | 4 | 12 | Sözleşmede kilit personel ve değişiklik onayı maddesi; eşli çalışma; belgelenmiş kod | Proje Yöneticisi |
| R-04 | Mevzuat değişikliğinin hizmet kurallarını değiştirmesi | 3 | 3 | 9 | Kuralların yapılandırılabilir iş kuralı motorunda tutulması; Hukuk Müşavirliği ile aylık görüşme | Hizmet Sahibi |
| R-05 | Eski sistem verisinin kalitesinin düşük olması | 4 | 3 | 12 | Alfa'da veri profilleme; temizleme kuralları; il müdürlüklerinin onayı | Veri Taşıma Uzmanı |
| R-06 | Donanım güvenlik anahtarı teslimatının gecikmesi | 2 | 4 | 8 | Siparişin Ocak 2027'de verilmesi; pilot iller için öncelikli teslimat | Proje Yöneticisi |
| R-07 | Personelin yeni iş akışına direnci | 3 | 3 | 9 | İl müdürlüklerinden "dijital elçiler"; erken katılım; yerinde eğitim | Hizmet Sahibi |
| R-08 | SMS maliyetinin öngörüyü aşması | 3 | 2 | 6 | TOTP ve geçiş anahtarının teşviki; gönderim sınırları; aylık maliyet izleme | Ürün Yöneticisi |
| R-09 | Erişilebilirlik bulgularının beta öncesi kapanmaması | 2 | 4 | 8 | Bileşen kütüphanesinde erken uyum; her sprintte uzman incelemesi | Erişilebilirlik Uzmanı |
| R-10 | Kritik güvenlik açığının beta sırasında bulunması | 2 | 5 | 10 | Sürekli güvenlik taraması; SOME izleme; acil değişiklik süreci | Güvenlik Mimarı |
| R-11 | KÖA test ortamının erişilebilir olmaması | 3 | 3 | 9 | KÖA ile protokolde test ortamı taahhüdü; geçici sanal servis | Teknik Mimar |
| R-12 | Bütçe ödeneğinin 2027'de kısılması | 2 | 4 | 8 | Kapsamın önceliklendirilmesi; H-07 ve H-08'in sonraya bırakılabilir olması | Proje Sponsoru |

## 8. Kalite ve test yaklaşımı

### 8.1 Kalite hedefleri

Kalite; kullanıcı ihtiyaçlarının karşılanması, KHGM-VBP-YTB-001'de tanımlanan güvenlik ve erişilebilirlik gereksinimlerine uyum, güvenilir işletim (aylık %99,5 erişilebilirlik) ve sürdürülebilir kod tabanı olarak tanımlanır. Kalite güvencesi otomatik araçlara bırakılmaz; test faaliyetleri hizmet ekibinin gözetiminde yürütülür ve canlıya olabildiğince benzer bir ortamda yapılır (GOV.UK Service Standard madde 14). Bu bölüm genel yaklaşımı tanımlar; ayrıntılı test planları ve test senaryoları Test Yöneticisi tarafından ayrı belgelerde hazırlanır.

### 8.2 Test seviyeleri

| Seviye | Amaç | Sorumlu |
|---|---|---|
| Birim ve bileşen testi | Kodun tek başına doğru çalışması | Geliştiriciler |
| Entegrasyon testi | Hizmetler arası ve dış sistem arayüzlerinin uyumu | Geliştiriciler ve test mühendisleri |
| Sistem testi | Uçtan uca iş akışlarının gereksinimlere uygunluğu | Test ekibi |
| Güvenlik testi | Statik ve dinamik analiz, bağımlılık taraması, bağımsız sızma testi (Rehber 3.1.11, 3.2.6) | Güvenlik Mimarı, bağımsız firma |
| Erişilebilirlik değerlendirmesi | Otomatik tarama, uzman incelemesi ve yardımcı teknoloji kullanıcılarıyla araştırma | Erişilebilirlik Uzmanı, bağımsız firma |
| Performans testi | Tepe yük ve dayanıklılık | Platform ekibi |
| Kullanıcı kabul testi | İş birimlerinin hizmeti kabulü | Hizmet Sahibi ve il müdürlüğü temsilcileri |
| Operasyonel kabul | Yedekten dönüş, FKM geçişi, izleme ve alarm, işletim kılavuzları | Bilgi İşlem işletim ekibi |

Sızma testi, Rehber 3.1.11 gereği anonim kullanıcı, vatandaş, temsilci ve personel gibi farklı yetki profilleriyle yapılır; test firmasından gizlilik taahhüdü alınır.

### 8.3 Test ortamları

| Ortam | Amaç | Veri | Dış sistemler |
|---|---|---|---|
| GEL (geliştirme) | Geliştirici doğrulaması | Sentetik | Sanal servisler |
| TEST | Entegrasyon ve sistem testi | Sentetik | Sanal servisler ve sağlayıcıların test ortamları |
| ÖNCANLI | Kabul, performans, güvenlik ve erişilebilirlik değerlendirmesi | Sentetik, canlı hacmine ölçeklenmiş | e-Devlet, MNKS, TSBS ve KÖA test ortamları |
| CANLI | Üretim | Gerçek | Gerçek |

Gerçek kişisel veri hiçbir canlı dışı ortamda kullanılmaz (Rehber 3.2.6.2); ÖNCANLI ortamı yapılandırma açısından canlının kopyasıdır ve aynı altyapı kodundan üretilir.

### 8.4 Genel giriş ve çıkış ölçütleri

Her test seviyesine giriş için; test edilecek yapılandırma kaleminin sürüm etiketiyle tanımlanmış olması, ortamın hazır ve izlenebilir olması, bir önceki seviyenin çıkış ölçütlerinin karşılanmış olması ve test verisinin hazırlanmış olması aranır. Bir seviyeden çıkış için; planlanan kapsamın yürütülmüş ve gereksinim izlenebilirlik matrisinde raporlanmış olması, açık kritik hata bulunmaması, yüksek önemli hatalar için Hizmet Sahibi'nin onayladığı bir eylem planının bulunması ve test özet raporunun yayımlanmış olması aranır. Beta ve canlı aşamalarına geçişte ayrıca bağımsız sızma testi ve erişilebilirlik değerlendirmesinde kritik bulgu kalmamış olması gerekir.

### 8.5 Hata yönetimi

Hatalar iş takip aracında önem derecesiyle (kritik, yüksek, orta, düşük) kaydedilir. Kritik hatalar aynı gün, yüksek hatalar sprint içinde ele alınır. Güvenlik açıkları yalnızca yetkili ekip üyelerince görülebilen ayrı bir kayıt alanında tutulur.

## 9. Yapılandırma ve değişiklik yönetimi

**Yapılandırma kalemleri.** Kaynak kod, altyapı kodu, veri tabanı geçiş betikleri, yapılandırma dosyaları, yetki matrisi politika dosyası, içerik ve çeviri dosyaları, tasarım bileşen kütüphanesi ve bu belgeler yapılandırma kalemidir. Tümü KHGM bünyesinde barındırılan sürüm denetim sisteminde tutulur (Rehber 3.2.4, "Açık Kaynak Kod Tabanının Kurum Bünyesinde Tutulması"); kaynak kodun mülkiyeti KHGM'ye aittir. Gizli anahtarlar ve parolalar sürüm deposunda değil, gizli anahtar kasasında tutulur (Rehber 3.2.1.7).

**Dallanma ve sürüm.** Ana dal tabanlı geliştirme uygulanır; her değişiklik en az bir başka geliştiricinin incelemesinden ve otomatik derleme hattından geçer. Sürümler anlamsal sürüm numarasıyla etiketlenir; çalışan uygulamanın sürüm numarası ve derleme özeti izlenir. Canlıya her sürüm aynı derleme çıktısından, ortamdan ortama terfi ettirilerek alınır.

**Değişiklik sınıfları.**

| Sınıf | Örnek | Onay |
|---|---|---|
| Standart | İçerik düzeltmesi, onaylı şablonla yapılandırma | Ürün Yöneticisi |
| Normal | Yeni işlev, entegrasyon değişikliği | Değişiklik Danışma Kurulu (haftalık, Salı) |
| Önemli | Kimlik doğrulama, yetkilendirme, ödeme akışı, veri modeli | Değişiklik Danışma Kurulu ve Bilgi Güvenliği Yöneticisi |
| Acil | Kritik güvenlik açığı, P1 olay | Nöbetçi yönetici ve Bilgi Güvenliği Yöneticisi; sonradan Kurul'a raporlanır |

Değişiklik Danışma Kurulu; Teknik Mimar (başkan), Ürün Yöneticisi, Test Yöneticisi, işletim ekibi temsilcisi ve Güvenlik Mimarından oluşur. 15 Aralık – 1 Şubat arasında yalnızca acil değişiklikler canlıya alınır. Kapsam değişiklikleri (yeni hizmet türü, bütçe veya takvim etkisi olan değişiklik) ayrıca Yönlendirme Kurulu onayı gerektirir. Bu belgelerde yapılacak değişiklikler revizyon tablosuna işlenir ve parametre değişiklikleri KHGM-VBP-YTB-001 Bölüm 14'te güncellenmeden uygulanmaz.

## 10. Tedarikçi yönetimi

| Tedarikçi | Kapsam | Tedarik yöntemi | Sözleşme süresi |
|---|---|---|---|
| Ana yüklenici | Yazılım geliştirme, test, veri taşıma, ilk yıl bakım | Açık ihale | 2026-12-04 – 2028-06-30 (+12 ay garanti) |
| Donanım sağlayıcı | Sunucu, depolama, ağ | Çerçeve anlaşma | Teslimat 2027-02 |
| Güvenlik anahtarı sağlayıcı | 2.300 FIDO2 anahtarı | Doğrudan temin | Teslimat 2027-03 |
| Bağımsız güvenlik test firması | Sızma testleri (beta öncesi, canlı öncesi) | Pazarlık usulü | 2027-07 – 2028-01 |
| Bağımsız erişilebilirlik firması | WCAG 2.2 AA değerlendirmesi | Pazarlık usulü | 2027-07 – 2028-01 |
| SMS toplayıcı | SMS gönderimi | Mevcut KHGM çerçeve sözleşmesi | Yıllık |

Tedarikçi sözleşmelerine bilgi güvenliği gereksinimleri, tedarik zinciri güvenliği taahhüdü ve kabul kriterleri eklenir (Rehber 3.5.3, "Tedarikçi Sözleşmelerinde Bilgi Güvenliğinin Ele Alınması", "Tedarik Zinciri Güvenliği", "Kabul Kriterlerinin Belirlenmesi"). Yükleniciden, yazılımın kullanım amacına uygun olmayan özellik ve arka kapı içermediğine dair taahhütname alınır (Rehber 3.2.6.3). Teknik şartnamede güvenlik gereksinimleri yer alır (Rehber 3.2.6.1). Yüklenici personeli kurum sistemlerine yalnızca KHGM onayıyla, süreli yetkiyle ve çok faktörlü kimlik doğrulamayla uzaktan erişir (Rehber 3.1.12, "Kurum Dışı Paydaşların Uzaktan Erişimi"). Yüklenici performansı aylık değerlendirme toplantısında; teslim edilen hikâye puanı, hata kaçış oranı, kilit personel sürekliliği ve sprint hedeflerine ulaşma oranıyla izlenir. Hakediş ödemeleri aşama kabulüne bağlıdır: sözleşme bedelinin yüzde 15'i alfa, yüzde 30'u özel beta, yüzde 30'u kamuya açık beta, yüzde 25'i canlı ve eski sistem kapatma kabulünde ödenir.

## 11. Eğitim ve değişim yönetimi

- **Personel eğitimi:** 1.150 personel için 4 saatlik uygulamalı eğitim; özel beta öncesi pilot illerde yerinde, sonrasında bölgesel merkezlerde (Ankara, İstanbul, İzmir, Erzurum, Diyarbakır, Antalya). Eğitim donanım güvenlik anahtarlarının dağıtımıyla birleştirilir; her personel anahtarını eğitimde kaydeder.
- **Dijital elçiler:** Her il müdürlüğünden en az bir gönüllü uzman, 2 günlük ileri eğitim alır ve ilk düzey iç destek verir.
- **Çağrı merkezi:** 120 temsilciye 1 günlük eğitim, senaryo tabanlı yanıt rehberi.
- **Yardımlı dijital hizmet:** Kabul bürosu görevlilerine başvuru sahibiyle birlikte portal kullanımı ve kişisel veri gizliliği eğitimi.
- **Kullanıcı rehberleri:** Türkçe ve İngilizce kısa videolar (altyazılı ve işaret dili seçenekli), adım adım rehberler.
- **Sistem yöneticileri:** İşletim kılavuzu, olay müdahale tatbikatı ve FKM geçiş eğitimi.

## 12. Takvim

| Dönem | Başlıca işler |
|---|---|
| Kasım-Aralık 2026 | PYP onayı, yüklenici sözleşmesi, ekip kurulumu, alfa başlangıcı |
| Ocak-Mart 2027 | Prototipler ve kullanıcı araştırması, mimari kararlar, güven anlaşmaları, donanım teslimatı ve kurulumu |
| Nisan-Ağustos 2027 | Özel beta (3 pilot il, H-01, H-03, H-05), personel eğitimi (pilot), bağımsız güvenlik ve erişilebilirlik değerlendirmesi |
| Eylül-Aralık 2027 | Kamuya açık beta, tüm iller ve tüm hizmetler, ulusal eğitim, veri taşıma provaları, yük testi, FKM tatbikatı |
| Ocak 2028 | Paralel işletim (eski sistem birincil), değişiklik dondurma, tepe dönem izleme |
| Şubat 2028 | Canlı değerlendirmesi, canlıya geçiş (2028-02-14) |
| Mart-Haziran 2028 | Eski sistemdeki açık başvuruların kapanması, son veri taşıma, eski sistemin kapatılması, proje kapanış raporu |

Resmî tatiller ve dini bayramlar sprint planlamasında dikkate alınır; bu dönemlerde canlı ortama sürüm alınmaz.

## 13. Onay

Bu plan, Proje Yönlendirme Kurulu'nun 2026-11-20 tarihli toplantısında onaylanmıştır. Plan her aşama değerlendirmesinden sonra ve kapsam, bütçe ya da takvimi etkileyen her onaylı değişiklikte güncellenir.
