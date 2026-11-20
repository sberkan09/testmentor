---
name: runpod-kredi-korumasi
description: Runpod'da pod, volume ya da endpoint gibi ücretli bir kaynak açmadan, yeniden yapılandırmadan, deney ya da uzun iş başlatmadan önce ve oturum yeniden başladığında oku. Boşta kalan pod'un kredi yakmasını önleyen zorunlu adımları içerir.
---

# Runpod kredi koruması

Bir pod'u silmek, onu açan oturumun ayakta kalmasına bağlı olamaz. 20 Kasım 2026'da tam olarak bu oldu: deneyler bitti, oturum süreci yeniden başladı, silme adımı hiç çalışmadı ve pod 7 saat boşta kalarak yaklaşık 19 USD harcadı. Bu skill'in her adımı bunu yapısal olarak önlemek içindir.

## Pod açmadan önce

1. Açık pod var mı bak: `make status`, `list-pods`. Varsa önce onu kapat ya da kullan.
2. Bakiyeyi oku (`make balance`). İşin tahmini süresi × saatlik fiyat bakiyenin altında olmalı.
3. Pod'u yalnızca `make up` (ya da `make batch`) ile aç. Bu yollar pod'a bekçi ve son tarih koyar:
   - GPU `watchdog.idle_minutes` (20) dakika boşta kalırsa pod kendini siler.
   - `watchdog.max_hours` dolunca pod kendini siler.
   - Bekçi `RUNPOD_POD_ID` ve Runpod'un pod'a verdiği `RUNPOD_API_KEY` ile `DELETE /v2/pods/{id}` çağırır (20 Kasım 2026'da gerçek bir pod'da doğrulandı).
4. Kullanıcıya saatlik fiyatı, son tarihi ve bakiyeyi yaz.

## İş sürerken

- Birden çok adımlı işler `make batch BATCH=<ad>` ile koşar (`config/batches/`). `eval/batch.py` son adımda, hata ya da sinyal olsa bile `make down` çalıştırır.
- Elle sıralı iş yazıyorsan sonuna `make down` ekle; arka plana atılan işin çıktısını izle.
- Süre yetmeyecekse `make extend HOURS=1`. Bekçiyi kapatma, `watchdog.enabled: false` yapma.
- İzleme aralıkları kısa olsun; bir hata görürsen işi durdur ve pod'u sil, sonra düşün.

## İş bitince

- `make down`; `get-pod` 404 ve `list-pods` boş olmalı. Süre × fiyatı raporla.
- `docs/altyapi.md` doğrulama defterine yaz.

## Oturum yeniden başlarsa

Başka hiçbir şeyden önce açık pod'a bak. Varsa ve iş bittiyse hemen sil; iş sürüyorsa bekçinin son tarihini kontrol et.

## Başka projelere taşımak için

Aynı kural her bulut GPU işinde geçerlidir: kaynak, açan oturumdan bağımsız bir ömür sınırı ve boşta kendini silme mekanizması olmadan açılmaz. Bu dosyayı ya da CLAUDE.md'deki "Kredi koruması" bölümünü diğer projelerin CLAUDE.md dosyasına kopyala.
