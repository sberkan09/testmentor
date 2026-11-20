# Vatandaş Başvuru Portalı (VBP) — Yazılım Tasarım Belgesi

| Alan | Değer |
|---|---|
| Belge No | KHGM-VBP-YTB-001 |
| Sürüm | 1.0 |
| Tarih | 2026-11-20 |
| Kurum | Kamu Hizmetleri Genel Müdürlüğü (KHGM), Bilgi İşlem Dairesi Başkanlığı |
| Sınıf | Hizmete Özel |
| İlgili belgeler | KHGM-VBP-KIB-001 Kavramsal İşletim Belgesi, KHGM-VBP-PYP-001 Proje Yönetim Planı |

**Revizyon tablosu**

| Sürüm | Tarih | Açıklama | Hazırlayan / Onaylayan |
|---|---|---|---|
| 0.1 | 2026-09-18 | İlk taslak (mimari ve kimlik doğrulama) | Teknik Mimar |
| 0.9 | 2026-11-06 | Paydaş gözden geçirmesi; çatışma ve parametre tabloları eklendi | Güvenlik Mimarı, Erişilebilirlik Uzmanı |
| 1.0 | 2026-11-20 | Proje Yönlendirme Kurulu onayı | Proje Yöneticisi / Bilgi Güvenliği Yöneticisi |

## 1. Amaç ve kapsam

Bu belge, KHGM'nin vatandaşlara ve şirket temsilcilerine izin, ruhsat ve lisans başvurusu, belge yükleme, harç ödeme ve bildirim hizmeti sunan Vatandaş Başvuru Portalı (VBP) ile personelin başvuruları işlediği arka ofis uygulamasının yazılım tasarımını tanımlar. Hizmet kataloğu, aktörler, hacimler ve güvence düzeyi gerekçeleri KHGM-VBP-KIB-001'de; takvim, organizasyon ve test yaklaşımı KHGM-VBP-PYP-001'de yer alır. Ayarlanabilir tüm değerler Bölüm 14'teki parametre tablosunda tek yerde tutulur; diğer belgeler bu tabloya atıf yapar.

## 2. Dayanak standartlar ve öncelik kuralı

- **Siber Güvenlik Başkanlığı Bilgi ve İletişim Güvenliği Rehberi 1.1 ("Rehber").** 2019/12 sayılı Cumhurbaşkanlığı Genelgesi doğrultusunda hazırlandığından KHGM için bağlayıcıdır. VBP varlık grubunun kritiklik derecesi, Rehber'in kritiklik derecelendirme anketiyle "Derece 3" olarak belirlenmiştir; uygulanacak tedbirler bu dereceye göre seçilir (Rehber 2.1.2) ve KHGM, VBP için 1., 2. ve 3. seviye tedbirlerin tümünü uygulamayı kararlaştırmıştır.
- **NIST SP 800-63-4, 800-63A-4, 800-63B-4, 800-63C-4:** kimlik risk yönetimi, kanıtlama, doğrulama ve federasyon.
- **NIST SP 800-53 Rev. 5:** 800-63B-4 §2.4.1 gereği orta temel kümeden uyarlanmış kontroller; kuruluşça tanımlanan parametreler bu belgede doldurulmuştur.
- **OWASP ASVS 5.0:** genel hedef Düzey 2; arka ofis kimlik doğrulaması ve yönetim arayüzlerinde Düzey 3.
- **WCAG 2.2:** AA düzeyi. **GOV.UK Service Standard:** hizmet tasarımı ve işletim yaklaşımı.

**Öncelik kuralı.** Rehber açık bir yükümlülük getiriyorsa Rehber geçerlidir. Rehber konuyu kuruma bırakıyor ya da yalnızca örnek veriyorsa ("vb."), daha özgül hükmü olan teknik standart uygulanır: kimlikte NIST SP 800-63-4 ailesi, uygulama güvenliğinde ASVS, erişilebilirlikte WCAG 2.2. Her sapma Bölüm 13'e ve Dijital Kimlik Kabul Beyanı'na (DIAS, 800-63-4 §3.4.4) telafi edici kontroller ve kalan riskle birlikte işlenir (§3.4.2).

## 3. Mimari

### 3.1 Genel yapı

VBP çok katmanlı tasarlanmıştır; internete açık bileşenler DMZ'de, veri tabanları internetten erişilemeyen veri bölgesindedir (Rehber 3.2.5.3). Sistem KHGM'nin Ankara'daki birincil veri merkezinde ve İstanbul'daki Felaket Kurtarma Merkezi'nde (FKM) çalışır; kurumsal kritik veri kamuya açık bulut depolamada tutulmaz (Rehber 3.2.7.2). Sunucular arası iletişim karşılıklı TLS ile şifrelenir (Rehber 3.2.5.11).

| Bölge | Bileşen | Görev |
|---|---|---|
| DMZ | Web uygulama güvenlik duvarı, yük dengeleyici | TLS sonlandırma, HSTS, ön hız sınırlama, istek boyutu denetimi |
| DMZ | Portal Ön Yüzü | Sunucu taraflı sayfalar; JavaScript olmadan da çalışan aşamalı geliştirme |
| DMZ | Arka Uç Ön Yüz Hizmeti (BFF) | Oturum çerezini yönetir; erişim belirteçleri tarayıcıya gönderilmez (ASVS V10.1.1) |
| Uygulama | Kimlik ve Oturum Hizmeti | e-Devlet ve KKS için OIDC istemcisi, yerel doğrulayıcı, oturum deposu |
| Uygulama | Başvuru, Belge, Ödeme, Bildirim hizmetleri | Başvuru yaşam döngüsü; yükleme hattı ve tarama; KÖA entegrasyonu; SMS ve e-posta kuyruğu |
| Uygulama | İş Akışı ve Arka Ofis; Yetkilendirme Karar Noktası | Personel arayüzü; rol ve öznitelik tabanlı politika değerlendirmesi |
| Uygulama | Entegrasyon Katmanı | MNKS, TSBS, KBYS, KÖA bağdaştırıcıları ve devre kesiciler |
| Uygulama | Denetim Kaydı Hizmeti | Değiştirilemez iş ve güvenlik kayıtları; SIEM'e aktarım |
| Veri | İlişkisel veri tabanı, nesne deposu, oturum deposu, mesaj kuyruğu | Başvuru ve hesap verisi; şifreli ve sürümlü belgeler; sunucu taraflı oturumlar; asenkron işler |
| Yönetim | Ayrıcalıklı Erişim Yönetimi (PAM), atlama sunucusu | Sistem yöneticisi erişimi ve oturum kaydı |

### 3.2 Teknoloji ilkeleri

Ön yüz, erişilebilirlik özellikleriyle tanımlanmış ortak bir bileşen kütüphanesinden üretilir (GOV.UK Service Standard madde 13). Tüm yanıtlar HSTS (en az bir yıl, alt alan adları dahil), içerik güvenlik politikası, `frame-ancestors 'none'`, `nosniff` ve kısıtlayıcı yönlendiren politikası taşır (Rehber 3.2.9.3; ASVS V3.4.1, V3.4.3, V3.4.6); kişisel veri içeren yanıtlar `Cache-Control: no-store` ile gönderilir (ASVS V14.3.2). Kriptografik işlemler TS ISO/IEC 19790 onaylı modüllerle yapılır (Rehber 3.2.10, onaylı kriptografik modüller tedbiri; bkz. Ç-8).

## 4. Kimlik doğrulama tasarımı

### 4.1 Kimlik doğrulama yolları

VBP'de yalnızca aşağıdaki yollar vardır; belgelenmemiş giriş yolu ya da varsayılan hesap bulunmaz (ASVS V6.1.3, V6.3.2, V6.3.4; Rehber 3.2.1.6):

1. **Vatandaş:** e-Devlet Kapısı ile OpenID Connect yetkilendirme kodu akışı (PKCE). VBP güvenen taraf (RP), e-Devlet kimlik sağlayıcıdır (IdP).
2. **Şirket temsilcisi:** VBP yerel hesabı; parola ile birlikte TOTP, geçiş anahtarı ya da kısıtlı doğrulayıcı olarak SMS.
3. **Personel:** KHGM Kurumsal Kimlik Sağlayıcı (KKS) ile OIDC; FIDO2 donanım güvenlik anahtarı ve PIN (AAL3).
4. **Sistem yöneticisi:** PAM ve atlama sunucusu; ayrı yönetici hesabı, AAL3.
5. **Servis hesapları:** karşılıklı TLS ve kısa ömürlü istemci kimlik bilgileri; insan hesabı servis hesabı olarak kullanılmaz (Rehber 3.1.12, "Servis Hesaplarının Yönetimi").

