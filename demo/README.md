# Demo videosu

Senaryo `web/e2e/demo.spec.ts` (altın set v1 KDH "Vatandaş Başvuru Portalı", 120 gereksinim):
içe alma ve kolon eşleme → öbekler, adlar ve test durumları (yerel model) → test durumunu adım adım
düzeltme ve sabitleme → gereksinimi başka öbeğe taşıma (artımlı yeniden üretim) → matris ve xlsx.
Ekranın altında Türkçe açıklama şeridi çizilir; model üretimi süren bölümler videoda hızlandırılır.

## Sahte modelle (GPU yok)

```bash
cd web && DEMO=1 DEMO_FRAMES=/tmp/demo/frames DEMO_MARKS=/tmp/demo/marks.json \
  npx playwright test e2e/demo.spec.ts --trace off
cd .. && uv run python demo/make_video.py /tmp/demo/frames /tmp/demo/marks.json demo.mp4
# Hazır kayıt (gerçek model, 23.11): docs/demo/testmentor-demo.mp4
```

Playwright yapılandırması API'yi `TESTMENTOR_FAKE_LLM=1` ile açar (8000 portunda çalışan bir API
yoksa).

## Gerçek modelle (Runpod)

1. `make up MAX_HOURS=1` (bekçili pod; fiyat, son tarih, bakiye yazılır).
2. API'yi pod'a bağlı aç: `set -a; . ./.env; set +a; eval "$(uv run python demo/pod_env.py)";
   TESTMENTOR_STORE=memory uv run uvicorn api.main:app --port 8000`.
3. Yukarıdaki Playwright komutu (çalışan API'yi kullanır).
4. `make down` (404 ile doğrulanır).

Video karelerden üretilir (Chromium ekran akışı, CDP); Playwright'in kendi video kaydedicisi bu
ortamdaki ffmpeg sürümüyle çalışmadı.
