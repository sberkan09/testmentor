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

## Uygulamada netleşenler

Sözleşme (`worker/contracts.py`) değiştirilmedi. Sözleşmede tanımsız kalan noktalar:

- **`job_progress`** kalıcı değildir ve `seq` artırmaz. Olayın `seq` alanı son kalıcı olayın numarasıdır; `events_after` ve olay halkası bu olayı içermez, yalnızca `subscribe` ile canlı gelir. API WebSocket'te bu olayı yinelenen-olay süzgecinden geçirmeden olduğu gibi iletir; istemci `seq` ilerletmez (paket 8 ile uyumlu).
- **`stage_waiting_approval`** payload'ı `{"stage": "<kind>"}` (`NodeKind` değeri).
- **Reddedilen komut** gövdesi çıplak `CommandResult`'tır (`detail` içine sarılmaz): `version_conflict` ve `nothing_to_undo` 409, `locked` 423, `invalid` 422. `reason` alanının ilk sözcüğü (`:` ya da boşluğa kadar) kodu belirler; bilinmeyen kod 422. Komut gövdesi şemaya uymazsa da 422 ve `CommandResult(reason="invalid: ...")` döner. `X-User` yoksa 400 (`detail` gövdesi), bilinmeyen proje 404.
- **`POST /locks`**: 200 `{"locked": true}` ya da 423 `{"locked": false}`; `X-User` zorunlu.
- **`POST /projects`** içe alma hatası (`ValueError`, `KeyError`: bozuk `meta`, eşleme, var olan anahtar) 422; `detail` düz metindir.
- **WebSocket**: `after` yoksa ya da `events_after` `None` dönerse ilk mesaj `{"type":"snapshot","snapshot":...}`; aksi halde önce kaçırılan olaylar, sonra canlılar. Abonelik tekrar oynatmadan önce kurulur (`subscribe` çağrılır, bir `await sleep(0)` ile kaydın oluşması beklenir); tekrar oynatılmış `seq`'e eşit ya da küçük canlı olaylar atlanır, böylece boşluk ve yineleme olmaz. Gerçek `subscribe` bir async üreteç ise kayıt ilk okumada olabilir; paket 5 kaydı çağrı anında yapan bir nesne döndürmeli ya da bu sıra yeniden düşünülmeli. Sunucu 20 sn'de bir `{"type":"ping"}` yollar; istemcinin `{"type":"ping"}` mesajına `{"type":"pong"}` döner. Bilinmeyen proje için bağlantı 4404 koduyla kapatılır.
- **Uçlar `async def`**: servis tek thread'li ve olay döngüsüne bağlıdır; `def` uç FastAPI'nin thread havuzunda koşar ve servis bunu `RuntimeError` ile reddeder (paket 5 incelemesi, bulgu 1). `events_after` sunucunun yayınlamadığı ileri bir `seq` için de `None` döner, WebSocket bu durumda snapshot gönderir (bulgu 8).
- **Statik dosya**: `web/dist` varsa `/` altında, bulunmayan yollar için `index.html` yedeğiyle sunulur; API yolları öncelikli. `create_app(service, static_dir=..., ping_interval_s=...)` ikisini de ayarlar.
- **`api/main.py`**: `build_service()` paket 5'in `worker.service` kurucusunu çağıracak tek yerdir; bağımlılıklar `build_deps()` ile `ServiceDeps` olarak hazırlanır. `worker/service.py` yoksa açık hata ile durur; kurucu bağlanana kadar `NotImplementedError`.
- Testler `tests/api/fake_service.py` ile çalışır (`move_requirement`, `edit_test_case`, `pin`, `unpin`, `lock_changed`; diğer komutlar yalnızca `command_applied`). Aşama ve iş görünümleri sahtede boştur.
