# Altın set v1, Deneme 2: 10 resmî referanslı madde

Paket 1b, aşama 2'nin ilk yarısı (20 Kasım 2026). Amaç, rubrik r1'in resmî kaynaktan aktarılmış referans denetimlerle çalışıp çalışmadığını hakemle sınamak. Dosya: `items.json` (JSON listesi, 10 madde).

## Alanlar

v1 alanlarına ek olarak her madde şunları taşır:

- `reference_basis`: denetimlerin alındığı resmî belge.
- `reference_preconditions`: yalnızca ERTMS maddelerinde, test vakasının başlangıç koşulları.
- `method_rationale`: doğrulama yöntemi eşlemesinin gerekçesi.

Denetimler yalnızca yeniden gruplanarak aktarıldı:

- ERTMS: I satırı eylem, onu izleyen O satırları ve yorumlar beklenen sonuç olur. Köşeli parantez arayüz sütunudur (BTM, RTM, JRU, DMI, ODO, INT).
- Destek parçaları (`support_passages`) normatif belgeden aynen alındı, denetimlerin kaynağı olan belgeden alınmadı. Sayfa üst ve alt bilgileri atıldı, boşluklar tek boşluğa indirildi. Doğrulama, her parçanın kaynak metnin alt dizgisi olduğunu ve ERTMS denetimlerindeki her sözcüğün ilgili test vakasında geçtiğini kontrol eder.

## Maddeler

| Kimlik | Gereksinim kaynağı | Referans denetimlerin kaynağı |
| --- | --- | --- |
| ETC-901 | SUBSET-026 §3.6.2.2.2 a) (LRBG) | SUBSET-076-5-2 Feature 3060200 TC2 |
| ETC-902 | SUBSET-026 §3.6.3.1.3 (geçerlilik yönü) | 3060300 TC6 |
| ETC-903 | SUBSET-026 §3.6.4.2.2.2 (bağlantı bilgisi ve SOLR sırası) | 3060400 TC20 |
| ETC-904 | SUBSET-026 §3.7.3.1 a) (SSP değiştirme) | 3070300 TC14 |
| ETC-905 | SUBSET-026 §3.8.2.2.2 ve §3.8.2.1.7 (MA isteğinin tetiklenmesi ve nedeni) | 3080200 TC7 |
| KDH-901 | NIST SP 800-63B-4 §3.1.1.2 (parola uzunluğu, tam doğrulama) | 800-63-4 uygunluk kriterleri v0.1: PV-1, PV-2, PV-7 |
| KDH-902 | NIST SP 800-63B-4 §3.2.2 (deneme sınırlama) | PV-12, RL-2, RL-3, RL-4 |
| KDH-903 | WCAG 2.2 SC 3.1.1 (A) | ACT kuralları b5c3f8 ve bf051a (onaylı sürümler), Applicability + Expectation |
| KDH-904 | SGB Rehber v1.1 tedbir 3.2.2.3 (Türkçe) | Rehber 3.2.2 Denetim Maddeleri, 3.2.2.3 soruları |
| KDH-905 | NIST SP 800-53 Rev. 5 AC-7 | 800-53A Rev. 5 AC-07 değerlendirme hedefleri (yalnızca hedefler var) |

Kaynak sürümleri:

- SUBSET-026 v4.0.0 ve SUBSET-076-5-2 v4.0.0 (SV30), ERA ETCS B4 R1 dizini.
- SUBSET-076-7 Tablo 3'te bu maddelerin hiçbiri yok. Bu yüzden ERTMS yöntemi Test.

## Lisans ve atıf

