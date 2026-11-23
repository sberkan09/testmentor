# Uçtan uca test (Playwright)

`flow.spec.ts` paket 8'in bitti testidir. Akış (her adım `test.step`, her öğe `data-testid`):

1. Kullanıcı adı girilir.
2. Altın set v0'dan üretilen csv yüklenir, kolon eşleme önizlemesi doğrulanır.
3. Öbekler ve aşama çubuğu görünür.
4. Bir gereksinim fareyle sürüklenip başka öbeğe taşınır.
5. Bir test durumunun adımı düzenlenir, kaydedilir, sabitlenir.
6. Matris görünümünde kapsama görünür.
7. xlsx indirilir, dosya boş değildir.
8. İkinci tarayıcı bağlamında (başka kullanıcı) güncel durum, taşınan gereksinim ve düzenleme kilidi görünür.

## Gerçek API ile (paket 6 birleştikten sonra)

```bash
cd web && npm ci            # ya da: make web-install
make web-e2e                # = cd web && npm run e2e
```

`playwright.config.ts` iki sunucu açar (zaten çalışan varsa onları kullanır):

- API: `TESTMENTOR_FAKE_LLM=1 uv run uvicorn api.main:app --port 8000` (depo kökünde)
- Web: `npm run build && vite preview --port 4173` (`/projects` isteklerini ve WebSocket'i API'ye yönlendirir)

Sunucuları elle açmak istersen:

```bash
TESTMENTOR_FAKE_LLM=1 uv run uvicorn api.main:app --port 8000 &
cd web && npm run build && npx vite preview --port 4173 &
cd web && npx playwright test --trace off
```

Playwright tarayıcısı kuruludur; `playwright install` çalıştırma. Config, `/opt/pw-browsers/chromium-1243/chrome-linux64/chrome` varsa onu kullanır; başka yerdeyse `PW_CHROMIUM_PATH=...` ver. Gerekirse `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`.

Her proje anahtarı koşuya özgüdür (zaman damgası), bu yüzden aynı API'de tekrar koşabilir.

## Paket 10 testleri

- `documents.spec.ts`: Belgeler sekmesinden belge yüklenir; öbek denetçisinde arama düğümünün parça kimlikleri (`<belge>#<sıra>`) görünür, test setlerinin sürümü artar (yeniden üretildi).
- `auth.spec.ts`: parolalı giriş (yanlış parola, jetonsuz istek 401, bozuk jetonla giriş ekranına dönüş). `E2E_PASSWORD` verilmezse sunucunun başlık kipinde olduğu varsayılır ve yalnızca parola alanının olmadığı denetlenir.
- `helpers.ts` içindeki `login` parola alanı görünürse `E2E_PASSWORD` ile doldurur; `flow.spec.ts` ve `documents.spec.ts` iki kipte de koşar.

## Compose ile kurulan uygulamaya karşı (paket 10)

`E2E_BASE_URL` verilince Playwright sunucu açmaz, o adresi kullanır (API ve derlenmiş ön yüz aynı adreste):

```bash
# harici profili, sahte model, Postgres; .env yerine bir deneme dosyası (docs/pilot.md)
docker compose -p tm10 -f infra/compose.yaml --env-file deneme.env --profile harici up -d --wait
echo "pilot-parola-123" | docker compose -p tm10 -f infra/compose.yaml --env-file deneme.env --profile harici exec -T app python -m api.users add ayse
echo "pilot-parola-123" | docker compose -p tm10 -f infra/compose.yaml --env-file deneme.env --profile harici exec -T app python -m api.users add mehmet
cd web && E2E_BASE_URL=http://127.0.0.1:18000 E2E_PASSWORD=pilot-parola-123 npx playwright test --trace off
```

Deneme dosyası: `POSTGRES_PASSWORD`, `LLM_API_KEY` (sahte modelde kullanılmaz), `TESTMENTOR_AUTH_SECRET` (en az 32 karakter), `TESTMENTOR_FAKE_LLM=1`, `APP_PORT=18000`, `TESTMENTOR_DATA_DIR` (users.yaml klasörü), `LLM_BASE_URL` ve `EMBEDDING_BASE_URL` (sahte modelde kullanılmaz).

## Sahte API ile (geliştirme ve ön doğrulama)

Arka uç yokken `web/mock/server.mjs` sözleşmeye göre çalışan küçük bir sahte API sunar (akışlı üretim, sürüm çakışması, kilit, geri alma dahil):

```bash
cd web && npm run e2e:mock          # sahte API + önizleme açar, aynı spec'i koşar
cd web && npm run mock              # yalnızca sahte API (8000); TESTMENTOR_API=http://127.0.0.1:8000 npm run dev
```

Bu paket 8 oturumunda sahte API ile yeşildir. Gerçek API'de beklenen farklar: `case-*` satırları test durumları üretilince görünür (zaman aşımı 60 sn), öbek adları gerçek model/fake_llm çıktısıdır.

## Demo videosu

```bash
E2E_VIDEO=on npx playwright test --trace off    # 1440x900, adımlar arasında bekleme
```

Video `test-results/` altına yazılır. `E2E_VIDEO` kapalıyken beklemeler yoktur.
