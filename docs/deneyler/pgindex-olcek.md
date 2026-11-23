# Postgres bilgi havuzu indeksi: ölçek testi

Pilot hazırlığı, 23 Kasım 2026. `PgIndex` daha önce yalnızca küçük tablolarla denenmişti. Koşucu `eval/kb_scale.py`, ham sonuçlar `results/20261123-kb-scale/` (`once.json`, `sonra.json`). pgvector 0.8.7, Postgres 18 (`pgvector/pgvector:0.8.7-pg18`), bu geliştirme konteynerinde (4 çekirdek).

## Kurulum

- **Tablo:** 51 proje. 50 proje × 2.000 parça ve bir proje × 20.000 parça, toplam 120.000 parça.
- **Metin gerçek:** altın set v1 derleminin yazar görünür belgeleri (KDH ve ETC), 400 token'lık parçalar (6.697 parça), yeni belge kimlikleriyle çoğaltıldı.
- **Vektörler rastgele:** 1024 boyutlu birim vektörler. Yoğun aramanın maliyeti metne değil satır sayısına bağlı.
- **Sorgular gerçek:** altın setin 98 referans öbeğinden rastgele birinin üye metinleri (üretimdeki öbek araması gibi). Sorgu vektörü bir parçanın yakınına dikildi; o parça yoğun sıralamada ilk çıkmalı. Ölçülen proje başına 30 sorgu.

## Bulgular ve düzeltmeler

1. **Yoğun arama sonuç kaçırıyordu.** Tablo büyüyünce planlayıcı küresel HNSW indeksini kullanıp proje süzgecini sonradan uyguladı. 20.000 parçalık projede 30 sorgunun 6'sında en yakın parça ilk sırada değildi. D9'u ölçen bellek içi indeks kesin arama yapıyor. Düzeltme: HNSW indeksi kaldırıldı, arama proje başına kesin tarama (`ensure_schema` eski indeksi siler).
2. **Anahtar kelime araması yavaştı ve BM25 değildi.** Öbeğin bütün üye metinlerindeki terimler OR'lanıyordu; yaygın kelimeler neredeyse her parçayı eşleştirdi ve `ts_rank_cd` hepsi için hesaplandı. Üstelik bu sıralama, D9'da ölçülen bellek içi BM25 ile ilk 20 sonuçta yalnızca %15 (KDH) ve %21 (ETC) örtüşüyordu. Düzeltme:
   - Proje başına terim sıklığı (`kb_terms`) ve parça uzunluğu (`fts_len`) tutuluyor.
   - Sorgunun ayırt edici terimleri bir aday kümesi seçiyor: projenin en çok %20'sinde geçen terimler, en nadir 32 tanesi, `ts_rank_cd` ile ilk 400 aday.
   - Adaylar bellek içi indeksle aynı BM25 formülüyle (k1, b, idf, uzunluk normalizasyonu), bütün sorgu terimleri üzerinden puanlanıyor.
   - Sınırsız ayarla sonuç bellek içi BM25 ile birebir aynı (test). Seçilen ayarla ilk 20'de %96 (KDH) ve %95 (ETC) örtüşüyor.
3. **Yükleme satır satır yapılıyordu** ve HNSW bakımı yavaşlatıyordu. Satırlar artık toplu ekleniyor.

Eşik seçimi (gerçek derlem, 98 öbek sorgusu, bellek içi BM25'in ilk 20'siyle örtüşme ve süre):

| ayar (en çok df, terim, aday) | KDH örtüşme | KDH ms | ETC örtüşme | ETC ms |
| --- | --- | --- | --- | --- |
| eski (bütün terimler, `ts_rank_cd`) | 0,148 | 426 | 0,208 | 1.258 |
| sınırsız BM25 | 1,000 | 494 | 1,000 | 1.229 |
| 0,2, 32, 100 | 0,791 | 56 | 0,808 | 109 |
| 0,2, 32, 200 | 0,919 | 67 | 0,898 | 120 |
| **0,2, 32, 400 (seçilen)** | **0,964** | **78** | **0,947** | **123** |
| 0,1, 32, 200 | 0,920 | 48 | 0,887 | 115 |
| 0,3, 64, 200 | 0,915 | 104 | 0,967 | 454 |
| 0,2, 16, 200 | 0,830 | 52 | 0,773 | 30 |

## Sonuç (120.000 parça, 51 proje)

| | önce | sonra |
| --- | --- | --- |
| 2.000 parçalık proje: arama p50 / p95 | 378 / 1.112 ms | 94 / 184 ms |
| 20.000 parçalık proje: arama p50 / p95 / en kötü | 2.933 / 14.117 / 21.862 ms | 541 / 1.190 / 1.325 ms |
| 20.000 parça: yoğun p50 / anahtar kelime p50 | 9 / 2.713 ms | 131 / 424 ms |
| dikilen parça yoğun sıralamada ilk (2.000 / 20.000) | 30 / 24 (30 sorgudan) | 30 / 30 |
| başka projeden sonuç | 0 | 0 |
| yükleme (120.000 parça) | 1.662 sn (72 parça/sn) | 131 sn (916 parça/sn) |
| tablo boyutu | 1.962 MB | 1.025 MB |

## Kapasite notu

- Arama öbek başınadır. 100 öbekli bir projede 20.000 parçayla tam yeniden arama veritabanında yaklaşık 1 dakika sürer; 2.000 parçayla ~10 saniye. Model üretimi bunun çok üstündedir.
- Kesin yoğun arama proje başına satır sayısıyla doğrusal büyür: 20.000 parçada ~130 ms. Bir projede 100.000 parçayı geçen bir bilgi havuzu beklenirse proje başına bölümlenmiş tablo ve bölüm içi yaklaşık indeks düşünülmeli.
- Ölçüm bu konteynerin 4 çekirdeğinde ve aynı makinedeki Postgres'le yapıldı; pilot sunucusunda sayılar farklı olacaktır.
