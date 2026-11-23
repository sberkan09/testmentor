# Paket 9 planı: 3B katman görünümü

23 Kasım 2026. Model: Opus. Paket 8'den sonra; süre yetmezse ilk kesilecek iş (`durum.md`). Bitti ölçütü (tasarım): 2.000 gereksinimde akıcı gezinme.

## Kapsam

- `web/src/views/layers/`: react-three-fiber. Üst üste üç düzlem: öbekler (gereksinim noktaları öbek adalarında), test durumları, matris; aralarında izlenebilirlik ipleri (gereksinim → onu kapsayan test durumları → matris satırı). Yukarı ipi çıkmayan gereksinim (kapsanmamış) vurgulanır.
- Çizim: noktalar ve ipler `InstancedMesh` / `LineSegments` ile (2.000 gereksinim, ~5.000 test durumu, ~10.000 ip); metin yalnızca HTML katmanında ve yakınlaşınca (tasarım: metin WebGL içinde çizilmez). *Uygulamada değişti: noktalar `Points`, adalar ve matris hücreleri birleştirilmiş tek ağ; ipler uzakta demet, yakında odaktaki adalar için tek tek (aşağıda "Uygulamada netleşenler").*
- Etkileşim: yörünge kamera, seçim (ışın), seçilen öğede kameranın ilgili 2B görünüme inmesi (öbek görünümü ya da matris), düzenleme yok.
- Düzen: öbek merkezleri öbek görünümündeki konumlardan; test durumları kapsadıkları gereksinimlerin ağırlık merkezinin üstünde.

## Testler

- **Bitti testi** `web/e2e/layers-perf.spec.ts`: 2.000 gereksinim ve ~5.000 test durumlu sentetik snapshot (API'siz, sabit veri) ile katman görünümü açılır; 5 sn yörünge hareketinde ortalama kare süresi ≤ 33 ms (≥ 30 fps), Playwright'in Chromium'unda yazılım çizimiyle ölçülür (eşik bu yüzden 30 fps). Seçim, seçilen öğenin 2B görünümünü açar. İpler uzaklığa bağlı çizildiği için iki yörünge ölçülür: tüm görünüm (demet ipler) ve geçiş uzaklığının hemen içi (tek tek ipler; test katmanı ve çizilen parça sayısını da doğrular).

## Kurallar

Ücretli kaynak ve hakem yok. 2B görünümler bu paketten bağımsız kalır.

## Uygulamada netleşenler

### İlk ölçüm ve maliyet dökümü

İskelet (her öğe türü bir `InstancedMesh`, ~19.300 parçalı tek `LineSegments`, sRGB çıktı) Playwright Chromium + SwiftShader'da **328 ms/kare** verdi (5 sn'de 19 kare). Bileşen başına eşzamanlı çizim süresi (`gl.render` + 1 piksellik `readPixels`, 25 karenin ortancası, 1440×900, makine başka oturumların yüküyle dolu, yük ortalaması ~32):

| Bileşen | Süre |
| --- | --- |
| 2.000 gereksinim, `InstancedMesh` (sekizyüzlü) | 42 ms |
| 5.022 test durumu, `InstancedMesh` (küp) | 110 ms |
| 2.000 matris hücresi, `InstancedMesh` (kare) | 56 ms |
| 80 ada + 101 halka, `InstancedMesh` | 10 ms |
| 19.318 ip parçası, `LineSegments`, sRGB çıktı | 104–126 ms |
| aynı ipler, doğrusal çıktı | 52–56 ms |
| 9.022 nokta, `Points` | 7–12 ms |
| 56.000 üçgen, birleştirilmiş tek ağ | 21–23 ms |
| yalnızca gereksinim → test parçaları (9.659) | 22–26 ms |
| yalnızca test → matris parçaları (9.659, sıralı matriste uzun) | 39–50 ms |

Sonuç: SwiftShader'da örnekli çizim örnek başına ~20 µs tutuyor (üçgen sayısından bağımsız) ve ince çizgiler piksel başına pahalı. Tüm ipler tam görünümde tek başına bütçeyi aşıyor.

### Tasarımdan ve plandan sapmalar (bu commit'ten önce yazıldı)

