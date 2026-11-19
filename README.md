# testmentor

Gereksinim setinden test durumlarına ve gereksinim-test matrisine giden, yerel modelle çalışan stüdyo uygulaması.

Depo şu an yalnızca tasarımı ve ölçüm verisini içerir; kod henüz yazılmadı.

- [`docs/tasarim.md`](docs/tasarim.md): teknik tasarım. Veri modeli, pipeline aşamaları, deney planı, cache ve kuyruk, bilgi havuzu, API, arayüz, iş paketleri.
- [`eval/golden/altin-set-v0.json`](eval/golden/altin-set-v0.json): altın set v0.1. Beş sentetik proje, 40 gereksinim, 15 referans öbek, 49 referans test durumu (135 adım). Sentetiktir; bir test mühendisinin gözden geçirmesi gerekir.

Geliştirme `docs/tasarim.md` içindeki iş paketleri sırasıyla ilerler. İlk iş paket 0 (altyapı) ve paket 1'dir (ölçüm koşucusu ve D0–D5 deneyleri).
