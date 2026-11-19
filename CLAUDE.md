# testmentor: çalışma talimatı

Gereksinim setinden test durumlarına ve gereksinim-test matrisine giden, yerel modelle çalışan stüdyo uygulaması. Kod henüz yok; iş paketler halinde ilerler.

## Önce oku

- `docs/tasarim.md` tek doğruluk kaynağıdır. Koda başlamadan önce Özet bölümünü ve üzerinde çalıştığın paketle ilgili bölümleri oku.
- Paket görev tanımları `docs/paketler/` altındadır. Yalnızca verilen paketin kapsamında çalış.
- Tasarımdan sapman gerekiyorsa önce `docs/tasarim.md` dosyasını güncelle (ayrı commit), sonra kodu yaz. Sessizce sapma.
- Bir kararı tahminle verme: `docs/tasarim.md` içindeki Deney planı tablosunda karşılığı varsa çalışma varsayımını kullan ve deneyi işaretle.

## Depo düzeni

- `core/`: grafik, hash, aşamalar, prompt şablonları. Saf Python.
- `services/`: `LLMClient`, embedding ve arama istemcileri.
- `worker/`: iş kuyruğu. `api/`: REST ve WebSocket. `web/`: React uygulaması.
- `eval/`: altın set ve ölçüm koşucusu. `config/`: tüm ayarlar. `infra/`: Docker Compose.
- `docs/`: tasarım, paket tanımları, deney raporları, araştırma notları.

## Kod kuralları

- Python 3.12, `uv`, `ruff`, `pytest`, `pydantic` v2. Ön yüzde TypeScript katı kip.
- Kod ve tanımlayıcılar İngilizce; dokümanlar, kullanıcıya görünen metinler ve commit mesajları Türkçe.
- `core/` HTTP, veritabanı sürücüsü ya da model istemcisi içe aktarmaz. Birim testleri model çağırmaz.
- Model çağrıları yalnızca `services/llm_client.py` üzerinden, OpenAI uyumlu API ile yapılır. Motor ve model adı kodda geçmez.
- Ayarlanabilir her değer (model, motor, eşikler, öbek sınırı, bekleme süresi, çıktı şeması, doğrulama yöntemi listesi) `config/` altında durur. Deney sonucu tek satırlık ayar değişikliğiyle uygulanabilmelidir.
- Önce arayüz ve test, sonra uygulama. Paketin bitti ölçütü `docs/tasarim.md` içindedir; ölçüt geçmeden paket bitmiş sayılmaz.

## Prompt kuralları

Önek cache'i tam eşleşmeyle çalışır; önekte tek karakter değişirse sonrası yeniden hesaplanır.

- Sıra: sistem talimatı, proje kartı, çıktı şeması ve örnekler, getirilen parçalar, gereksinimler.
- İlk üç katmana tarih, sayaç, kullanıcı adı ya da rastgele sıralı liste yazma. Listeleri deterministik sırala.
- Durum değişikliklerini (kullanıcı düzeltmeleri, sabit testler, ek talimat) prompt'un sonuna ekle, öneki değiştirme.
- Tüm aşamalar aynı sistem talimatını ve proje kartını paylaşır. Yardımcı çağrılar (öbek adı, onarım) ayrı bir sistem prompt'u kullanmaz.
- Her prompt şablonu sürüm numarası taşır ve sürüm `input_hash` hesabına girer.
- Çıktı JSON şemasına bağlıdır ve şema `pydantic` modelinden türetilir. Her test adımının kendi beklenen sonucu vardır. Ön koşul, test girdisi ve varsayım gerekmiyorsa boş kalır.

## Veri ve Runpod

