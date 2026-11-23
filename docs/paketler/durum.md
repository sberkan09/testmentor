# Durum ve karar günlüğü (paket 4–9)

Başlangıç: 23 Kasım 2026. Kullanıcı talimatı: "Yarına kadar bitir, bana sorma, önerdiğin her şeyi onaylıyorum, gerektiğinde kendin karar ver." Bu dosya her birleştirmede güncellenir; yeniden başlayan oturum buradan devam eder.

## Durum

| Paket | Plan | Kol | Durum |
| --- | --- | --- | --- |
| 3, 3b | `paket-3-plan.md`, `paket-3b-plan.md` | – | birleşti (#5) |
| 4 | `paket-4-plan.md` | A (Sonnet) | **birleşti** (23.11): bitti testi (altın set v0 csv ve xlsx → matris → xlsx) geçti; 316 test |
| 5 | `paket-5-plan.md` | B (Opus) | yazılıyor (23.11) |
| 6 | `paket-6-plan.md` | B (5'ten sonra) | planlandı |
| 7 | `paket-7-plan.md` | C (Sonnet) | **kod birleşti** (23.11): yalıtım testi geçti, 374 test; D9 batch koşuyor (ayrı çalışma ağacından) |
| 8 | `paket-8-plan.md` | D (Sonnet) | **birleşti** (23.11): build, lint, 35 birim testi; e2e yalnızca sahte API'ye karşı geçti, gerçek API ile paket 6'dan sonra |
| 9 | `paket-9-plan.md` | – | **kesildi** (PoC/demo hedefi, 23.11) |
| Demo | – | bu oturum | gerçek model çıktılarıyla demo videosu (Playwright kaydı + ffmpeg alt yazı, MP4) |

Hedef (kullanıcı, 23.11): yarına tam kullanıma hazır sürüm değil, **PoC ve demoya uygun sürüm**, ayrıca demo videosu. Kesme sırası: paket 9 (kesildi) → D10 → D9'un ek kolları → fark ekranı ve çok kullanıcılı ayrıntılar.

## Kullanıcı adına verilen kararlar

| Tarih | Karar | Gerekçe |
| --- | --- | --- |
| 23.11 | Paket 3 PR #5 açıldı ve birleştirildi (merge commit); dal main'den yeniden başlatıldı | kullanıcı onayı ("önerdiğin her şey") |
| 23.11 | Runpod için 15 USD kredi önerildi (asgari 10) | `make up` alt sınırı 5 USD + volume ~0,58 USD/gün + paket 7 GPU ~3,3 USD + kabul koşusu ~1,35 USD + %50 pay |
| 23.11 | Paketler ayrı alt oturumlarda (bir paket bir bağlam), en çok üç kol paralel; tasarım tablosundaki model; her kol bu oturumda diff okunarak ve testler koşturularak doğrulanır | "bir paket bir oturum" kuralı ve süre |
| 23.11 | Paketler arası sözleşmeler (`worker/contracts.py`: komut, olay, snapshot, düğüm görünümü, servis arayüzü) bu oturumda yazılır ve dondurulur | paralel kolların birbirine bağlandığı yer |
| 23.11 | Kalıcılık: Postgres (psycopg 3). Birim testleri bellek içi depo ile; Postgres testleri yerel Postgres 16 ile (`make pg`), sunucu yoksa atlanır | konteynerde Docker servisi yok, Postgres 16 sunucusu var |
| 23.11 | Yerelde pgvector yok: bilgi havuzu indeksi bir arayüz arkasında; testler ve ölçüm numpy + anahtar kelime (BM25) ile, üretimde pgvector (uzantı varsa koşan entegrasyon testi) | tasarım pgvector diyor; geliştirme ortamında uzantı kurulamıyor |
| 23.11 | İlk sürümde kimlik doğrulama yok: komutun sahibi `X-User` başlığından okunur; proje bazlı yetki sonraki sürüm | süre; tasarımdaki "kullanıcı girişi" kapsam dışına alındı (tasarımda kayıtlı) |
| 23.11 | Paket 5 bitti ölçütü D8'e göre güncellendi: taşıma 1 artımlı test + 2 ad çağrısıyla biter | D8: çıkılan set çağrısız budanır |
| 23.11 | Hiçbir alt oturum ücretli kaynak açmaz ve hakem çağırmaz; Runpod yalnızca bu oturumda, `make batch` ile | kredi koruması |
| 23.11 | Paket 4 ve 5'in çalışma ağaçları main'deki birleştirme commit'inden açıldı (sözleşme ve planlar yoktu); ikisine de bu dalı birleştirmeleri bildirildi | alt oturum araçlarının taban commit'i |
| 23.11 | `api/schema.json` bu oturumda üretildi (paket 6'nın parçası öne alındı), paket 8 sözleşmeye göre paralel başladı | ön yüz en uzun iş; arka uçsuz başlayabilir |
| 23.11 | Kullanıcı Runpod'a kredi yükledi (bakiye 21,03 USD) | – |
| 23.11 | Hedef PoC/demo sürümüne indi; paket 9 kesildi; ön yüzde öncelik demo akışı (yükleme → öbekler → düzenleme → matris → xlsx) | kullanıcı talimatı |
| 23.11 | Demo videosu gerçek model çıktılarıyla çekilir (kısa GPU koşusu, ~1–1,5 USD); sahte modelin metinleri demoda yapay görünür | demo inandırıcılığı |
| 23.11 | Paket 4: `core/importing.py` ve `core/matrix_view.py` `worker.contracts` içindeki saf pydantic modelleri içe aktarıyor (katman yönü ters); PoC için kabul, sözleşme modelleri ileride `core/` altına taşınabilir | süre; dosya, HTTP ya da veritabanı bağımlılığı yok |
| 23.11 | D9'da reranker kolu koşulmadı: tasarım ilk sürümde reranker'sız, kod hazır (`kb.reranker`), model seçimi ve CPU çapraz kodlama PoC'ye değer katmıyor | süre, kesme sırası |
| 23.11 | D10 kesildi: örnek havuzu kodu hazır (varsayılan kapalı), ama altın setin referans testlerinden kurulan havuz cevap anahtarını sızdırır; sızıntısız havuz ayrı iş | ölçüm geçerliliği, kesme sırası |
| 23.11 | GPU batch'leri ayrı bir çalışma ağacından (`/home/user/testmentor-batch`, sabit commit) koşar; ana dala birleştirmeler koşan batch'in kodunu değiştirmez | paralel birleştirme ile ölçümün yalıtımı |

