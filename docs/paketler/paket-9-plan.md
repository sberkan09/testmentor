# Paket 9 planı: 3B katman görünümü

23 Kasım 2026. Model: Opus. Paket 8'den sonra; süre yetmezse ilk kesilecek iş (`durum.md`). Bitti ölçütü (tasarım): 2.000 gereksinimde akıcı gezinme.

## Kapsam

- `web/src/views/layers/`: react-three-fiber. Üst üste üç düzlem: öbekler (gereksinim noktaları öbek adalarında), test durumları, matris; aralarında izlenebilirlik ipleri (gereksinim → onu kapsayan test durumları → matris satırı). Yukarı ipi çıkmayan gereksinim (kapsanmamış) vurgulanır.
- Çizim: noktalar ve ipler `InstancedMesh` / `LineSegments` ile (2.000 gereksinim, ~5.000 test durumu, ~10.000 ip); metin yalnızca HTML katmanında ve yakınlaşınca (tasarım: metin WebGL içinde çizilmez).
- Etkileşim: yörünge kamera, seçim (ışın), seçilen öğede kameranın ilgili 2B görünüme inmesi (öbek görünümü ya da matris), düzenleme yok.
- Düzen: öbek merkezleri öbek görünümündeki konumlardan; test durumları kapsadıkları gereksinimlerin ağırlık merkezinin üstünde.

## Testler

- **Bitti testi** `web/e2e/layers-perf.spec.ts`: 2.000 gereksinim ve ~5.000 test durumlu sentetik snapshot (API'siz, sabit veri) ile katman görünümü açılır; 5 sn yörünge hareketinde ortalama kare süresi ≤ 33 ms (≥ 30 fps), Playwright'in Chromium'unda yazılım çizimiyle ölçülür (eşik bu yüzden 30 fps). Seçim, seçilen öğenin 2B görünümünü açar.

## Kurallar

Ücretli kaynak ve hakem yok. 2B görünümler bu paketten bağımsız kalır.
