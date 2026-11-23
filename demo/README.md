# Demo

Senaryo `web/e2e/demo.spec.ts`: altın set v1 KDH "Vatandaş Başvuru Portalı" (120 gereksinim, 60 Türkçe ve 60 İngilizce) ve sistemin iki belgesi (`eval/corpus/kdh/system/`: Kavramsal İşletim, Yazılım Tasarım; altın set için yazılmış kurgusal belgeler).

Akış:

1. Parolalı giriş.
2. İçe alma ve kolon eşleme.
3. Belgeleri bilgi havuzuna yükleme.
4. Yerel modelle öbekler, adlar ve test durumları; öbeğin getirilen parçaları.
5. Test durumunu adım adım düzeltme ve sabitleme (örnek havuzuna girer).
6. Gereksinimi başka öbeğe taşıma (artımlı yeniden üretim).
7. Matris ve xlsx.
8. 3B katman görünümü.

Ekranın altında Türkçe açıklama şeridi çizilir. Model üretimi süren bölümler videoda hızlandırılır.

## Canlı demo: `make demo`

Sunumu yapan makinede çalışır. Gerekenler: `uv`, Node 22, `.env` içinde Runpod ve model anahtarları.

1. Pod `make up` ile bekçili açılır. Varsayılan en uzun ömür 2 saattir (`HOURS=3 make demo` ile değişir).
2. Uygulama bu makinede `http://127.0.0.1:8080` adresinde açılır: bellek içi depo, parolalı giriş. Kullanıcı `ayse`; parola rastgele üretilir ve ekrana yazılır (ya da `DEMO_PASSWORD` ile verilir).
3. Proje ve iki belge yüklenir, ilk üretim beklenir (`demo/preload.py`, yaklaşık 4–5 dakika). Sunuma bu hazır projeyle başlanır.
4. Ctrl-C ile biter. Betik nasıl biterse bitsin `make down` çalışır ve pod silinir. Bekçi ayrıca süre dolunca ya da GPU 20 dakika boşta kalınca pod'u siler. Uzun bir sunumda başka bir terminalden `make extend HOURS=1`.

Saatlik ücret yaklaşık 2,7 USD'dir. Bir şey ters giderse yedek olarak hazır video kullanılır.

## Demo videosu: `make demo-video OUT=dizin`

Aynı kurulum. Ardından Playwright senaryosu Chromium ekran akışını kare kare kaydeder (CDP). `demo/make_video.py` bekleme aralıklarını hızlandırarak MP4 üretir (`OUT/demo.mp4`). Sonunda pod silinir.

Hazır kayıtlar:

- `docs/demo/testmentor-demo.mp4`: bilgi havuzu sunucuya bağlanmadan önceki ilk sürüm (23.11).
- `docs/demo/testmentor-demo-v2.mp4`: belgeler, örnek havuzu, parolalı giriş ve 3B görünüm.

## Sahte modelle (GPU yok, senaryo denemesi)

```bash
cd web && DEMO=1 DEMO_FRAMES=/tmp/demo/frames DEMO_MARKS=/tmp/demo/marks.json \
  npx playwright test e2e/demo.spec.ts --trace off
cd .. && uv run python demo/make_video.py /tmp/demo/frames /tmp/demo/marks.json demo.mp4
```

Playwright yapılandırması API'yi `TESTMENTOR_FAKE_LLM=1` ile açar (8000 portunda çalışan bir API yoksa). Parolalı kipi denemek için API'yi `TESTMENTOR_AUTH_MODE=password` ile ayrıca açın ve `E2E_BASE_URL`, `E2E_PASSWORD` verin.

Playwright'in kendi video kaydedicisi bu ortamdaki ffmpeg sürümüyle çalışmadı; bu yüzden video karelerden üretilir.