Güvence düzeyleri (vatandaş IAL2/AAL2/FAL2, temsilci IAL2/AAL2, personel IAL2/AAL3/FAL2) KHGM-VBP-KIB-001 Bölüm 11'de gerekçelendirilmiştir.

### 4.2 e-Devlet federasyonu (FAL2)

İlişki, önceden kurulmuş ikili güven anlaşmasına dayanır; anlaşma kabul edilecek en düşük IAL/AAL değerlerini, öznitelikleri ve anahtar yayımlama yöntemini tanımlar (800-63C-4 §2.3, §3.5.1).

- İşlemi her zaman VBP başlatır; `state`, `nonce` ve PKCE her istekte üretilip tarayıcı oturumuna bağlanır (63C §2.3; ASVS V10.1.2, V10.2.1, V10.5.1).
- Kimlik belirtecinin imzası, hedef kitlesi ve tek kullanımı doğrulanır (63C §2.2, §2.3; ASVS V6.8.2, V10.5.4). Geçerlilik penceresi en çok 5 dakika, saat kayması toleransı 60 saniyedir.
- Federe tanımlayıcı, e-Devlet'in VBP'ye özgü takma adlı tanımlayıcısıdır; T.C. kimlik numarası ayrı öznitelik olarak alınır (63C §2.3) ve veri tabanında birincil anahtar yapılmaz (Rehber 4.1.1.3).
- `acr`, `amr` ve `auth_time` her girişte denetlenir (63C §4.7; ASVS V6.8.4). Bildirilen düzey AAL2'nin altındaysa ya da alan yoksa VBP tek faktörlü doğrulama varsayar ve oturumu "sınırlı kip"te açar: kişisel veri ve başvuru içeriği gösterilmez, daha güçlü yöntemle yeniden giriş önerilir.
- e-Devlet oturumunun bitmesi VBP oturumunu bitirmez (800-63B-4 §5.2). e-Devlet arka kanal oturum kapatma bildirimi sağlarsa doğrulanmış oturum kapatma belirteciyle işlenir (ASVS V10.5.5). Yeniden doğrulama gerektiğinde `prompt=login` ile taze doğrulama istenir; yeterliliğe VBP karar verir (800-63B-4 §5.2).

### 4.3 Şirket temsilcisi yerel hesabı

Yerel hesap, e-Devlet kimlik bilgisi olmayan yabancı uyruklu temsilciler ve birden çok şirket adına işlem yapan vekil müşavirler için gereklidir. Kimlik bir kez kanıtlanır: Türk vatandaşı temsilci e-Devlet federasyonuyla, yabancı uyruklu temsilci il müdürlüğünde yüz yüze (IAL2, 800-63A-4 §4.2). Şirket adına yetki, Ticaret Sicil Bilgi Servisi (TSBS) sorgusu ve personelin yetki belgesi incelemesiyle doğrulanır; yılda bir ve TSBS'de değişiklik görüldüğünde yenilenir.

Kanıtlamadan sonra e-postayla etkinleştirme bağlantısı gönderilir. Kurum ilk parola üretmez; temsilci parolasını kendisi belirler (Rehber 3.2.1.5). Etkinleştirmede ikinci faktör bağlanması zorunludur. AAL2 doğrulayıcıları en az bir oltalamaya dirençli seçenek sunmak zorunda olduğundan (800-63B-4 §2.2.2) geçiş anahtarı (WebAuthn) önerilen yöntem olarak sunulur.

### 4.4 Personel kimlik doğrulaması (AAL3)

KKS'deki bağlı doğrulayıcı, PIN ile etkinleştirilen ve özel anahtarı dışa aktarılamayan FIDO2 donanım anahtarıdır; çok faktörlü kriptografik ve oltalamaya dirençlidir (800-63B-4 §2.3.1, §2.3.2, §3.2.5). Eşitlenebilir geçiş anahtarları personel için kabul edilmez (§2.3.2). Her personele iki anahtar bağlanır. Kimlik kanıtlaması işe girişte İnsan Kaynakları'nda yüz yüze yapılır. VBP arka ofis oturumunu yalnızca KKS `acr` ile AAL3 bildirdiğinde açar.

### 4.5 Parola politikası

Politika yalnızca VBP'nin merkezi olarak doğruladığı temsilci parolalarına uygulanır; personel anahtar PIN'i yerel etkinleştirme sırrıdır (800-63B-4 §3.2.10).

- **Uzunluk.** En kısa 15 karakter, her Unicode kod noktası bir karakter. 800-63B-4 §3.1.1.2(1) çok faktörlü süreçte 8 karaktere izin verip 15'i tek faktörlü kullanım için zorunlu tutar; ASVS V6.2.1 8'i alt sınır, 15'i güçlü öneri sayar. VBP 15'i seçmiştir, çünkü AAL2 hareketsizlik sonrası yeniden doğrulamada parola oturum sırrıyla birlikte tek başına kullanılabilir (§2.2.3; Ç-1). En uzun 128 karakterdir (§3.1.1.2(2); ASVS V6.2.9).
- **Karakterler.** Boşluk dahil yazdırılabilir ASCII ve Unicode kabul edilir; karmadan önce NFC normalleştirmesi yapılır; parola kesilmeden ve harf dönüşümü yapılmadan doğrulanır (§3.1.1.2; ASVS V6.2.8).
- **Bileşim kuralı yoktur** (§3.1.1.2(5); ASVS V6.2.5). IA-5(1)(h) değeri: "en kısa uzunluk dışında kural yok".
- **Yasaklı liste.** Yeni parola; sızıntı derlemeleri, yaygın parolalar ve bağlama özgü sözcüklerle (KHGM, Kamu Hizmetleri, VBP, Vatandaş Başvuru, kullanıcı adı, şirket unvanı ve türevleri) bütün olarak karşılaştırılır (§3.1.1.2; ASVS V6.1.2, V6.2.4, V6.2.12; IA-5(1)(a)-(b)). Liste kurum içinde tutulur, 3 ayda bir ve sızıntı şüphesinde güncellenir. Ret nedeni açıklanır ve güçlü parola için yönlendirme gösterilir.
- **Geçerlilik süresi.** En uzun geçerlilik 365 gündür. Rehber 3.2.1.8 (Parola Yönetimi) en uzun geçerlilik tanımlanmasını şart koşar; 800-63B-4 §3.1.1.2(6) ve ASVS V6.2.10 periyodik değişikliği yasaklar. Öncelik kuralı gereği Rehber uygulanır ve sapma DIAS'a işlenmiştir (Ç-2). Süre dolmadan 14 gün önce bildirim gönderilir (ASVS V6.4.5). Ele geçirme kanıtında (sızıntı eşleşmesi, şüpheli giriş) değişiklik derhal zorunludur (§3.1.1.2(6)).
- **Değiştirme.** Mevcut parola, yeni parola ve onayı istenir (Rehber 3.2.1.8; ASVS V6.2.3); onay alanı WCAG 2.2 SC 3.3.7 güvenlik istisnasına girer (Ç-7).
- **Kullanılabilirlik.** Alan varsayılan olarak maskelenir, gösterme seçeneği vardır (Rehber 3.2.1.4; ASVS V6.2.6). Yapıştırma, parola yöneticisi ve otomatik doldurma engellenmez (§3.1.1.2; ASVS V6.2.7; WCAG 2.2 SC 3.3.8). İpucu ve gizli soru yoktur (§3.1.1.2(7)-(8); Rehber 3.2.1.8).
- **Saklama.** Bellek açısından maliyetli parola karma işlevi, en az 128 bit tuz ve donanım güvenlik modülündeki gizli anahtarla ek anahtarlı karma kullanılır (§3.1.1.2; IA-5(1)(d); ASVS V11.4.2; Rehber 3.2.1.4). Maliyet parametresi yılda bir gözden geçirilir.

