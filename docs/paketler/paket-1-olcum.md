# Paket 1: altın set ve ölçüm koşucusu

Model: tasarım Opus, uygulama Sonnet. Önkoşul: paket 0.

## Amaç

Altın set üzerinde tek komutla tekrar edilebilen bir ölçüm koşucusu ve onunla koşulan D0–D5 ile D12 deneyleri. Paketin sonunda sunum motoru, model ve temel ayarlar ölçümle seçilmiş olur.

## Girdi

`eval/golden/altin-set-v0.json`. Yapı:

- `projects[]`: `key`, `name`, `domain`, `requirements[]`, `test_cases[]`.
- Gereksinim: `id`, `language`, `text`, `reference_cluster`, `verification_methods[]`, `method_rationale`, `difficulty`, `note`.
- Test durumu: `id`, `title`, `covers[]`, `type`, `priority`, `preconditions`, `test_inputs`, `assumptions`, `steps[{no, action, expected}]`.

Her proje ayrı bir gereksinim seti olarak işlenir.

## Koşucu

- Komut: `python -m eval.run --config config/experiments/<deney>.yaml`.
- Çıktı: `results/<koşu kimliği>/` altında `outputs.jsonl`, `metrics.json`, `report.md`.
- Koşucu pipeline'ı bir çağrılabilir olarak alır. Bu pakette en yalın pipeline yazılır: embedding ve agglomerative kümeleme, öbek başına test üretimi, toplu doğrulama yöntemi sınıflandırması. Paket 3 bunu gerçek aşamalarla değiştirir; koşucu değişmez.
- Deney ayar dosyasında tek değişken değişir; geri kalanı çalışma varsayımından gelir.

## Puanlama

### Katman 1: kural denetimi (her koşu, model çağrısı yok)

| Ölçüt | Tanım |
| --- | --- |
| `schema_valid_rate` | şemaya uyan çıktı oranı |
| `step_structure_rate` | her adımında işlem ve beklenen sonuç dolu olan test oranı |
| `coverage_rate` | yöntemi Test içeren gereksinimlerden en az bir `covers` listesinde geçenlerin oranı |
| `no_test_violations` | yöntemi Test içermeyen gereksinime yazılan test sayısı |
| `method_exact_match` | yöntem kümesi referansla aynı olan gereksinim oranı |
| `method_jaccard` | yöntem kümelerinin ortalama Jaccard benzerliği |
| `cluster_ari` | proje başına, referans öbeklemeyle düzeltilmiş Rand indeksi |
| `seconds_per_cluster`, `tokens_total`, `tokens_per_second` | süre ve hız, 16 eşzamanlı istekte |

### Katman 2: hakem model (her deney)

- Birim gereksinimdir. Referans denetimler, o gereksinimi kapsayan referans testlerin adım ve beklenen sonuç çiftleridir.
- Hakeme gereksinim metni, numaralı referans denetimler ve o gereksinimi kapsayan üretilmiş testler verilir.
- Hakem JSON döner: her denetim için `matched` ve kanıt (üretilen test ve adım), ayrıca `invented[]` (gereksinimde olmayan uydurma içerik), `boundary_ok`, `ambiguity_flagged`.
- Ana ölçüt `check_recall`: eşleşen denetim sayısı bölü toplam denetim. Üslup puanlanmaz.
- Hakem Claude Sonnet'tir, sıcaklık 0. Rubrik sürümlüdür. Hakem çıktıları girdi hash'iyle cache'lenir; aynı çıktı iki kez puanlanmaz.
- Tuzak gereksinimler (`note` alanı "Tuzak" ile başlayanlar) raporda ayrı gösterilir.
- Gerçek proje verisi sete girdiğinde hakem yerel modele ya da uzmana geçer.

### Katman 3: uzman (yalnızca final ve hakem ayarı)

- Betik, 10 öbek için iki adayın çıktısını rastgele A ve B sırasıyla tek bir xlsx formuna yazar.
- Test mühendisi her çifti 1–5 puanlar. Betik puanları içe alır ve adaylarla eşler.

### Karar kuralı

1. Aday katman 1 eşiklerini geçer: `schema_valid_rate` en az %99, onarım sonrası `coverage_rate` %100, `step_structure_rate` %100, `no_test_violations` 0.
2. Geçenler `check_recall` değerine göre sıralanır; eşitlikte hızlı olan öne geçer.
3. İlk iki adayı uzman karşılaştırır.

Tek bir toplam puan üretilmez; rapor ölçütleri ayrı sütunlarda verir. Türkçe ve İngilizce gereksinimler ayrı raporlanır.

## Deneyler

| No | Soru | Not |
| --- | --- | --- |
| D0 | Hakem puanı uzman puanıyla uyuşuyor mu | Test mühendisi gerekir. Yoksa hakemle devam edilir ve rapora uyarı yazılır |
| D1 | Sunum motoru | vLLM ve SGLang; 1, 8, 16, 32 eşzamanlı istek |
| D2 | Model | Qwen3.8-27B, Gemma 4 31B, gpt-oss-120b |
| D3 | Düşünme modu ve örnekleme | Seçilen modelde |
| D4 | Ağırlık hassasiyeti | 16 bit, FP8, 4 bit |
| D5 | Eşzamanlılık ve bağlam | Dizi sınırı ve bağlam uzunluğu |
| D12 | Önek ısıtma | Paralel çağrıları ilk çağrı öneki işleyene kadar bekletmek ve bekletmemek |

Sıra: D1, D2, D3, D4, D5, D12. D0 test mühendisi hazır olduğunda koşulur.

## Bitti ölçütü

- Bir deney tek komutla koşar ve raporunu yazar.
- Aynı ayarla iki koşu katman 1 ölçütlerinde aynı sonucu verir; fark varsa raporlanır.
- Deney raporları `docs/deneyler/` altındadır.
- `docs/tasarim.md` içindeki Deney planı tablosuna Sonuç sütunu eklenmiş, seçilen motor, model ve ayarlar `config/` altına yazılmıştır.
- Oturum sonunda çalışan Runpod kaynağı kalmamıştır.

## Dikkat

- Deneyleri toplu koş; pod'u deneyler arasında açık bırakma.
- Hakem çağrıları API ücreti doğurur. Cache'i kapatma, hakemi yalnızca değişen çıktılar için çağır.
- Altın set sentetiktir. Sonuçlar gerçek projeler için kesin sayılmaz; set v1'e yükseldiğinde D2 tekrarlanır.
