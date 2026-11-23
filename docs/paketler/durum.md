# Durum ve karar günlüğü (paket 4–9)

Başlangıç: 23 Kasım 2026. Kullanıcı talimatı: "Yarına kadar bitir, bana sorma, önerdiğin her şeyi onaylıyorum, gerektiğinde kendin karar ver." Bu dosya her birleştirmede güncellenir; yeniden başlayan oturum buradan devam eder.

## Durum

| Paket | Plan | Kol | Durum |
| --- | --- | --- | --- |
| 3, 3b | `paket-3-plan.md`, `paket-3b-plan.md` | – | birleşti (#5) |
| 4 | `paket-4-plan.md` | A (Sonnet) | **birleşti** (23.11): bitti testi (altın set v0 csv ve xlsx → matris → xlsx) geçti; 316 test |
| 5 | `paket-5-plan.md` | B (Opus) | **birleşti** (23.11): bitti testi (taşıma 1 TestCaseDelta + 2 ClusterLabel, geri alma 0 çağrı) geçti; 450 test, Postgres 24/24; bağımsız Opus incelemesi 8 bulgu (1 kritik) → hepsi testle düzeltildi; 475 test, Postgres 27/27, e2e geçti |
| 6 | `paket-6-plan.md` | E (Sonnet) | **birleşti** (23.11): iki bitti testi sahte servisle geçti, 388 test; gerçek servise bağlantı (`api/main.build_service`) paket 5 birleşince |
| 7 | `paket-7-plan.md` | C (Sonnet) | **bitti** (23.11): yalıtım testi geçti; D9: gerçek hibrit arama +0,073 [+0,035, +0,114], 400 token, ilk 4 (`kb.top_k`), kart var |
| 8 | `paket-8-plan.md` | D (Sonnet) | **birleşti** (23.11): build, lint, 35 birim testi; **bitti testi (Playwright) gerçek API'ye karşı geçti** (sahte modelle) |
| 9 | `paket-9-plan.md` | F (Opus) | yeniden açıldı (kullanıcı, 23.11), sürüyor |
| 10 | `paket-10-plan.md` | G (Opus) | pilot hazırlığı, sürüyor |
| 11 | `paket-11-plan.md` | ana oturum | D10 ve reranker, sürüyor |
| Demo | – | **bitti** (23.11) | `docs/demo/testmentor-demo.mp4` (76 sn, gerçek model çıktıları, bekleme bölümleri hızlandırılmış); kayıt `demo/record_real.sh`, kurgu `demo/make_video.py` |

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
| 23.11 | Sahte embedding kelime yerine karakter üçlüleriyle: kelime torbası küçük projelerde her gereksinimi tek öbek bırakıyordu (e2e taşıma adımı öbek bulamadı) | e2e ve geliştirme kipinde anlamlı öbekler |
| 23.11 | Demo veri seti: altın set v1 KDH "Vatandaş Başvuru Portalı" (60 TR + 60 EN; gerçek BGE-M3 ile 23 öbek). v0'ın 40 gereksinimi 0,35'te 33 öbeğe dağılıyor (27 tek üyeli) | ekranda anlamlı öbekler, Türkçe kamu hizmeti konusu |
| 23.11 | Paket 5 incelemesi: 7. bulgu kararı, reddedilen geri alma kaydı yığından düşer; düzeltme kolu onay kuralında çalışan düğümün onayını korudu (depo hatasından sonra yeniden onay istenmesin), kabul edildi | inceleme bulguları |
| 23.11 | D9: `kb.top_k` 8 → 4 (4/8/12 arasında ölçülebilir fark yok, 4 en kısa prompt); parça boyu 400 ve kart kalır | planın kuralı: fark yoksa basit ve ucuz olan |

| 23.11 | Demo kaydı Playwright videosu yerine CDP ekran akışı kareleriyle; `make_video.py` bekleme aralıklarını 6 sn'ye sıkıştırır, bir çıktı karesinden kısa kareleri atar | Playwright'ın ffmpeg derlemesi ortamda yok |
| 23.11 | Kullanıcı "2, 3 ve 4'ü yap": pilot hazırlığı (paket 10), kalite (paket 11: D10, reranker), 3B görünüm (paket 9) | kullanıcı talimatı |
| 23.11 | Bulgu: sunucu (`api/main.py`) bilgi havuzunu hiç bağlamıyordu; demo dahil sunucuda parça getirme kapalıydı. Paket 10'un ilk işi | inceleme |
| 23.11 | Pilot doğrulaması bu konteynerde Docker ile (daemon elle başlatıldı, `pgvector/pgvector:0.8.7-pg18` çekildi); GPU servisleri yerelde çalıştırılmaz | ortam |