### 4.6 İkinci faktör ve tek kullanımlık kodlar

**TOTP** 6 haneli, 30 saniye adımlıdır. 800-63B-4 §3.1.4.2 ömrün saat kayması, ağ gecikmesi ve giriş süresine göre tanımlanmasını, ASVS V6.5.5 en çok 30 saniyeyi öngörür. VBP geçerli adımla birlikte yalnızca bir önceki adımı kabul eder (en çok 59 saniye; Ç-5). Her kod bir kez kabul edilir (ASVS V6.5.1), sunucu saati güvenilir kaynaktan alınır (ASVS V6.5.8). TOTP tohumları en az 160 bit ve şifreli saklanır.

**SMS** kamuya açık telefon ağı kullandığından kısıtlı doğrulayıcıdır (800-63B-4 §3.2.9). KHGM bu riski akıllı telefonu olmayan temsilciler için kabul etmiş, DIAS'a geçiş planı eklemiştir. SMS yalnızca doğrulanmış numaraya gider; bağlama sırasında riskler ve alternatifler bildirilir (§3.1.3.3; ASVS V6.6.1). Kod 6 haneli, 5 dakika geçerli ve yalnızca kendi giriş işlemine bağlıdır (§3.1.3.2; ASVS V6.6.2); yeni kod sayaç sıfırlamaz. Gönderim hesap başına saatte 5, günde 10 ile sınırlıdır. Numara değişikliği yeni doğrulayıcı bağlama sayılır (§3.1.3.3).

**E-posta** hiçbir aşamada kimlik doğrulama faktörü değildir (800-63B-4 §3.1.3.1; ASVS V6.3.6). Yalnızca adres doğrulama ve kurtarma kodu için kullanılır; bu kodlar 60 dakika geçerlidir (≤24 saat, 800-63A-4 §3.8; 800-63B-4 §4.2.1.2).

### 4.7 Hız sınırlama, bot önleme ve kilitleme

Temel tercih hesabı kilitlemek yerine denemeleri yavaşlatmaktır; kilitleme, kullanıcı adını bilen saldırganın meşru kullanıcıyı dışarıda bırakmasına izin verir (ASVS V6.1.1; Ç-3).

1. **Hesap bazlı gecikme (AC-7).** 15 dakika içinde 10 ardışık başarısız denemede AC-7(b)'deki "sonraki giriş istemini geciktirme" seçeneği uygulanır: gecikme 1 dakikadan başlar, her başarısızlıkta iki katına çıkar, en çok 60 dakikadır (800-63B-4 §3.2.2).
2. **Bot doğrulama sorgusu.** Hesapta 5 ardışık başarısızlık ya da bir IP'den 10 dakikada 20 başarısızlık sonrasında istenir: önce etkileşimsiz tarayıcı kanıtı, yetmezse nesne tanıma sorgusu (Bölüm 10.4).
3. **Doğrulayıcının devre dışı bırakılması.** Aynı doğrulayıcıda başarılı giriş olmadan 50 başarısız deneme olduğunda doğrulayıcı (parola ve ikinci faktör birlikte denenmişse ikisi) devre dışı kalır ve yalnızca kurtarmayla yeniden bağlanır (§3.2.2, üst sınır 100). Bu, Rehber 3.2.1.1'deki kalıcı kilit niteliğindedir.
4. **Personel.** KKS'de 10 ardışık başarısız denemede hesap yönetici kaldırana kadar kilitlenir (AC-7(b)) ve SOME'ye alarm gider.
5. Başarılı giriş, kullanılan doğrulayıcıların sayaçlarını sıfırlar (§3.2.2).

Giriş, parola sıfırlama ve kayıt işlevleri hesabın varlığını hata metni, durum kodu, yanıt boyutu ya da süresiyle belli etmez (Rehber 3.2.1.9; ASVS V6.3.8). Parola sıfırlama hesap başına saatte 3, IP başına saatte 10 ile; kimlik doğrulama uç noktaları IP başına dakikada 20 istekle sınırlıdır.

### 4.8 Hesap kurtarma ve bildirimler

Temsilci hesabı en çok AAL2 olduğundan kurtarma 800-63B-4 §4.2.2.2'ye göredir: (a) kayıtlı kurtarma kodu ile e-postaya gönderilen kurtarma kodu, (b) bir kurtarma kodu ile bağlı tek faktörlü doğrulayıcı (parola ya da TOTP) veya (c) e-Devlet ya da il müdürlüğünde yeniden kimlik kanıtlama. Kayıtlı kurtarma kodu 80 bit (16 karakter Base32), karma olarak saklanır, kullanılınca geçersiz olur ve yenisi verilir (§4.2.1.1). Kurtarma ikinci faktörleri atlamaz (ASVS V6.4.3) ve ana mekanizmadan zayıf değildir (Rehber 3.2.1.11). Sonunda yeni parola belirlenir (IA-5(1)(e)) ve diğer oturumları sonlandırma seçeneği sunulur (ASVS V7.4.3). Yardım masası sıfırlamayı başlatabilir, parolayı göremez ve belirleyemez (ASVS V6.4.6).

Doğrulayıcı bağlama ya da kaldırma, kurtarma, kurtarma kodu yenileme, e-posta ya da telefon değişikliği ve olağan dışı konumdan giriş, kayıtlı tüm adreslere anında bildirilir (800-63B-4 §4.2.3, §4.6; ASVS V6.3.5, V6.3.7).

## 5. Oturum yönetimi ve yeniden kimlik doğrulama

### 5.1 Oturum sırrı ve çerez

Oturum, kimlik doğrulamanın ardından sunucuda üretilen, en az 128 bit entropili opak referans belirteciyle sürer (800-63B-4 §5.1; ASVS V7.2.3; Rehber 3.2.2.1); her doğrulama ve yeniden doğrulamada yenilenir (ASVS V7.2.4). Çerez `__Host-vbp_sid` adını ve `Secure`, `HttpOnly`, `Path=/` özniteliklerini taşır; portalda `SameSite=Lax`, arka ofiste `SameSite=Strict` (§5.1.1; ASVS V3.3.1-V3.3.4; Rehber 3.2.2.4). Oturum kimliği URL'de, hata mesajında ve iz kaydında yer almaz; kayıtta yalnızca özeti tutulur (Rehber 3.2.2.2). Durum değiştiren isteklerde CSRF belirteci doğrulanır (§5.1; Rehber 3.2.10.5).

### 5.2 Zaman aşımları

Süreler oturumun AAL değerine göre belirlenmiş ve sistem güvenlik planına işlenmiştir (800-63B-4 §5.2; ASVS V7.1.1; Rehber 3.2.2.3).

- **AAL2 (vatandaş, temsilci):** hareketsizlik 30 dakika, toplam 12 saat. NIST üst önerisi 1 saat ve 24 saattir (§2.2.3); daha kısa süreler, portalın belediye hizmet noktaları ve internet kafeler gibi paylaşılan bilgisayarlardan kullanılmasından kaynaklanır. Hareketsizlik dolup toplam süre dolmadıysa temsilci oturum sırrıyla birlikte yalnızca parolasını girerek devam eder (§2.2.3); vatandaş için e-Devlet'ten taze doğrulama istenir.
- **AAL3 (personel):** hareketsizlik 15 dakika, toplam 10 saat (§2.3.3); mesai ve fazla mesai payını kapsar. Yeniden doğrulama ilk doğrulamayla aynıdır.
- **Ekran kilidi (AC-11):** arka ofis 8. dakikada uyarı gösterir; kullanıcı süreyi uzatmazsa 10. dakikada ekranı kilitler ve kişisel veriyi gizler. Kilit yalnızca AAL3 yeniden doğrulamayla açılır (AC-11(b)); kilitli oturum 15. dakikada sonlandırılır. İş istasyonu kilidi KHGM masaüstü politikasına tabidir.
- **Sonlandırma (AC-12):** hareketsizlik dolunca kimliği doğrulanmış durum biter ve işlem yapılamaz; AAL2'de oturum sırrı yalnızca parola ile yeniden doğrulama için toplam süre sonuna kadar sunucuda tutulur, AAL3'te hemen silinir. Oturum tamamen; toplam süre dolduğunda, çıkışta, parola ya da doğrulayıcı değiştiğinde (diğer oturumlar için kullanıcı tercihiyle), rol ya da yetki değiştiğinde, hesap devre dışı bırakıldığında veya silindiğinde, yönetici sonlandırdığında ve oturum izleme dolandırıcılık göstergesi saptadığında biter (Rehber 3.2.2.3; ASVS V7.4.1, V7.4.2, V7.4.5; 800-63B-4 §5.3). Sunucu kaydı silinir, `Clear-Site-Data` gönderilir (ASVS V14.3.1). Her korumalı sayfada çıkış bağlantısı vardır (AC-12(1)).

