---
name: bulut-gpu-kredi-korumasi
description: Runpod ya da başka bir bulutta GPU/CPU pod'u, sunucusuz uç nokta, volume gibi saatlik ücretli bir kaynak açmadan, yeniden başlatmadan, uzun bir deney ya da toplu iş başlatmadan önce ve bir oturum yeniden başladığında kullan. Hangi projede olursa olsun geçerlidir. Kaynağın, onu açan oturum durduğunda bile kendiliğinden kapanmasını sağlayan zorunlu adımları içerir.
---

# Bulut GPU kredi koruması

## Neden var

20 Kasım 2026'da bir deney işi bittikten sonra GPU pod'u 7 saat boşta açık kaldı ve yaklaşık 19 USD boşa gitti. Pod'u silme adımı, onu açan oturumun ayakta kalmasına bağlıydı: oturumun süreci yeniden başladı, izleme işi öldü, silmeyi kimse yapmadı. Kullanıcı bir gün önce tam olarak bu riske karşı uyarmıştı; benzer olay başka projelerde ve oturumlarda da yaşandı. Ders: "dikkatli ol", "ara ara kontrol et", "iş bitince sil" gibi kurallar yetmiyor, çünkü para yakan an tam da modelin çalışmadığı an. Gereken, oturumdan bağımsız çalışan bir mekanizma.

## Temel kural

Saatlik ücretli hiçbir kaynak, onu açan oturumdan bağımsız iki güvence olmadan açılmaz:

1. **En uzun ömür (son tarih):** Kaynak en geç belli bir saatte kendini siler.
2. **Boşta kendini silme:** İş yoksa (ör. GPU kullanımı belirli bir süre %5'in altında) kendini siler.

"Silmeyi izlerken elle yaparım" plan değildir. Oturum her an durabilir: süreç yeniden başlar, kullanım kredisi biter, kullanıcı uygulamaya bakmaz, bir izin isteği yanıtsız kalır.

## Runpod'da nasıl yapılır

Runpod her pod'a `RUNPOD_POD_ID` ve pod'a özel bir `RUNPOD_API_KEY` verir. Pod bunlarla kendini silebilir; ayrı bir anahtar gerekmez (20 Kasım 2026'da gerçek pod'da doğrulandı: pod ~55 sn'de kendini sildi). Başlatma betiğine arka planda şu bekçiyi ekle (`WATCHDOG_DEADLINE` pod oluşturulurken ortam değişkeni olarak epoch saniye verilir):

```bash
self_delete() {
  echo "[watchdog] $1; pod siliniyor"
  until python3 - <<'PY'
import os, sys, urllib.request
pid, key = os.environ["RUNPOD_POD_ID"], os.environ.get("RUNPOD_API_KEY", "")
req = urllib.request.Request(f"https://api.runpod.io/v2/pods/{pid}", method="DELETE",
                             headers={"Authorization": f"Bearer {key}"})
try:
    urllib.request.urlopen(req, timeout=30); sys.exit(0)
except Exception as e:
    print("[watchdog] silme başarısız:", e); sys.exit(1)
PY
  do sleep 30; done
}
(
  set +e; start=$(date +%s); idle=0
  while sleep 60; do
    now=$(date +%s)
    deadline=$(cat /tmp/watchdog_deadline 2>/dev/null || echo "${WATCHDOG_DEADLINE:-0}")
    [ "${deadline:-0}" -gt 0 ] && [ "$now" -ge "$deadline" ] && { self_delete "son tarih doldu"; continue; }
    if command -v nvidia-smi >/dev/null && [ $((now - start)) -ge 1800 ]; then   # ilk 30 dk yükleme
      util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -1 | tr -dc 0-9)
      if [ "${util:-0}" -lt 5 ]; then idle=$((idle + 1)); else idle=0; fi
      [ "$idle" -ge 20 ] && self_delete "GPU 20 dk boşta"
    fi
  done
) >> /tmp/watchdog.log 2>&1 &
```

- Süre gerekirse pod'u yeniden başlatmadan uzat: exec API ile `/tmp/watchdog_deadline` dosyasına yeni epoch yaz.
- Yalnızca indirme yapan pod, iş bitince hemen `self_delete "indirme bitti"` çağırır.
- Bekçiyi bir kez gerçek ve ucuz bir CPU pod'unda dene: son tarihi 90 sn sonraya kur, pod'un kendini sildiğini `get-pod` 404 ile gör. Denemede kendi yedek silmeni hazır tut.

## Pod açmadan önce

1. Açık kaynak var mı bak (`list-pods`); iş bittiyse sil.
2. Bakiyeyi oku; tahmini süre × saatlik fiyat bakiyeyi aşmamalı.
3. Pod'u yalnızca bekçi ve son tarihle aç. Kodda zorunlu kıl: son tarih yoksa pod açma fonksiyonu hata versin, bekçiyi kapatan ayar olmasın.
4. Kullanıcıya saatlik fiyatı, son tarihi ve bakiyeyi yaz.

## İş sürerken

- Birden çok adımlı işi, son adımı her durumda silme olan bir koşucuyla çalıştır (`try/finally`, `trap ... EXIT`, SIGTERM/SIGHUP yakalama). Silme, izleyen oturumun işi değil, işin kendi son adımıdır.
- Arka plana atılan işi kısa aralıklarla izle; hata görürsen önce kaynağı sil, sonra düşün.
- Süre yetmeyecekse bekçiyi kapatma, son tarihi uzat.

## İş bitince

- Kaynağı sil (durdurmak yetmez), `get-pod` 404 ve `list-pods` ile doğrula, süre × fiyatı raporla.

## Oturum yeniden başlarsa ya da kullanıcı uzun süre sonra dönerse

Başka hiçbir şeyden önce açık kaynakları listele. İş bittiyse hemen sil ve kullanıcıya ne kadar süre açık kaldığını ve maliyetini dürüstçe yaz.

## Proje kurulurken

Projede böyle bir mekanizma yoksa, ilk ücretli kaynağı açmadan önce kur ve projenin CLAUDE.md dosyasına bağlayıcı kural olarak yaz. Örnek uygulama: github.com/sberkan09/testmentor deposunda `scripts/infra_render.py` (`watchdog_lines`), `scripts/runpod.py` (`watchdog_deadline`, `extend`), `eval/batch.py` ve `tests/test_watchdog.py`.
