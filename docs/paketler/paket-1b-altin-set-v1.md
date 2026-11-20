# Paket 1b: altın set v1, belge derlemi

Model: Opus (tasarım), alt ajanlar (belge tarama). Önkoşul: paket 1 (PR #2 birleşti).

## Amaç

Stüdyoda projelere tasarım dokümanları, standartlar ve proje yönetim planı gibi belgeler eklenecek; testler bu geniş bağlamla yazılacak. Altın set v0 bu durumu ölçemiyor: 40 kısa sentetik gereksinim, belge yok. Bu paket gerçek bir durumu simüle eden iki proje ekler. Her projede kamuya açık bir belge derlemi ve ondan türetilen en az 100 gereksinim bulunur.

| Proje | Anahtar | Dil | Belgeler | Referans testlerin kaynağı |
| --- | --- | --- | --- | --- |
| Kamu dijital hizmeti (vatandaş başvuru portalı: kimlik doğrulama, güvenlik, erişilebilirlik, kişisel veri) | `KDH` | Türkçe ve İngilizce | NIST SP 800-63-4, NIST SP 800-53 Rev.5 ve 800-53A, OWASP ASVS 5.0, WCAG 2.2 ve W3C ACT kuralları, Bilgi ve İletişim Güvenliği Rehberi ve Denetim Rehberi (Siber Güvenlik Başkanlığı), KVKK (İngilizce resmî metin), GOV.UK Service Standard; sisteme özgü sentetik belgeler (kavramsal işletim, proje yönetim planı, tasarım) | ACT kuralları, 800-53A prosedürleri, Denetim Rehberi; kalanı Claude yazar ve işaretlenir |
| ERTMS/ETCS araç üstü birimi | `ETC` | İngilizce | ERA: CCS TSI, SUBSET-026 (SRS), SUBSET-041 (performans), SUBSET-036/037 (arayüz), SUBSET-091 (emniyet), SUBSET-076 (test) | SUBSET-076 resmî test vaka ve dizileri |

## Kurallar

- Kurum verisi girmez. Kamuya açık belgeler ve onlardan türetilen gereksinimler kullanılır (CLAUDE.md "Veri ve Runpod" bu paketle güncellendi).
- Ücretli standartlar (ISO, IEC, EN, DO-178C) kullanılmaz.
- Belgeler depoya konmaz. `eval/corpus/<proje>/manifest.yaml` her belgenin adresini, SHA-256'sını, lisansını, türünü ve dilini tutar; `python -m eval.corpus fetch` indirir ve metni çıkarır (`eval/corpus/cache/`, depoya girmez). Lisansı açık belgelerin çıkarılmış metni depoya alınabilir.
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
| 2 | Deneme 2: 10 gereksinim (5 ERTMS, 5 kamu: ACT, 800-53A, Denetim Rehberi ve Claude referanslı) hakemden geçer; rubrik r1 bu referanslarla çalışıyor mu | bekliyor |
| 3 | Derlem listesi ve indirme/çıkarma betiği; araştırmada yalnızca arama özetinden doğrulanan iddialar birincil belgeden yeniden kontrol edilir | bekliyor |
| 4 | Gereksinimler: proje başına ≥100. ERTMS'te önce resmî testi olan maddeler seçilir, tek tutarlı bölümden; yöntem çeşitliliği için test edilemez maddeler eklenir. **Kullanıcıya gösterilir.** | bekliyor |
| 5 | Referans testler ve denetimler | bekliyor |
| 6 | Doğrulama: şema, kimlikler, katman dağılımları; pilot alt kümede "altın parçalı ve parçasız" karşılaştırması (pod gerekir, `make batch`) | bekliyor |

## Kapsam dışı

Parçalama, indeks ve arama kodu (paket 7). Bu paket yalnızca veriyi ve ölçülebilirliğini hazırlar.

## Bitti ölçütü

- İki proje, her biri ≥100 gereksinim, şemaya uygun; kimlikler ve kaynaklar tutarlı.
- Her gereksinimin referans kökeni ve belge gereksinimi işaretli; resmî referanslı gereksinim oranı raporlanmış.
- Derlem listesi tekrar indirilebilir ve özet değerleri tutuyor.
- Pilot ölçüm: belge gerektiren denetimlerde altın parçalı koşu parçasız koşudan anlamlı biçimde daha iyi. Değilse set D9'u ölçemiyor demektir; rapora yazılır.
