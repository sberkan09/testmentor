# ERTMS izlenebilirlik denemesi (paket 1b, aşama 1)

20 Kasım 2026. Kaynaklar: ERA ETCS B4 R1 dizini, SUBSET-026 v4.0.0, SUBSET-076-5-2 v4.0.0 (SV30), SUBSET-076-7 v4.0.0. Metinler `pdftotext -layout` ile çıkarıldı. Kullanıcı ERTMS metninin özel depoya girmesini onayladı.

- `refs2.json`: test vakası başına "Based on Requirements" atıfları, girdi/çıktı satır sayıları, `Use_FT` sayısı (SV30; 2.325/2.435 test vakası ayrıştırıldı).
- `srs_clauses.json`: SUBSET-026 madde numarası → ilk satır.
- `table3.txt`: SUBSET-076-7 Tablo 3, test edilemez gereksinimler.
- `scripts/`: üretim betikleri (indirme ve çıkarma yolları geçici dizine göredir; aşama 3'te `eval/corpus` komutuna taşınacak).

Bulgular paket tanımında (`docs/paketler/paket-1b-altin-set-v1.md`, aşama 1).