Uyarı ve uzatma davranışı Bölüm 10.3'tedir.

### 5.3 Eşzamanlı oturumlar

Vatandaş ve temsilci için en çok 3 eşzamanlı oturum vardır; dördüncüsü en eskisini sonlandırır ve kullanıcıya bildirilir. Personel ve sistem yöneticisi için sınır 1'dir; olay SIEM'e iletilir (AC-10; ASVS V7.1.2). Kullanıcılar "Oturumlarım" sayfasında etkin oturumlarını görüp yeniden doğrulamayla sonlandırabilir (Rehber 3.2.2.5; ASVS V7.5.2).

### 5.4 Hassas işlemlerde yeniden doğrulama (IA-11)

Şu işlemler son 5 dakika içinde tam kimlik doğrulama gerektirir (IA-11; Rehber 3.2.1.10; ASVS V7.5.1, V7.5.3): e-posta, telefon ve doğrulayıcı ayarı değişikliği; kurtarma kodu yenileme; yeni temsilci yetkilendirme; iade için IBAN bildirme; arka ofiste karar onayı, iade onayı ve toplu dışa aktarım. Vatandaş için `max_age` ve `prompt=login` ile e-Devlet'e yönlendirilir (63C §4.7).

## 6. Arka ofis yetkilendirme modeli

Yetkilendirme, rol tabanlı erişim ile öznitelik kurallarının birleşimidir ve her istekte sunucudaki Yetkilendirme Karar Noktası'nda değerlendirilir (Rehber 3.2.3, "Yetki Denetimi"; ASVS V8.2.1, V8.3.1). Yetki matrisi, Hizmet Sahibi'nin onayladığı ve sürüm denetimindeki bir politika dosyasıdır (ASVS V8.1.1).

| Rol | Temel yetkiler | Öznitelik kısıtları |
|---|---|---|
| Başvuru Uzmanı | İnceleme, ek belge isteme, karar önerisi | Kendi ili ve hizmet türleri; yalnızca kendine atanmış dosyalar |
| Onay Yetkilisi | Öneriyi onaylama veya iade | Kendi birimi; kendi hazırladığı dosyayı onaylayamaz |
| Mali İşler Uzmanı | Mutabakat, iade hazırlama | Başvuru içeriği maskeli |
| Yardım Masası Uzmanı | Durum görüntüleme, kurtarma başlatma | Kişisel veri maskeli; belge içeriği yok |
| Birim Yöneticisi | Atama, raporlar | Kendi birimi |
| Denetçi | İş ve güvenlik kayıtlarını okuma | Tüm iller; değişiklik yok |
| Sistem Yöneticisi | Altyapı ve yapılandırma | Uygulama üzerinden başvuru verisine erişim yok |

**Görevler ayrılığı.** Başvuru kararı ve harç iadesi hazırlayan ve onaylayan olarak iki kişi gerektirir. Personel kendisi, yakını ya da daha önce temsilcisi olduğu şirketle ilgili dosyada görev alamaz; atamada çıkar çatışması beyanı alınır.

**Veri düzeyi.** Nesne düzeyinde yetki her başvuru kimliği için denetlenir; kimlikler tahmin edilemez (ASVS V8.2.2). T.C. kimlik numarası, iletişim ve özel nitelikli veri alanları, işlenmesi asıl amaç olmayan rollere maskeli gösterilir (Rehber 3.2.7.20, 4.1.4.2; ASVS V8.2.3). Yetki değişikliği anında uygulanır, etkilenen oturumlar sonlandırılır (ASVS V8.3.2).

**Bağlam.** Arka ofise yalnızca kurum ağından ya da yönetilen cihazlardaki VPN'den erişilir; ağ konumu tek başına yetki gerekçesi değildir (ASVS V8.4.2). Toplu dışa aktarım günde 5 işlemle sınırlıdır, birim yöneticisi onayı ister ve SOME'ye bildirilir (Rehber 3.2.7.4). Acil erişim, Bilgi Güvenliği Yöneticisi onayıyla en çok 8 saat verilir; işlemler işaretlenir ve ertesi iş günü incelenir.

**Hesap yaşam döngüsü.** Hesap talepleri tanımlı süreçle izlenir (Rehber 3.1.12, "Erişim Kontrol Politikasının Oluşturulması ve Uygulanması"). Ayrılan ya da görevi değişen personelin hesabı İK bildiriminden itibaren 4 saatte, 45 gün kullanılmayan personel hesabı otomatik olarak devre dışı kalır (AC-2(3)). 24 ay giriş yapılmayan temsilci hesabı pasif duruma alınır (Rehber 3.2.1.12). Ayrıcalıklı yetkiler 3 ayda bir, diğerleri 6 ayda bir gözden geçirilir; bu, Rehber'in yılda en az bir gözden geçirme beklentisini aşar (Rehber 3.1.12, "Sistem Yöneticisi Görevlerinin Güvenliği").

## 7. İz kayıtları ve izleme

### 7.1 Kayıt envanteri ve içerik

Her bileşenin kayıtları; biçimi, yeri ve erişim yetkisiyle bir envanterde tanımlıdır (ASVS V16.1.1). Kaydedilen güvenlik olayları: başarılı ve başarısız tüm kimlik doğrulamalar ve faktör türü (Rehber 3.2.1.3; ASVS V16.3.1), yetkilendirme retleri (ASVS V16.3.2), kişisel veriye erişimler (Rehber 4.1.2.1), yönetici işlemleri ve yapılandırma değişiklikleri (Rehber 3.1.12; 3.2.5), girdi doğrulama hataları (Rehber 3.2.10.2), dış sistem çağrılarının girdi ve sonuçları (Rehber 3.2.11.9), TLS hataları (ASVS V16.3.4).

Her kayıt olay türü, kaynak bileşen, zaman, kullanıcı ya da servis kimliği, kaynak ve hedef adres, işlem özeti ve ilişki kimliği içerir (Rehber 3.1.8.4, 3.2.8.2; ASVS V16.2.1). Zaman UTC ve milisaniye çözünürlüklüdür; sunucular iki iç NTP sunucusundan eşitlenir (AU-8; Rehber 3.1.8.3). Parola, tek kullanımlık kod, oturum belirteci ve kart verisi yazılmaz; T.C. kimlik numarası maskelenir, özel nitelikli veri girmez (Rehber 3.2.8.3, 4.1.2.6; ASVS V16.2.5). Kullanıcı girdileri kodlanarak kayıt sahteciliği önlenir (Rehber 3.2.8.6; ASVS V16.4.1).

### 7.2 Koruma ve saklama

Kayıtlar şifreli kanalla, uygulamadan ayrı merkezi kayıt sistemine ve KHGM SOME'nin SIEM'ine aktarılır (Rehber 3.1.8.6, 3.2.4.1; ASVS V16.4.3). Merkezi depo yalnızca ekleme kipindedir, bloklar zaman damgalı özetlerle zincirlenir; uygulama sunucusu ele geçirilse bile kayıt silinemez (Rehber 3.1.8.1, 3.2.7.8; ASVS V16.4.2). Erişim yalnızca Denetçi ve SOME analistine açıktır.

Güvenlik iz kayıtları 2 yıl saklanır: 1 yıl çevrim içi, 1 yıl şifreli arşiv (AU-11; Rehber 3.1.8.1). Kişisel veri erişim kayıtları 2 yıl (Rehber 4.1.2.2), hata ayıklama kayıtları 30 gün tutulur. Başvuru işlem tarihçesi iş verisidir ve dosyayla saklanır (Bölüm 8.3). Depolama, 2 yıllık hacme yüzde 30 pay eklenerek ayrılmıştır (AU-4; Rehber 3.1.8.5).