- **Noktalar `Points`.** Gereksinim (yuvarlak) ve test durumu (kare) tek tepeli nokta sprite'ları; boyut uzaklıkla ölçeklenir. Kapsanmamış gereksinim: üstüne daha büyük halka sprite'ı (ayrı ağ yok). Adalar ve matris hücreleri birleştirilmiş tek statik ağ (örnekleme yok). Planın `InstancedMesh` maddesi bu yüzden uygulanmadı.
- **Doğrusal çıktı.** Renkler sRGB olarak verilip olduğu gibi yazılır (`legacy` renk yönetimi, `LinearSRGBColorSpace` çıktı); parça başına sRGB dönüşümü yok. Işıksız düz renklerde görünüm aynı; yarı saydam iplerin karışımı sRGB uzayında olur.
- **Matris düzlemi öbek bloklarında.** Matris satırları kendi adasının üstünde, blok içinde kimlik sırasıyla (matris görünümündeki öbek kolonu). Kimlik sıralı tek ızgarada test → matris ipleri sahneyi boydan boya kesiyordu (yukarıdaki tabloda en pahalı kalem).
- **İpler uzaklığa bağlı (tasarım güncellendi).** Kamera, çerçeve uzaklığının `EXACT_THREADS_BELOW` (0,45) katından uzaktaysa her ada için demet: her kapsanmış gereksinimden adanın test durumu merkezine bir ip, oradan adanın matris bloğuna bir ip (~2.000 parça). Daha yakında yalnızca kameranın baktığı noktaya en yakın adaların gerçek ipleri (gereksinim → test durumu → matris satırı), `EXACT_SEGMENT_BUDGET` (1.600) parçalık bütçeyle; bütçe yaklaştıkça yarıya kadar küçülür (ekranda ipler uzar). Kapsanmamış gereksinimin iki görünümde de ipi yoktur. Değerler `web/src/views/layers/tiers.ts` içinde.
- **Etiketler** yalnızca yakınlaşınca: çerçeve uzaklığının 0,6 katından yakında öbek adı, sayısı ve kapsanmamış sayısı; 0,2 katından yakında gereksinim, test durumu ve matris satırı kimlikleri. En fazla 60 etiket, yakındaki önce, çakışan atlanır; konumlar kare döngüsünde düzen okumadan yazılır.
- **Seçim:** ışın önce noktalar ve matris hücrelerine, sonra ekranda 8 piksel içindeki en yakın noktaya, sonra adaya. Seçilen öğeye kamera 550 ms'de iner, ardından gereksinim ve test durumu öbek görünümünü (öbek kartı görünür alana kaydırılır), matris hücresi matris görünümünü (satır görünür alana kaydırılır) açar ve denetçide öğe seçilir.
- **Bağımsızlık:** katman görünümü `React.lazy` ile ayrı parça (three.js dahil); 2B görünümler ondan hiçbir şey içe aktarmaz. Ana paket 241,8 kB'tan 242,5 kB'a çıktı (yalnızca sekme ve tembel yükleme).
- **Ölçüm yöntemi:** sahne istek üzerine çizilir (`frameloop="demand"`, sönümlü yörünge her karede yeniden çizim ister); her çizilen kare `window.__testmentorLayers.frames` içine zaman damgası yazar. Ortalama = (son − ilk) / (kare sayısı − 1), en az 100 kare şartıyla. Fare her animasyon karesinde bir adım sürüklenir. Chromium bayrakları: `--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`; çizici dizgesi `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)`.

### Eşik ve bütçe taraması

Yeni düzende (Points, birleştirilmiş ağlar, öbek bloklu matris, doğrusal çıktı), eşzamanlı çizim süresi, uzaklık oranına göre (oran = kamera uzaklığı / çerçeve uzaklığı; yük ortalaması ~30, değerler gürültülü):

| İpler | oran 1 | 0,8 | 0,6 | 0,5 | 0,45 | 0,4 | 0,3 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hepsi tek tek (19.318 parça) | 46 ms | 68 | 60 | 71 | 78 | 73 | 64 |
| ada demetleri (3.810 parça, ilk biçim) | 18 | 24 | 26 | 26 | 29 | 25 | 26 |
| ipsiz | 14 | 17 | 13 | 19 | 20 | 15 | 15 |

Tüm iplerin tek tek çizimi hiçbir uzaklıkta bütçeye girmiyor; yaklaştıkça ipler ekranda uzadığı için ucuzlamıyor da. Demet ilk biçimde her gereksinim için iki parçaydı (gereksinim → merkez → satır); merkez → matris ipleri ada başına bire indirildi (~2.000 parça, tek başına ~6 ms). Yörünge ölçümüyle (kare aralığı, yük ~10–20): yalnızca odaktaki adaların gerçek ipleri (1.340 parça, 6 ada) 0,12–1 oranlarında 19–27 ms; aynı odak artı diğer adaların demetleri 28–30 ms, demetsiz 23 ms. Bu yüzden eşiğin içinde diğer adaların demetleri çizilmez. Eşik 0,45: bunun üstünde odak, görünen sahnenin küçük bir parçası kalıyor ve demet görünümü daha bilgilendirici; bütçe 1.600 parça, yaklaştıkça yarıya iner (0,2 oranında ~800 parça, 3 ada).

## Sonuç

Bitti testi `web/e2e/layers-perf.spec.ts` geçiyor (eşik değişmedi: ortalama ≤ 33 ms, ≥ 100 kare). 1440×900, Chromium 153 + SwiftShader, bayraklar yukarıda. Ölçümler, aynı makinede başka oturumların ağır işleri sürerken alındı (4 çekirdek); yük ortalaması her koşunun yanında:

| Koşu (commit) | Yük | Uzak, demet ipler | Eşik içi (0,43), 1.340 gerçek ip parçası | Sonuç |
| --- | --- | --- | --- | --- |
| eski hal, 93eb7e5 öncesi | ~8 | 20,6 ms | 26,1 ms | geçti |
| eski hal | ~3 | 20,0 ms | 24,3 ms | geçti |
| kamera düzeltmesi sonrası | ~20 | 25,7 ms | 29,3 ms | geçti |
| kamera düzeltmesi sonrası | ~25 | 32,8 ms | 36,5 ms | kaldı (eşik içi) |
| kamera düzeltmesi sonrası | ~30 | 24,9 ms | 32,5 ms | geçti |
| 6770045, tüm e2e takımı | ~34 | 29,6 ms | 30,5 ms | geçti |

Sessiz makinede (yük ≤ 8) uzak görünüm ~20 ms, eşik içi ~24–26 ms; ilk ölçüm 328 ms idi. Test çekişmeye duyarlıdır: başka bir süreç 3+ çekirdeği kullanırken eşik içi yörünge 33 ms'yi aşabilir (bir koşuda 36,5 ms). Eşik gevşetilmedi, yeniden deneme ya da yüke göre atlama eklenmedi.

Seçim adımları (gereksinim → öbek görünümü ve öbek kartı görünür alanda; matris hücresi → matris görünümü ve satır görünür alanda; denetçide öğe seçili) ve "başladığı yere dönen sürükleme seçim sayılmaz" adımı her koşuda geçti. Mevcut e2e (`flow.spec.ts`) yeşil, `demo.spec.ts` önceden olduğu gibi atlanıyor.
