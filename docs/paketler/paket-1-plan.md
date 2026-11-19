# Paket 1 planı

Tarih: 19 Kasım 2026. Görev tanımı: [`paket-1-olcum.md`](paket-1-olcum.md). Önkoşul paket 0 birleşti (PR #1).

## Durum ve engeller

- **Hakem (katman 2) için Claude API anahtarı yok.** Vekil Anthropic host'larına anahtar eklemiyor; anahtar yalnızca ortam değişkeni (`ANTHROPIC_API_KEY`) olarak verilebilir ve yeni oturumda görünür. Kullanıcıya bildirildi. Hakem, kayıtlı çıktılar üzerinde GPU olmadan sonradan koşacak şekilde ayrı komut olarak yazılır: `python -m eval.judge results/<koşu>`.
- Sonuç: D1 (hız ve hata oranı) ve katman 1 eşikleri anahtarsız karar verir. D2'nin ana ölçütü `check_recall` hakem ister; hakem koşana kadar D2–D3 kararları "katman 1 + hız" ile geçici yazılır ve raporda işaretlenir.
- D0 için test mühendisi yok: hakemle devam edilir, raporlara uyarı yazılır.
- Resmî 4 bit Qwen3.8-27B deposu yok (Qwen kuruluşunda yalnızca BF16 ve FP8). D4'ün 4 bit kolu BF16 ağırlıklardan çalışma anında nicemlemeyle denenir; üçüncü taraf depo kullanılmaz.

## Mimari

- `core/schemas.py`: test durumu seti ve doğrulama yöntemi çıktıları (pydantic, şema buradan türer).
- `core/prompts.py`: sürümlü şablonlar. Sıra: ortak sistem talimatı, proje kartı, aşama şeması ve örnekleri, getirilen parçalar (bu pakette yok), gereksinimler. Sürüm `input_hash` hesabına girer.
- `core/hashing.py`, `core/clustering.py` (kosinüs, agglomerative), `core/metrics.py` (katman 1, model çağrısı yok).
- `eval/pipeline.py`: en yalın pipeline. Embedding ve kümeleme; proje başına toplu yöntem sınıflandırması; öbek başına paralel test üretimi (yöntemi Test olan gereksinimlere test, diğerleri bağlam); eksik kapsama için onarım çağrısı.
- `eval/run.py`: `python -m eval.run --config config/experiments/<deney>.yaml`. Çıktı `results/<koşu>/outputs.jsonl`, `metrics.json`, `report.md`. `throughput` bölümü D1 ve D5 için eşzamanlılık basamaklarında yük ölçer. `--repeat 2` iki koşuyu katman 1'de karşılaştırır.
- `eval/judge.py` + `services/judge_client.py`: hakem, Anthropic SDK ile Claude Sonnet 5.5. Rubrik sürümlü, çıktılar girdi hash'iyle diskte cache'lenir.
- Ayarlar: `config/pipeline.yaml` (çalışma varsayımları), `config/experiments/*.yaml` (her deney tek değişken), `config/judge.yaml`.
- Runpod: tek GPU pod'u açılır; model ve sunucu ayarları pod silinmeden `PATCH` ile değiştirilir (`make reconfigure`). İmaj yeniden çekilmez, deneyler toplu koşar.

## GPU planı ve maliyet tahmini

| Oturum | İş | Tahmini süre |
| --- | --- | --- |
| vLLM pod | D1 vLLM (1/8/16/32), D2 Qwen ×2 (tekrar), D3 (düşünme, sıcaklık), D5 (dizi sınırı, bağlam), D12, D2 Gemma, D2 gpt-oss, D4 (BF16, FP8, 4 bit) | 2,5 saat |
| SGLang pod | D1 SGLang (1/8/16/32) ve kalite koşusu | 0,5 saat |
| İndirme | Qwen3.8-27B BF16 (yaklaşık 54 GB); volume 200'den 260 GB'a büyütülür (+60 GB, yaklaşık 4,2 USD/ay) | 0,3 saat CPU |
| **Toplam** | yaklaşık 3 GPU saati × 2,69 USD | **yaklaşık 8–10 USD** |

Paket tanımında bütçe yazmıyor. Kullanıcı bütçeyi açtı; bu pakette 15 USD'yi geçmeden durmayı hedef alıyorum, 20 USD'de durup bildiririm. Uzun koşulardan önce bakiye denetlenir, koşu sırasında günlük ve GPU belleği kısa aralıklarla izlenir, iş biter bitmez pod silinir.