### 7.3 İnceleme ve izleme

SIEM korelasyon kurallarıyla sürekli izler (Rehber 3.1.8.7; SI-4). Ayrıcalıklı işlemler her iş günü, genel güvenlik kayıtları haftalık incelenir ve bulgular Bilgi Güvenliği Yöneticisine raporlanır (AU-6; Rehber 3.1.8.2). Başlıca göstergeler: kimlik bilgisi doldurma örüntüleri, olağan dışı toplu görüntüleme, mesai dışı arka ofis erişimi, yönetici hesabı oluşturma ve silme (Rehber 3.1.12). Kayıt üretimi ya da aktarımı başarısız olursa SOME ve nöbetçi yönetici 15 dakika içinde uyarılır; depolama yüzde 80 dolulukta uyarı verir (AU-5; Rehber 3.1.8.6). Kayıt hattı tamamen durursa arka ofiste dışa aktarım ve toplu işlemler askıya alınır.

## 8. Veri koruma ve saklama

### 8.1 Veri sınıflandırma

| Düzey | Örnek | Koruma |
|---|---|---|
| Kamuya açık | Hizmet rehberleri, harç tarifesi | Bütünlük |
| Kuruma özel | İş akışı durumları, istatistikler | Rol tabanlı erişim |
| Kişisel veri | Ad, T.C. kimlik numarası, adres, başvuru içeriği, belgeler | Aktarımda ve durağanda şifreleme, maskeleme, erişim kaydı |
| Özel nitelikli kişisel veri | Bazı izinlerde istenen sağlık raporu, adli sicil belgesi | Ek alan şifrelemesi, ayrı anahtar, AAL3 ve atama şartı |

Sınıflandırma ve koruma gereksinimleri ASVS V14.1.1-V14.1.2 kapsamında belgelenmiştir. Veri tabanı ve nesne deposu AES-256 ile şifrelenir; özel nitelikli veri ayrıca uygulama katmanında HSM'de yönetilen ayrı anahtarla şifrelenir (Rehber 3.2.7.10) ve yalnızca çok faktörlü doğrulanmış, dosyaya atanmış personele açılır (Rehber 4.1.3.5).

### 8.2 Kişisel veri işleme

İşlenen veriler, KHGM kişisel veri işleme envanterinde amaç, hukuki dayanak, kategori, alıcı ve azami süreyle tanımlıdır (Rehber 4.1.1.1); süreler KHGM Kişisel Veri Saklama ve İmha Politikası'ndadır (Rehber 4.1.1.2). Aydınlatma metni veri toplanmadan önce gösterilir ve görüntülenme zaman damgasıyla kaydedilir (Rehber 4.1.6.2). Açık rıza yalnızca rızaya dayanan isteğe bağlı işlemlerde amaç başına ayrı alınır ve zaman damgasıyla saklanır (Rehber 4.1.7.1, 4.1.7.2). MNKS'den yalnızca başvurunun gerektirdiği öznitelikler sorgulanır. Görüntü üst verisi saklanmadan önce temizlenir (ASVS V14.2.8). Üçüncü taraf analiz aracı kullanılmaz; analitik kurum içinde ve çerezsizdir (ASVS V14.2.3).

### 8.3 Saklama ve imha

| Veri | Saklama | Süre sonunda |
|---|---|---|
| Gönderilmemiş taslak ve ekleri | Son değişiklikten itibaren 90 gün | Silme; 7 gün önce bildirim |
| Sonuçlanmış başvuru dosyası (belgeler, kararlar, işlem tarihçesi) | Kapanıştan itibaren 10 yıl (KHGM politikası) | Arşiv değerlendirmesi, imha |
| Ödeme ve iade kayıtları | 10 yıl (KHGM politikası) | İmha |
| Bildirim gönderim kayıtları | 2 yıl | İmha |
| Güvenlik ve kişisel veri erişim kayıtları | 2 yıl | İmha |
| Pasif temsilci hesabı | Pasifleştirmeden itibaren 12 ay | Hesap kimlik verisi silinir |

Periyodik imha 6 ayda bir çalışır, geri getirilemez silme yapılır ve tutanak oluşturulur (Rehber 3.2.7.19, 4.1.5.4; ASVS V14.2.7). Yedekten dönüşte imhası yapılmış kayıtlar imha listesine göre yeniden silinir (Rehber 4.1.5.6). Canlı dışı ortamlarda yalnızca sentetik veri vardır (Rehber 3.2.6.2, 3.2.7.7).

## 9. Dosya yükleme

Tüm yüklemeler aynı hattan geçer (ASVS V5.1.1; Rehber 3.2.4.5).

**Türler ve sınırlar.** Kabul edilenler PDF (PDF/A dahil), JPEG ve PNG'dir. Arşiv, ofis belgesi ve çalıştırılabilir içerik kabul edilmez; böylece sıkıştırılmış dosya riskleri (ASVS V5.2.3, V5.3.3) tasarım gereği ortadan kalkar. Dosya en çok 10 MB; başvuru başına en çok 20 dosya ve 50 MB; hesap kotası 500 MB (ASVS V5.2.1, V5.2.4); görüntü en çok 40 megapikseldir (ASVS V5.2.6). Kullanıcı saatte en çok 60 dosya yükleyebilir. İstek boyutu WAF'ta da sınırlanır (Rehber 3.2.10.14).

**İşleme hattı.** (1) Dosya, uygulama dizini dışındaki karantinaya rastgele tanımlayıcıyla yazılır; özgün ad yalnızca denetlenmiş üst veri olarak tutulur (ASVS V5.3.1, V5.3.2). (2) Uzantı ile içerik imzası karşılaştırılır (ASVS V5.2.2). (3) İki farklı üreticinin tarama motoru çalıştırılır (ASVS V5.4.3; Rehber 3.1.5). (4) PDF'te gömülü betik, gömülü dosya ya da otomatik eylem varsa içerik yeniden oluşturulur, olmazsa dosya reddedilir; görüntü üst verisi temizlenir. (5) Temiz dosya şifreli nesne deposuna taşınır, KBYS'ye referans iletilir.

**Zararlı içerik** saptanırsa dosya 30 gün karantinada kalır, kullanıcıya ayrıntı içermeyen genel mesaj gösterilir ("Dosyanız güvenlik denetiminden geçemedi; lütfen farklı bir dosya yükleyin."), olay SIEM'e yazılır; aynı hesaptan 24 saatte ikinci olayda SOME'ye alarm gider.

**İndirme.** Belgeler uygulamanın belirlediği, RFC 6266'ya göre kodlanmış adla, `Content-Disposition: attachment` ve doğru içerik türüyle sunulur (ASVS V5.4.1, V5.4.2). Personel belgeleri arka ofisteki yalıtılmış görüntüleyicide açar.

**Erişilebilir yükleme.** Sürükle-bırak alanının yanında her zaman "Dosya seç" düğmesi vardır (WCAG 2.2 SC 2.5.7); ilerleme ve tarama sonucu durum mesajıyla duyurulur (SC 4.1.3); ret nedeni dosya adıyla metin olarak verilir (SC 3.3.1).

## 10. Erişilebilirlik, formlar ve dil

### 10.1 Uygunluk hedefi

Portal ve arka ofis WCAG 2.2 AA uygunluğunu hedefler; hedef KHGM Erişilebilirlik Beyanı'nda yayımlanır (GOV.UK Service Standard madde 5). Bileşen kütüphanesi; klavye kullanımı (SC 2.1.1), görünür odak (SC 2.4.7), odağın yapışkan başlık ya da çerez bandı altında kalmaması (SC 2.4.11), en az 24×24 CSS piksel hedef (SC 2.5.8), 320 CSS piksel genişlikte yeniden akış (SC 1.4.10) ve en az 4,5:1 metin kontrastıyla (SC 1.4.3) tanımlanır.

### 10.2 Formlar ve hatalar

Formlar "her sayfada tek konu" ilkesiyle küçük adımlara bölünür; her alanın görünür etiketi ve gerekirse biçim örneği vardır (SC 3.3.2); kişisel bilgi alanları `autocomplete` ile işaretlenir (SC 1.3.5). Daha önce girilen ya da MNKS ve TSBS'den gelen bilgi tekrar istenmez (SC 3.3.7).