- Gerçek proje verisi bu depoya ve Runpod'a girmez. Deneyler yalnızca `eval/golden/` altındaki sentetik setle yapılır.
- Model ağırlıklarını yalnızca modelin resmî kuruluş hesabından indir; benzer adlı depolar vardır.
- Krediyi yalnızca gerektiği kadar harca. Ücret doğuran bir kaynak oluşturmadan önce GPU'yu ve saatlik fiyatını `list-gpu-types` çıktısından yaz; paketin bütçesini aşma.
- GPU pod'unu yalnızca model yükleme ve ölçüm için aç. Kod ve birim testleri pod kapalıyken yazılır.
- Kalıcılık network volume ile sağlanır (pod ile aynı veri merkezi, yalnızca Secure Cloud). Durdurulmuş pod'a güvenme: yerel diskli pod yalnızca aynı makinede yeniden başlar ve GPU o arada gidebilir.
- İş bitince pod'u sil, durdurmakla yetinme. `get-pod` (404) ve `list-pods` ile doğrula; süre çarpı fiyatı raporla.
- Uzun bir koşudan önce hesap bakiyesini kontrol et. Bakiye sıfırlanınca pod durur ve çalışan iş kaybolur.
- Hesaptaki başka projelere ait kaynaklara (pod, volume, endpoint) dokunma.
- Hugging Face anahtarı Runpod Secret olarak durur ve `{{ RUNPOD_SECRET_HF_TOKEN }}` ile verilir. Anahtarı isteme, yazdırma, depoya koyma.
- Pod'da genel amaçlı komut çalıştıran bir uç nokta açma. Dışarı açılan her uç nokta anahtar korumalı olur. Runpod HTTP vekili yaklaşık 125 saniyede zaman aşımına uğrar; uzun üretimde akış kullan.
- Her Runpod koşusundan sonra `docs/altyapi.md` içindeki doğrulama defterini güncelle: GPU, imaj etiketi, süre, bellek tepe değeri, maliyet, karşılaşılan tuzaklar.
- Diğer anahtarlar `.env` dosyasında durur ve depoya girmez.

## Claude Code ile çalışma

- Bir paket bir oturumdur. Paketler arasında `/clear` kullan.
- Modeli oturum başında seç, ortasında değiştirme: her değişim prompt cache'ini sıfırlar. Tasarım (Opus) ve uygulama (Sonnet) ayrı oturumlardır.
- Paket 2, 3 ve 5'e plan kipinde başla; planı `docs/paketler/` altındaki dosyaya yaz.
- Gürültülü işleri (test koşusu, uzun günlük, doküman tarama) alt ajana ver; ana oturuma yalnızca özet dönsün.
- Test çıktısını kısa tut: `pytest -q --tb=short`. Uzun çıktıyı dosyaya yaz ve yalnızca hata satırlarını oku.
- Komut satırı aracı varsa onu kullan (`git`, `gh`, `docker`, `runpodctl`).
- Doğrulama olmadan iş bitirme: her değişiklik için geçen bir test ya da komut çıktısı göster.

## Özetleme talimatı

Oturum özetlenirken şunlar korunur: üzerinde çalışılan paket ve bitti ölçütü, değiştirilen dosyalar, başarısız testler ve nedenleri, tasarımdan sapma kararları, çalışan Runpod kaynakları.

## Komutlar

Ayrıntı ve servis adresleri: `docs/altyapi.md`. Paket 1 `make eval` hedefini ekler.

- `make test`: birim testleri (model çağrısı yok). `make lint`: ruff.
- `make up` / `make down`: Runpod GPU pod'unu aç ve hazır olana kadar bekle / sil ve 404 ile doğrula. Motor ve model: `ENGINE=sglang MODEL=gemma-4-31b make up`.
- `make smoke`: açık pod'a 16 eşzamanlı, şemaya bağlı istek ve önek cache ölçümü.
- `make volume`, `make download`, `make download-down`: network volume ve ağırlık indirme (ücretli).
- `make balance`, `make status`: bakiye, kayıtlı kaynaklar.
- `make compose`: `infra/compose.yaml` dosyasını `config/` altından yeniden üret. `make local-up`: yerelde ya da üretimde compose.
