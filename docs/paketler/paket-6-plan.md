# Paket 6 planı: API ve olay akışı

23 Kasım 2026. Model: Sonnet. Paket 5'ten sonra. Sözleşme: `worker/contracts.py`; gövdeler ve olaylar tam olarak oradaki modellerdir. Bitti ölçütü (tasarım): bağlantı kopup gelince istemci durumu sunucuyla aynı; iki kullanıcının çakışan komutu doğru reddediliyor.

## Kapsam

- `api/app.py` (FastAPI, `create_app(service: ProjectService)`):
  - `GET /projects` → `[{id, name}]`; `POST /projects` (multipart: `meta` = `ImportRequest` JSON, `file`) → `Snapshot`.
  - `GET /projects/{id}/snapshot` → `Snapshot`.
  - `POST /projects/{id}/commands` (`CommandRequest`, aktör `X-User` başlığı, yoksa 400) → `CommandResult`; `version_conflict` 409, `locked` 423, `invalid` 422, `nothing_to_undo` 409.
  - `POST /projects/{id}/locks` (`{"ref": NodeRef}`) → 200 ya da 423.
  - `GET /projects/{id}/matrix.xlsx` (doğru içerik tipi ve dosya adı).
  - `WS /projects/{id}/events?after=<seq>&user=<ad>`: önce `events_after(after)` (None ise `{"type": "snapshot", "snapshot": ...}` mesajı), sonra canlı `ServerEvent`'ler; ping/pong ile kopma algılama.
- `api/main.py`: `uvicorn api.main:app`. `TESTMENTOR_FAKE_LLM=1`: `services.fake_llm` ve bellek içi depo (geliştirme ve Playwright); aksi halde `ClientComplete`, `Embedder`, `PostgresStore` (`TESTMENTOR_PG_DSN`). Statik dosya: `web/dist` varsa `/` altında sunulur.
- `api/export_schema.py`: `python -m api.export_schema` → `api/schema.json` (sözleşme modellerinin JSON şeması; paket 8 TypeScript tiplerini bundan üretir). Dosya depoya girer; test, üretilen dosyanın güncel olduğunu denetler.

## Testler

- **Bitti testi 1** `tests/api/test_reconnect.py`: istemci WebSocket'e bağlanır, olayları uygular, bağlantı koparılır, bu arada başka kullanıcı komut gönderir, istemci son `seq` ile yeniden bağlanır ve eksik olayları alır; istemcinin olaylardan kurduğu düğüm haritası `snapshot` ile aynıdır. Olaylar halkadan düştüyse snapshot mesajı gelir.
- **Bitti testi 2** `tests/api/test_conflict.py`: iki kullanıcı aynı test durumunu aynı sürümle düzenler; ilki kabul, ikincisi 409 ve güncel sürüm; kilitli düğüme ikinci kullanıcının düzenlemesi 423.
- Rotalar, içe alma (csv), xlsx indirme, şema dosyasının güncelliği. `fastapi.testclient` ve `httpx`; model yok.

## Kurallar

Ücretli kaynak ve hakem yok. `make test`, `make lint` yeşil.