Doğrulama sunucu tarafında yapılır (Rehber 3.2.10.1). Hatada sayfa başlığına "Hata:" eklenir, üstte her maddesi ilgili alana bağlanan bir hata özeti gösterilir, alanın yanında hata metinle açıklanır (SC 3.3.1) ve mümkünse düzeltme önerilir (SC 3.3.3), örneğin "Vergi numarası 10 haneli olmalıdır; 9 hane girdiniz." Hata yalnızca renkle belirtilmez (SC 1.4.1). Başvuru ve ödeme hukuki ve mali sonuç doğurduğundan gönderimden önce düzeltilebilir bir özet sayfası gösterilir; gönderilen başvuru karar öncesi geri çekilebilir (SC 3.3.4). Yardım bağlantısı her sayfada aynı konumdadır (SC 3.2.6).

### 10.3 Zaman aşımlarının erişilebilir yönetimi

Hareketsizlik zaman aşımı SC 2.2.1'in "uzatma" seçeneğiyle karşılanır: AAL2'de 25. dakikada, AAL3'te ekran kilidinden önce 8. dakikada erişilebilir bir iletişim kutusu açılır, kalan süre ekran okuyucuya duyurulur ve tek düğmeyle uzatılır. Uyarıdan sonra en az 120 saniye tanınır (SC 2.2.1 en az 20 saniye ister), uzatma sayısı sınırsızdır ve uzatma etkinlik sayılır (800-63B-4 §5.2).

Toplam oturum süresi ise 800-63B-4 §2.2.3 ve §2.3.3 gereği etkinlikle uzatılamaz ve SC 2.2.1'in istisnalarına (gerçek zamanlı olay, zorunlu süre, 20 saati aşan süre) açıkça girmez. Karar: 800-63B-4 geçerlidir ve durum kabul edilmiş erişilebilirlik sapması olarak kaydedilmiştir (Ç-6). Etkiyi azaltmak için bitişten 5 dakika önce uyarı verilir, yanıtlar her adımda taslak olarak kaydedilir ve yeniden doğrulamadan sonra kullanıcı veri kaybı olmadan kaldığı adıma döner (SC 2.2.5, AAA olsa da uygulanır). Başarılı yeniden doğrulama iki süreyi de sıfırlar.

### 10.4 Erişilebilir kimlik doğrulama

Kimlik doğrulama SC 3.3.8'e uygundur: parola alanında yapıştırma ve parola yöneticisi çalışır, TOTP ve SMS kodu `autocomplete="one-time-code"` ile yapıştırılabilir, geçiş anahtarı bilişsel test gerektirmeyen alternatif sunar. Rehber 3.2.1.9 CAPTCHA'yı kaba kuvvet önlemlerine örnek olarak verir ("vb."), zorunlu tutmaz; SC 3.3.8 ise bulmaca ve metin tanıma testlerini sınırlar. Karar: metin tabanlı CAPTCHA kullanılmaz; etkileşimsiz tarayıcı kanıtı ve gerekirse SC 3.3.8'in "nesne tanıma" istisnasına giren sorgu kullanılır, Bölüm 4.7'deki gecikme bunu tamamlar (Ç-4).

### 10.5 Dil

Varsayılan dil Türkçedir (Rehber 4.6.1.4); vatandaş ve temsilci işlemlerinin tümü İngilizce de sunulur. Sayfa dili `lang` ile (SC 3.1.1), farklı dildeki parçalar, örneğin İngilizce arayüzdeki Türkçe resmî belge adları, kendi `lang` özniteliğiyle işaretlenir (SC 3.1.2). Dil bağlantısı her sayfanın başında aynı yerdedir, form verisini korur ve tercih hesaba kaydedilir; bildirimler seçilen dilde gider. Resmî karar yazıları Türkçedir; İngilizce arayüzde yanında bilgi amaçlı özet gösterilir.

## 11. Hata yönetimi ve dayanıklılık

Uygulama tüm hataları yakalar ve güvenli duruma geçer: yetkilendirme hatasında istek reddedilir, kimlik doğrulama hatasında oturum açılmaz, ödeme sonucu belirsizse başvuru "ödendi" olmaz (Rehber 3.2.8.1; ASVS V16.5.3). Kullanıcıya yığın izi, sorgu ya da sürüm içermeyen genel mesaj ve ilişki kimliği gösterilir (ASVS V16.5.1); ayrıntı yalnızca kayda gider. Yakalanmamış istisnalar için son çare işleyici vardır (ASVS V16.5.4). Dış bağımlılıklar için devre kesici ve kademeli işlev kaybı tasarlanmıştır (ASVS V16.5.2):

| Bağımlılık | Kesintide davranış |
|---|---|
| e-Devlet Kapısı | Vatandaş girişi yapılamaz; açık oturumlar sürer; alternatif kanallar gösterilir |
| MNKS | Taslak kaydedilir, doğrulama kuyruğa alınır; doğrulama bitmeden gönderim yapılamaz |
| TSBS | Son başarılı yetki doğrulaması 30 günden yeniyse kabul edilir, değilse işlem bekletilir |
| KÖA | Başvuru 72 saat "ödeme bekliyor" durumunda kalır; mutabakat işi belirsiz işlemleri 15 dakikada bir sorgular |
| Bildirim Ağ Geçidi | Mesajlar kuyrukta bekler; 24 saatte iletilemeyen kritik bildirim portal gelen kutusunda gösterilir |
| KBYS | Belgeler nesne deposunda kalır, sonradan eşitlenir |

Ödemede KÖA'nın 3-D Secure sayfasına yönlendirilir; kart verisi VBP'ye gelmez. Sonuç yalnızca imzası doğrulanan sunucu bildirimiyle kabul edilir; mükerrer ödeme tekil işlem anahtarıyla önlenir.

## 12. Yedekleme ve kurtarma

Yedekleme planı yedeklenen sistemleri, işlem adlarını, zamanlarını, türünü, periyodunu ve sürümlemeyi tanımlar ve yılda bir gözden geçirilir (Rehber 3.1.13.1; 3.1.13). CP-9 değerleri: veri tabanı her gece tam yedeklenir ve işlem günlükleri sürekli arşivlenir; nesne deposu sürümlüdür, FKM'ye sürekli çoğaltılır ve günlük anlık görüntüsü alınır; sistem düzeyi bilgiler (altyapı kodu, yapılandırma) her değişiklikte ve haftalık, dokümantasyon haftalık yedeklenir. Günlük yedekler 35 gün, aylık yedekler 12 ay saklanır. Yedekler şifreli, değiştirilemez (WORM) ve birincil merkezden farklı konumdadır; erişimleri kaydedilir (CP-9(d); Rehber 3.1.13, "Yedekleme Medyalarının Saklanması, Güvenliği ve İmhası"; 4.1.5.5).

RPO 15 dakika, RTO 4 saattir (CP-10); başvuru ve ödeme verisi önce geri yüklenir. Yedekten dönüş testi 3 ayda bir yapılır ve tarih, kapsam, sonuç ve sorunlar kaydedilir (Rehber 3.1.13, "Yedekten Geri Dönüş Testleri"). FKM tatbikatı yılda bir yapılır (Rehber 3.1.13.15) ve Ocak tepesine denk getirilmez. Felaket kurtarma planı asgari envanteri, normale dönüş adımlarını ve KÖA ile Bildirim Ağ Geçidi sağlayıcılarının sorumluluklarını içerir (Rehber 3.1.13, "Felaket Kurtarma Planlarının Hazırlanması").

## 13. Standart çatışmaları ve çözümleri