- **ERTMS (SUBSET-026, SUBSET-076):** © ERA, UNISIG, EEIG ERTMS Users Group. Yeniden kullanım izni yok. Kullanıcı 20 Kasım 2026'da onayladı: depo özel kaldığı sürece türetilmiş metin depoya girebilir. Depo herkese açılırsa bu klasördeki ETC maddeleri yeniden ele alınır.
- **NIST SP 800-63B-4, 800-63-4 uygunluk kriterleri, SP 800-53 Rev. 5 / 800-53A Rev. 5:** ABD federal hükümeti eseri, ABD'de kamu malı. Kaynak: NIST.
- **WCAG 2.2 ve W3C ACT kuralları:** © W3C (MIT, ERCIM, Keio, Beihang), W3C Software and Document Notice and License. ACT kural metni ACT Rules Community Group tarafından yazıldı ve AG WG tarafından onaylandı. Bu dosya şu belgelerden kopyalanmış ve türetilmiş içerik taşır: "HTML page has lang attribute" (https://www.w3.org/WAI/standards-guidelines/act/rules/b5c3f8/), "HTML page lang attribute has valid language tag" (https://www.w3.org/WAI/standards-guidelines/act/rules/bf051a/) ve WCAG 2.2 SC 3.1.1. Değişiklik: Applicability ve Expectation eylem ve beklenen sonuç biçimine getirildi.
- **Bilgi ve İletişim Güvenliği Rehberi v1.1:** © T.C. Cumhurbaşkanlığı Siber Güvenlik Başkanlığı, CC BY 4.0. Değişiklik: tedbir tanımı aynen alındı, denetim soruları eylem ve beklenen sonuç biçimine dönüştürüldü.

## Aktarımda karşılaşılan zorluklar

- **JRU ve DMI değerleri:** ERTMS beklenen sonuçları arayüz düzeyindedir: `NID_MESSAGE_JRU`, `NID_SOLR`, DMI simge bitleri (SUBSET-027 ve ERA DMI belgesi). Bunlar derlemde yok ve hiçbir destek parçasından yazılamaz. Mesaj adları (SUBSET-026-8) ve paket numaraları (SUBSET-026-7 §7.4.1) da parçalara alınmadı.
- **Alt simgeler:** pdftotext alt simgeleri düzleştirdi: `LRBGONB` = LRBG_ONB, `LRBGRBC` = LRBG_RBC.
- **Seçenekli I satırları:** 3070300 TC14'te adım 3 (L1, balise) ve adım 5 (L2, telsiz) birbirinin seçeneğidir. Tek eylemde birleştirildi; "Info: If in L1/L2" koşulları korundu.
- **Kapsam taşması:** 3080200 TC7 §3.8.2.1.7 ve §3.8.2.2.2'ye dayanıyor, ama tekrar davranışını (§3.8.2.1.5, T_CYCRQST) da sınıyor. Bu madde TC'nin dayanak listesinde yok; ilgili iki denetim gereksinim cümlesinden çıkmaz.
- **Birleştirilmeyen test vakaları:** 3060200 TC2 ile TC3 aynı olay dizisini çelişen ön koşullarla (linking var/yok) çalıştırır. Bu yüzden yalnızca TC2 alındı.
- **TC metnindeki hatalar:** yazım hataları ("boad", "trasition", "recieved", "pertubation") TC'den aynen alındı.
- **Beklenen sonucu olmayan kriterler:**
  - PV-7 TEST bir sonuç vermiyor; beklenen sonuç PV-7 ifadesinden alındı.
  - RL-2 ve RL-3'te TEST ve EXAMINE tek denetimde birleştirildi.
- **ACT:** her kural tek Applicability + Expectation verir. İki kural, "inspect its lang attribute" bağlayıcı ifadesiyle birleştirildi. Kuralın geçmesi SC'nin sağlandığını göstermez, yalnızca "daha fazla test gerekir" anlamına gelir. bf051a'nın daha yeni, önerilmiş (onaylanmamış) bir sürümü var; o kullanılmadı.
- **SGB:**
  - `-layout` çıktısında soru ile tedbir eşlemesi belirsizdi. Eşleme, PDF'teki yatay tablo çizgilerinin konumuyla doğrulandı.
  - Bir soru (3. soru) iki soru içeriyordu; iki denetime bölündü.
  - "Yetkisiz güncellenebiliyor mu?" sorusunun beklenen yanıtı tedbir tanımından çıkarıldı.
  - Bir soru davranışı değil, testin yapılıp yapılmadığını soruyor.
- **800-53A:** adım, girdi ya da beklenen sonuç yok. Beklenen sonuç, hedefin olumlu ifadesidir. Yöntemler (EXAMINE, INTERVIEW, TEST) yalnızca kontrol düzeyinde verilmiş. Parametre değerleri sistem güvenlik planındadır; bu plan henüz yok.
- **AC-7 destek parçası:** OSCAL katalogdan basılı 800-53 biçiminde ([Assignment], [Selection]) üretildi. Basılı PDF'le harfi harfine karşılaştırılmadı.
