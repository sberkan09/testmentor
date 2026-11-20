# Paket 1b: altın set v1, belge derlemi

Model: Opus (tasarım), alt ajanlar (belge tarama). Önkoşul: paket 1 (PR #2 birleşti).

## Amaç

Stüdyoda projelere tasarım dokümanları, standartlar ve proje yönetim planı gibi belgeler eklenecek; testler bu geniş bağlamla yazılacak. Altın set v0 bu durumu ölçemiyor: 40 kısa sentetik gereksinim, belge yok. Bu paket gerçek bir durumu simüle eden iki proje ekler. Her projede kamuya açık bir belge derlemi ve ondan türetilen en az 100 gereksinim bulunur.

| Proje | Anahtar | Dil | Belgeler | Referans testlerin kaynağı |
| --- | --- | --- | --- | --- |
| Kamu dijital hizmeti (vatandaş başvuru portalı: kimlik doğrulama, güvenlik, erişilebilirlik, kişisel veri) | `KDH` | Türkçe ve İngilizce | NIST SP 800-63-4 (dört cilt) ve uygunluk kriterleri v0.1, NIST SP 800-53 Rev.5 (OSCAL 5.2.0) ve 800-53A (XLSX), OWASP ASVS 5.0, WCAG 2.2 ve W3C ACT kuralları (37 onaylı), Bilgi ve İletişim Güvenliği Rehberi ve isteğe bağlı Denetim Rehberi (Siber Güvenlik Başkanlığı, v1.1, CC BY 4.0), GOV.UK Service Standard; sisteme özgü sentetik belgeler (kavramsal işletim, proje yönetim planı, tasarım) | 800-63-4 uygunluk kriterleri (TEST/EXAMINE/INTERVIEW), ACT kuralları (Applicability ve Expectation), Rehber "Denetim Maddeleri", 800-53A hedefleri; ASVS ve kalanı Claude yazar ve işaretlenir |
| ERTMS/ETCS araç üstü birimi | `ETC` | İngilizce | ERA: SUBSET-026 (SRS, 9 bölüm), SUBSET-023 (sözlük), SUBSET-036 ve 037-1 (arayüz), SUBSET-041 (performans), SUBSET-091 (emniyet); isteğe bağlı SUBSET-027 (JRU) ve ERA_ERTMS_015560 (DMI); cevap anahtarı SUBSET-076-5-2 ve 076-7. CCS TSI çıkarıldı (aşama 3) | SUBSET-076 resmî test vaka ve dizileri |

## Kurallar

- Kurum verisi girmez. Kamuya açık belgeler ve onlardan türetilen gereksinimler kullanılır (CLAUDE.md "Veri ve Runpod" bu paketle güncellendi).
- Ücretli standartlar (ISO, IEC, EN, DO-178C) kullanılmaz.
- Belgeler depoya konmaz. `eval/corpus/<proje>/manifest.yaml` her belgenin adresini, SHA-256'sını, lisansını, türünü ve dilini tutar; `python -m eval.corpus fetch` indirir ve metni çıkarır (`eval/corpus/cache/`, depoya girmez). Lisansı açık belgelerin çıkarılmış metni depoya alınabilir.
- Cevap anahtarı test yazarından ayrılır. Derlem listesinde her belgenin `role` alanı vardır: `corpus` test yazarına verilir; `reference` (SUBSET-076, 800-63-4 uygunluk kriterleri, 800-53A, ACT kuralları) hiçbir koşulda verilmez; `mixed` belgelerde (`SGB-REHBER-1.1` "Denetim Maddeleri" tabloları, OSCAL 800-53 kataloğunun değerlendirme bölümleri) `reference_parts` ile işaretlenen kısımlar test yazarına giden metinden çıkarılır. Paket 7'nin parçalama ve indeks kodu bu alanı uygular. Altın parça seçerken bu kısımlardan parça alınmaz.
- ERTMS metinlerinin yeniden kullanım koşulu belirsiz (UNISIG telif ibaresi, izin yok). Kullanıcı 20 Kasım 2026'da onayladı: depo özel olduğu sürece ERTMS'ten türetilen metin (gereksinimler, referans testler, çıkarılmış belge metni, deney çıktıları) git'e girebilir. Depo herkese açılırsa bu karar yeniden ele alınır.
- Gereksinimler gerçek bir gereksinim belgesi gibi standarda atıf yapar; eşik ve prosedür belgede kalır. Cümle zaten "15 karakter" diyorsa bilgi havuzu bir şey eklemez.
- Sentetik sistem belgelerini bir alt ajan, standartlardan ve sistem özetinden, referans testleri görmeden yazar; ilgisiz içerik de içerir. Aksi hâlde belgeler cevap anahtarına dönüşür.
- v0 dosyaları değişmez; v1 yeni dosyalardır. Gereksinim kimlikleri `<ANAHTAR>-NNN` biçimindedir; ERTMS madde numarası ayrı alanda durur.

## Altın set v1 alanları (v0'a ek)

Gereksinim başına:
- `source`: belge ve bölüm (ör. SUBSET-026 §3.4.2.1).
- `reference_origin`: `official` (resmî test ya da prosedürden) ya da `claude`.
- `support_passages`: referans testleri yazmak için gereken belge parçalarının kimlikleri (altın parçalar).
- `needs_documents`: gereksinim cümlesinden tek başına yazılamayan denetim var mı.
- `reference_cluster`: ERTMS'te SRS bölüm başlığı; kamu projesinde standart alanı.
- `verification_methods`: ERTMS'te SUBSET-076-7'nin test edilemez gereksinim tablosundan, kamu projesinde 800-53A yöntem etiketlerinden türetilir (eşleme raporda gerekçelendirilir).

Hakem sonuçları bu katmanlara göre ayrı raporlanır: resmî ya da Claude referansı, belge gerektiren ya da gerektirmeyen.

## Aşamalar ve durum

Her aşama ayrı commit. Oturum yeniden başlarsa durum buradan okunur.

| No | Aşama | Durum |
| --- | --- | --- |
| 0 | Dal, paket tanımı, tasarım notu, CLAUDE.md güncellemesi | bitti (CLAUDE.md değişikliği ve ERTMS metninin depoya girmesi kullanıcı onaylı) |
| 1 | Deneme 1: ERTMS izlenebilirliği | bitti. Test vakaları "Based on Requirements" hücresinde SUBSET-026 maddelerini alt madde ve tablo satırı düzeyinde listeliyor (çoka çok; test vakası başına medyan 2 madde). Özellik kimliği SRS bölüm numarasıdır (3060300 = §3.6.3). 076-6-3 dizileri madde değil test vakası gösterir. Adımlar içerik eklemeden aktarılabilir: I satırı → eylem, ardından gelen O satırları ve yorum → beklenen sonuç, başlangıç koşulları → ön koşul. İstisnalar: 110 test vakasında I satırı yok; 652'sinde `Use_FT` (başka test vakasını çağırma) var, açılması gerekir. Beklenen sonuçlar arayüz düzeyinde (RTM mesajları, JRU kayıtları). Önerilen bölüm §3.6–3.8 (konum, hat tanımı, hareket yetkisi): 109 madde bir test vakasında geçiyor, 57'sinin yalnızca bölüm içine atıf yapan test vakası var; 100'e ulaşmak için kapsamı bölüm dışına taşan test vakaları kabul edilir. Tablo 3: yaklaşık 88 test edilemez satır, yöntem sütunu yok; Analiz/İnceleme/Gösterim eşlemesi bizim yorumumuz olur. Çıktılar: `eval/corpus/etc/probe/` |
| 2 | Deneme 2: 10 gereksinim (5 ERTMS, 5 kamu), resmî referans denetimleri (alt ajan A), referansları görmeyen test yazarı (alt ajan B), hakem | bitti, sonuçlar `eval/golden/spike2/`. **Belge etkisi açık:** üç bağımsız hakem örneğinde recall r1 ile belgeli 0,58–0,63, belgesiz 0,29; r2 ile belgeli 0,71, belgesiz 0,18–0,24. Hakem gürültüsü ±0,05. Bu bir **kâhin tavanıdır**: belge parçalarını referansı bilen ajan seçti, testleri Claude yazdı, temiz test vakaları seçildi. Tavanda bile ERTMS belgeli 0,40–0,47 (kamu 0,70–0,87). ERTMS kayıplarının bilinen nedenleri: (a) beklenen sonuçların bir kısmı derlemde olmayan kayıt cihazı ve sürücü ekranı spesifikasyonlarına dayanıyor; (b) resmî denetim davranışı tek bir somut senaryoyla doğruluyor, üretilen test genel yazıyor; (c) çoka çok test vakaları gereksinim dışı maddeleri de doğruluyor (ETC-905). **r2 benimsenmedi:** bu 10 maddeye bakılarak yazıldı; varsayılan rubrik r1 kalır. `eval/judge.py` artık `rubric_version`'a göre metni seçer; v0 r1'de kalır, rubrikler arası karşılaştırma yapılmaz. |
| 2a | Kamu kaynaklarının birincil belgeden doğrulanması | bitti. Rehber'in tedbir başına "Denetim Maddeleri" tabloları (63 tablo, yöntem ve soru) Denetim Rehberi'nde değil Rehber'de; Denetim Rehberi yalnızca yöntem anlatır. NIST 800-63-4 uygunluk kriterleri v0.1 (1.024 kriter, 63B için 313; her biri TEST/EXAMINE/INTERVIEW yönergeli) resmî referans kaynağı olarak eklendi. 800-53A yöntemleri kontrol başına etiketli, gereksinim ayırt etmez; yöntem etiketleri Rehber'in tedbir başına yöntemlerinden (Mülakat, Gözden Geçirme, Güvenlik Denetimi, Sızma Testi, Kaynak Kod Analizi) türetilir. ASVS 5.0.0: 345 gereksinim, test prosedürü yok (Claude referansı). ACT: 37 onaylı kural; insan test yönergesi Applicability ve Expectation, örnekler denetleyici araçlar içindir; başarısızlık SC ihlali, geçme yalnızca "daha fazla test gerekir". KVKK sitesi bu konteynerden erişilemiyor (sertifika); İngilizce metin DOĞRULANAMADI, derlemden çıkarıldı ya da kullanıcıdan istenecek. Standartlar arası çelişkiler var (parola uzunluğu ASVS 8 / NIST 15; Rehber parola süresi / NIST periyodik değişiklik yok): gerçekçi bir özellik, hangi standardın geçerli olduğunu proje belgeleri belirler. Metin çıkarma tuzakları: Rehber'de `-layout` denetim sorularını yanlış tedbire atıyor; 800-53A PDF'inde "ti" bağları düşüyor (XLSX kullanılır). | 
| 3 | Derlem listesi ve indirme/çıkarma betiği; araştırmada yalnızca arama özetinden doğrulanan iddialar birincil belgeden yeniden kontrol edilir | bitti. `eval/corpus/{etc,kdh}/manifest.yaml` (şema `eval/corpus/manifest.py`), komut `python -m eval.corpus list|fetch|verify`, önbellek `eval/corpus/cache/` (git dışı). ETC 18 belge (10 indirme, 225 metin dosyası; SUBSET-076-5-2 SV30 208 PDF), KDH 13 belge (11 indirme, 63 metin dosyası). Bütün 21 indirmenin SHA-256'sı sabit; boş önbelleğe iki bağımsız indirmede hepsi tuttu. Sabitleme: OSCAL kataloğu ve ASVS commit adresinden, WCAG 2.2 tarihli TR adresinden. Değişebilen sayfalar (ACT kuralları, GOV.UK) değiştirilmemiş metin olarak depoda (`eval/corpus/kdh/snapshots/`, lisans notu README'de); kaynak commit ve tarih `origin` alanında. Lisanslar birincil belgeden kontrol edildi (`license_evidence`): ERA belgelerinde yeniden kullanım izni yok (yalnızca 'ERA * UNISIG * EEIG ERTMS USERS GROUP' ibaresi; `private_only`), NIST kamu malı, Rehber ve Denetim Rehberi CC BY 4.0, ASVS CC BY-SA 4.0, W3C Document License, GOV.UK OGL v3. Çıkarılanlar ve gerekçeleri listenin `excluded` alanında: CCS TSI (EUR-Lex bot koruması, içerik dönmüyor), SUBSET-076-6-3, CENELEC/ETSI, KVKK (sertifika hatası), 800-53A PDF. Denetim kaybı analizindeki iki açık nokta doğrulandı: §3.6.5.1.4 SUBSET-026-3'te var; DMI belgesi ERA_ERTMS_015560 v4.0.0 (ERA dizini index006). Analizin 'derleme eklenecekler' listesi (SUBSET-026-8, 026-7 §7.4, §3.10.2, §4.8) zaten SUBSET-026 zip'inde: eksik derlem değil, **destek parçası seçimi**ydi; aşama 5 parçaları denetim başına seçerken bunu düzeltir. |
| 4 | Gereksinimler: proje başına ≥100. ERTMS'te önce resmî testi olan maddeler seçilir, tek tutarlı bölümden; yöntem çeşitliliği için test edilemez maddeler eklenir. **Kullanıcıya gösterilir.** | bekliyor |
| 5 | Referans testler ve denetimler. **Başlamadan önce kapılar:** (1) 15 ERTMS denetiminin her kaybı sınıflanır: derlem eksiği, senaryo özgüllüğü, test yazarının gerçek kaçırması, hakem hatası; yalnızca üçüncüsü sinyaldir. *Yapıldı (`eval/golden/spike2/audit_ertms.md`): 5 denetim her örnekte eşleşti; 10 kaybın 4'ü çoka çok, 3'ü senaryo özgüllüğü, 1'i derlem eksiği, 1'i tartışmalı hakem hatası, yalnızca 1'i gerçek yazar kaçırması. Üç örnek tek üretimin üç hakem koşusudur; yazar sinyali tek üretime dayanır. Sonuç: beklenen sonuç önce davranış çekirdeği olarak yazılır, kayıt cihazı ve ekran ayrıntısı ayrı kanal notuna gider; her denetim doğruladığı SRS maddesiyle etiketlenir, kapsam dışı denetim düşer; madde başına en az 3 bağımsız üretim. Derleme eklenecekler: SUBSET-026-8 (mesaj listesi), SUBSET-026-7 §7.4 (paket listesi), §3.10.2, §4.8 ve TAF maddesi.* (2) Destek parçaları denetim başına bağlanır; derlemde karşılığı yoksa açıkça "derlemde yok" yazılır ve bu denetimler ayrı raporlanır ya da ilgili spesifikasyonlar (SUBSET-027, DMI) derleme eklenir. (3) Çoka çok test vakalarında değerlendirme birimi seçilir: yalnızca tek maddeli test vakaları ya da "Based on" listesi seçili kümenin içinde kalan test vakalarıyla madde grubu. Adımları maddelere Claude dağıtırsa `reference_origin` bunu gösterir. (4) Kontrol katmanı: `needs_documents=false` gereksinimler eklenir; bunlarda belgeli ve belgesiz fark çıkmamalı. (5) İlk ~20 gereksinim r1 ve r2 için görülmemiş doğrulama kümesidir. | bekliyor |
| 6 | Doğrulama: şema, kimlikler, katman dağılımları; pilot alt kümede "altın parçalı ve parçasız" karşılaştırması (pod gerekir, `make batch`) | bekliyor |

## Kapsam dışı

Parçalama, indeks ve arama kodu (paket 7). Bu paket yalnızca veriyi ve ölçülebilirliğini hazırlar.

## Bitti ölçütü

- İki proje, her biri ≥100 gereksinim, şemaya uygun; kimlikler ve kaynaklar tutarlı.
- Her gereksinimin referans kökeni ve belge gereksinimi işaretli; resmî referanslı gereksinim oranı raporlanmış.
- Derlem listesi tekrar indirilebilir ve özet değerleri tutuyor.
- Pilot ölçüm: belge gerektiren denetimlerde altın parçalı koşu parçasız koşudan anlamlı biçimde daha iyi. Değilse set D9'u ölçemiyor demektir; rapora yazılır.