| No | Konu | Çatışan hükümler | Karar | Yöneten | Gerekçe |
|---|---|---|---|---|---|
| Ç-1 | Parola en kısa uzunluğu | ASVS V6.2.1: en az 8, 15 öneri. 800-63B-4 §3.1.1.2(1): tek faktörde 15, çok faktörlü süreçte 8 | 15 karakter | 800-63B-4 §3.1.1.2(1), tek faktör hükmü | AAL2 yeniden doğrulamada parola tek başına kullanılabiliyor (§2.2.3) |
| Ç-2 | Parola geçerlilik süresi | Rehber 3.2.1.8: en uzun geçerlilik tanımlanmalı. 800-63B-4 §3.1.1.2(6), ASVS V6.2.10: periyodik değişiklik yasak | 365 gün; yalnızca yerel parolalar; 14 gün önce bildirim; ele geçirmede derhal değişim | Rehber | Genelge kapsamında bağlayıcı; NIST/ASVS sapması DIAS'ta |
| Ç-3 | Kilitleme ve yavaşlatma | AC-7 ve Rehber 3.2.1.1 kilitleme seçeneği sunar. 800-63B-4 §3.2.2, ASVS V6.1.1 kötü niyetli kilitlemeyi önlemeyi ister | Dış kullanıcıda artan gecikme ve bot sorgusu, 50 denemede doğrulayıcı devre dışı; personelde 10 denemede yönetici kilidi | Dış kullanıcı: 800-63B-4 §3.2.2; personel: AC-7 | Dış hesaplar hizmet engellemeye açık; personel doğrulayıcısında deneme saldırı göstergesi |
| Ç-4 | CAPTCHA | Rehber 3.2.1.9 CAPTCHA'yı örnek sayar. WCAG 2.2 SC 3.3.8 bilişsel testi sınırlar | Metin CAPTCHA yok; etkileşimsiz kanıt, gerekirse nesne tanıma | WCAG 2.2 SC 3.3.8 | Rehber örneği bağlayıcı değil; amaç gecikmeyle de karşılanıyor |
| Ç-5 | TOTP kabul penceresi | ASVS V6.5.5: en çok 30 sn. 800-63B-4 §3.1.4.2: kayma, gecikme ve giriş süresi dikkate alınmalı | Geçerli ve bir önceki adım (en çok 59 sn) | 800-63B-4 §3.1.4.2 | Tek kullanım ve hız sınırı telafi edici |
| Ç-6 | Toplam oturum süresi | WCAG 2.2 SC 2.2.1: zaman sınırı uzatılabilmeli. 800-63B-4 §2.2.3, §2.3.3: kesin toplam süre | Hareketsizlikte uzatma; toplam süre uzatılamaz, 5 dk önce uyarı, veri kaybı olmadan yeniden doğrulama | 800-63B-4 | Kabul edilmiş erişilebilirlik sapması |
| Ç-7 | Parola onay alanı | Rehber 3.2.1.8 onay ister. WCAG 2.2 SC 3.3.7 tekrar girişi sınırlar | Onay alanı ve parolayı gösterme seçeneği | Rehber | SC 3.3.7 güvenlik istisnası |
| Ç-8 | Kriptografik modül onayı | 800-63B-4 §2.2.2, §2.3.2: FIPS 140 doğrulaması. Rehber 3.2.10: TS ISO/IEC 19790 onaylı modül | TS ISO/IEC 19790 onaylı modüller | Rehber | KHGM politikası FIPS 140 şartını aynı temelli onayla karşılanmış sayar |
| Ç-9 | Personel IAL | 800-63-4 §3.3.3.1: yüksek etkide IAL3 | IAL2 ve telafi edici kontrol (yüz yüze İK kanıtlaması, güvenlik soruşturması) | 800-63-4 §3.4.2 | KHGM-VBP-KIB-001 Bölüm 11 |

## 14. Parametre tablosu

| Parametre | Değer | Dayanak | Gerekçe |
|---|---|---|---|
| Parola en kısa uzunluğu | 15 karakter (Unicode kod noktası) | 800-63B-4 §3.1.1.2(1); ASVS V6.2.1 | Ç-1 |
| Parola en uzun uzunluğu | 128 karakter | 800-63B-4 §3.1.1.2(2); ASVS V6.2.9 | Parola cümleleri |
| Parola bileşim kuralı | Yok | IA-5(1)(h); 800-63B-4 §3.1.1.2(5) | Güvenliği artırmıyor |
| Parola en uzun geçerlilik süresi | 365 gün; 14 gün önce bildirim | Rehber 3.2.1.8; ASVS V6.4.5 | Ç-2 |
| Yasaklı parola listesi güncelleme | 3 ayda bir ve sızıntı şüphesinde | IA-5(1)(a); ASVS V6.2.12 | Yeni sızıntılar |
| Başarısız giriş sınırı (AC-7a) | 15 dakikada 10 ardışık deneme | AC-7; Rehber 3.2.1.9 | Ç-3 |
| Sınır aşımı eylemi (AC-7b, dış kullanıcı) | Gecikme 1 dk, her başarısızlıkta 2 kat, en çok 60 dk | AC-7; 800-63B-4 §3.2.2 | Kötü niyetli kilitlemeyi önlemek |
| Bot doğrulama sorgusu eşiği | Hesapta 5 ardışık başarısızlık veya IP başına 10 dakikada 20 | 800-63B-4 §3.2.2; Rehber 3.2.1.9 | Otomasyonu erken ayırmak |
| Doğrulayıcı devre dışı bırakma eşiği | 50 ardışık başarısız deneme | 800-63B-4 §3.2.2 (≤100) | Üst sınırın yarısı |
| Personel başarısız giriş sınırı | 10 ardışık deneme; yönetici kaldırana kadar kilit, SOME alarmı | AC-7; Rehber 3.2.1.1 | Ç-3 |
| TOTP | 6 hane; 30 sn adım; geçerli ve bir önceki adım | 800-63B-4 §3.1.4.2; ASVS V6.5.5 | Ç-5 |
| SMS tek kullanımlık kod | 6 hane; 5 dakika | 800-63B-4 §3.1.3.2 (≤10 dk) | Kısıtlı doğrulayıcı |
| SMS gönderim sınırı | Hesap başına saatte 5, günde 10 | 800-63B-4 §3.1.3.2; ASVS V2.4.1 | Maliyet istismarı |
| E-posta doğrulama ve kurtarma kodu | 60 dakika | 800-63A-4 §3.8; 800-63B-4 §4.2.1.2 (≤24 sa) | Yeterli erişim süresi |
| Kayıtlı kurtarma kodu | 80 bit (16 karakter Base32), tek kullanımlık | 800-63B-4 §4.2.1.1 (≥64 bit) | Elle girişe uygun |
| AAL2 hareketsizlik zaman aşımı | 30 dakika; 25. dakikada uyarı | 800-63B-4 §2.2.3 (≤1 sa); AC-12 | Paylaşılan bilgisayarlar |
| AAL2 toplam oturum süresi | 12 saat | 800-63B-4 §2.2.3 (≤24 sa); AC-12 | Bir iş günü |
| AAL3 hareketsizlik zaman aşımı | 15 dakika; 8. dakikada uyarı, 10. dakikada ekran kilidi | 800-63B-4 §2.3.3; AC-12 | NIST önerisi |
| AAL3 toplam oturum süresi | 10 saat | 800-63B-4 §2.3.3 (≤12 sa); AC-12 | Mesai ve fazla mesai |
| Arka ofis ekran kilidi | 10 dakika; açma yalnızca AAL3 ile | AC-11 | Açık ekranda kişisel veri |
| Zaman aşımı uyarısında uzatma süresi | En az 120 saniye; uzatma sınırsız; toplam süre bitiminden 5 dakika önce yeniden doğrulama uyarısı | WCAG 2.2 SC 2.2.1 (≥20 sn, ≥10 kez) | Yardımcı teknoloji kullanıcıları |
| Hassas işlem yeniden doğrulama tazeliği | Son 5 dakika | IA-11; Rehber 3.2.1.10; ASVS V7.5.1 | Oturum ele geçirme etkisi |
| Eşzamanlı oturum sınırı | Vatandaş/temsilci 3; personel 1; sistem yöneticisi 1 | AC-10; ASVS V7.1.2 | Çok cihaz ile kötüye kullanım dengesi |
| Parola tuzu ve TOTP tohumu | Tuz en az 128 bit; TOTP tohumu en az 160 bit | 800-63B-4 §3.1.1.2 (tuz ≥32 bit), §3.1.4.1 (≥112 bit) | Asgarinin üstünde pay |
| HSTS süresi | En az 1 yıl, alt alan adları dahil | ASVS V3.4.1; Rehber 3.2.9.3 | Protokol düşürme saldırıları |
| Oturum belirteci entropisi | En az 128 bit | 800-63B-4 §5.1 (≥64); ASVS V7.2.3 | ASVS daha katı |
| Federasyon belirteci geçerlilik penceresi | 5 dakika; saat kayması 60 sn | 800-63C-4 §2.3; ASVS V10.5.1 | Tekrar oynatma penceresi |
| Temsilci hesabı pasifleştirme | 24 ay kullanılmama | Rehber 3.2.1.12; AC-2(3) | 1-2 yıllık lisans dönemleri |
| Personel hesabı devre dışı bırakma | 45 gün kullanılmama; ayrılışta 4 saat | AC-2(3); Rehber 3.1.12 | Yetkisiz erişim penceresi |
| Acil erişim süresi | En çok 8 saat; ertesi iş günü inceleme | AC-2(3); Rehber 3.2.3 | Olağanüstü durum ile en az yetki dengesi |
| Toplu dışa aktarım sınırı | Günde 5 işlem; birim yöneticisi onayı | Rehber 3.2.7.4; ASVS V2.4.1 | Toplu veri sızıntısı riski |
| Temsil yetkisi yeniden doğrulama | Yılda bir ve TSBS değişikliğinde; TSBS kesintisinde son doğrulama 30 güne kadar geçerli | ASVS V16.5.2; Rehber 3.2.11 | Yetkisiz temsil riski ile süreklilik dengesi |
| Yetki gözden geçirme | Ayrıcalıklı 3 ay; diğer 6 ay | Rehber 3.1.12; ASVS V8.1.1 | Yıllık beklentinin üstünde |
| Güvenlik iz kaydı saklama (AU-11) | 2 yıl (1 yıl çevrim içi, 1 yıl arşiv) | AU-11; Rehber 3.1.8.1 | KHGM politikası |
| Kişisel veri erişim kaydı saklama | 2 yıl | Rehber 4.1.2.2 | KHGM politikası |
| Hata ayıklama kaydı saklama | 30 gün | Rehber 3.1.8.1 | Sorun giderme |
| Kayıt inceleme (AU-6) | SIEM sürekli; ayrıcalıklı işlemler her iş günü; genel haftalık | AU-6; Rehber 3.1.8.2 | Erken tespit |
| Kayıt depolama kapasitesi (AU-4) | 2 yıllık hacim + %30 pay | AU-4; Rehber 3.1.8.5 | Kayıt kaybını önlemek |
| Kayıt hatası uyarısı (AU-5) | 15 dakika içinde; depolama %80'de | AU-5; Rehber 3.1.8.6 | Kayıt kaybını önlemek |
| Zaman damgası (AU-8) | UTC, milisaniye; iki iç NTP | AU-8; Rehber 3.1.8.3 | Korelasyon |
| İzin verilen dosya türleri | PDF (PDF/A dahil), JPEG, PNG | ASVS V5.1.1; Rehber 3.2.4.5 | En dar küme |
| Dosya boyutu ve sayısı | Dosya 10 MB; başvuru 20 dosya/50 MB; hesap 500 MB; görüntü ≤40 MP | ASVS V5.2.1, V5.2.4, V5.2.6 | Taranmış belge boyutları |
| Zararlı dosya karantinası | 30 gün; aynı hesaptan 24 saatte ikinci olayda SOME alarmı | ASVS V5.1.1, V5.4.3; Rehber 3.2.4.5 | İnceleme olanağı |
| Dosya yükleme hız sınırı | Kullanıcı başına saatte 60 dosya | ASVS V2.4.1; Rehber 3.2.11.8 | Tarama kaynakları |
| API hız sınırı | Oturumlu 120 istek/dk (anlık 30); anonim 60 istek/dk/IP; kimlik doğrulama uçları 20 istek/dk/IP | Rehber 3.2.11.8; ASVS V2.4.1 | Tepe kapasitesini korumak |
| Parola sıfırlama talep sınırı | Hesap başına saatte 3; IP başına saatte 10 | Rehber 3.2.1.9; ASVS V6.1.1 | E-posta bombardımanı |
| Taslak başvuru saklama | 90 gün; silmeden 7 gün önce bildirim | Rehber 4.1.1.2; ASVS V14.2.7 | Veri en aza indirme |
| Ödeme ve iade kaydı saklama | 10 yıl | SI-12; Rehber 4.1.1.2 | KHGM politikası |
| Bildirim gönderim kaydı saklama | 2 yıl | SI-12; Rehber 4.1.1.2 | KHGM politikası |
| Pasif temsilci hesabının silinmesi | Pasifleştirmeden itibaren 12 ay | Rehber 3.2.1.12, 4.1.1.2 | Hesap kimlik verisinin gereksiz tutulmaması |
| Başvuru dosyası saklama | Kapanıştan itibaren 10 yıl | SI-12; Rehber 4.1.1.2 | KHGM politikası |
| Periyodik imha | 6 ayda bir | Rehber 4.1.5.4 | KHGM politikası |
| Yedekleme (CP-9) | Veri tabanı günlük tam + sürekli işlem günlüğü; nesne deposu sürekli çoğaltma + günlük anlık görüntü; sistem düzeyi her değişiklik + haftalık; dokümantasyon haftalık | CP-9; Rehber 3.1.13.1 | RPO hedefi |
| Yedek saklama | Günlük 35 gün; aylık 12 ay; WORM | CP-9(d); Rehber 3.1.13 | Fidye yazılımı, hatalı silme |
| RPO / RTO (CP-10) | 15 dakika / 4 saat | CP-10; Rehber 3.1.13 | Ödeme ve başvuru verisi |
| Geri dönüş ve FKM testi | Geri dönüş 3 ayda bir; FKM yılda bir | Rehber 3.1.13, 3.1.13.15 | Yedeklerin kullanılabilirliği |
| Hizmet erişilebilirlik hedefi | Aylık %99,5; bakım Pazar 02:00-05:00, en az 3 gün önce duyuru | GOV.UK Service Standard madde 14; CP-2 | En düşük trafik |
| Ödeme bekleme süresi | 72 saat; belirsiz işlemler 15 dakikada bir sorgulanır | ASVS V16.5.2 | KÖA kesintisi |
| Kritik bildirim yedek gösterimi | 24 saatte iletilemeyen bildirim portal gelen kutusunda | ASVS V16.5.2 | Bildirim ağ geçidi kesintisi |
| Ek belge yanıt süresi | 15 gün; süre dolmadan bir hatırlatma | KHGM iş kuralı (Hizmet Sahibi) | Dosyanın makul sürede sonuçlanması |
| Yama süresi (SI-2) | Kritik 7 gün; yüksek 30 gün | SI-2; Rehber 3.2.5 | İnternete açık sistem |
| Zafiyet taraması (RA-5) | Haftalık tarama; yılda bir ve büyük sürüm öncesi sızma testi | RA-5; Rehber 3.1.11 | Düzenli test |
| Olay bildirimi (IR-6) | Personel 1 saat içinde KHGM SOME'ye | IR-6; Rehber 3.1.10 | Hızlı müdahale |
| Oturum çerezi | `__Host-vbp_sid`; Secure; HttpOnly; Path=/; SameSite=Lax (portal) / Strict (arka ofis) | 800-63B-4 §5.1.1; ASVS V3.3.1-V3.3.4; Rehber 3.2.2.4 | Arka ofiste dış bağlantı yok |

## 15. Varsayımlar ve açık konular

- e-Devlet'in `acr`, `amr`, `auth_time`, takma adlı tanımlayıcı ve arka kanal oturum kapatma sağlayacağı, güven anlaşması taslağına dayanan bir varsayımdır; sağlanmazsa sınırlı kip ve VBP tarafı yeniden doğrulama uygulanır.
- KÖA sonuç bildirim imzası ve test ortamı sözleşme ekinde teyit edilecektir.
- Özel nitelikli veri isteyen hizmetler (H-02, H-04) için veri en aza indirme çalışması Alfa'da tamamlanacaktır.
- SMS'in kısıtlı doğrulayıcı olarak ne zaman kaldırılacağı, ilk canlı yılın sonunda TOTP ve geçiş anahtarı kullanım oranına göre değerlendirilecektir (800-63B-4 §3.2.9).
