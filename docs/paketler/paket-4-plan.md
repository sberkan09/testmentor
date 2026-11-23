# Paket 4 planı: içe alma, matris görünümü, xlsx dışa aktarım

23 Kasım 2026. Model: Sonnet. Sözleşme: `worker/contracts.py` (`ImportRequest`, `ColumnMapping`, `MatrixRowView`); değiştirilmez. Bitti ölçütü (tasarım): örnek set uçtan uca matrise dönüşüyor.

## Kapsam

İçinde:
- `core/importing.py` (saf): satırlardan (`list[dict[str, str]]`) `RequirementContent` listesine. Kolon eşleme (`ColumnMapping`), boş satır atlama, metin temizliği (fazla boşluk, satır sonları, baştaki madde işaretleri), kimliksiz gereksinime `import.id_prefix` + sıra (`REQ-1`…), çift kimlikte hata (`ImportError` alt sınıfı, satır numarasıyla), boş metinde hata, `import.max_requirements` sınırı. Dil algılama (kolon yoksa): Türkçe karakterler (ç ğ ı ö ş ü İ) ve sık Türkçe kelimelerle `tr`, aksi halde `en`; deterministik.
- `services/importer.py`: `read_rows(data: bytes, filename: str, sheet: str | None) -> list[dict[str, str]]` (csv: `import.encodings` sırasıyla, ayırıcı `csv.Sniffer`; xlsx: openpyxl, ilk satır başlık, hücreler metne); `build_project(request: ImportRequest, data, filename, *, embed, settings: StageSettings, stage_configs) -> ProjectState`: satırlar → gereksinimler → `embed` ile vektörler → `core.stages.clustering.initial_membership` (öbek anahtarları `C001`, `C002`…) → `core.graph.new_project` (kart metni boşsa `Project: <name> (<key>)`, yöntemler boşsa ayardaki varsayılan) → embedding ve öbekleme ağacı düğümleri aynı vektörlerden `settle_many` ile yazılır (embed bir kez çağrılır).
- `core/matrix_view.py` (saf): `matrix_rows(state, test_method) -> list[MatrixRowView]`, gereksinim kimliği sırasıyla. Öbek adı `CLUSTER_LABEL` içeriğinden, yoksa öbek anahtarı. Uyarılar: yöntemler `test_method` içerip kapsanmamış → `test_without_case`; içermeyip kapsanmış → `case_without_test_method`. Yöntem düğümü içeriksizse yöntem listesi boş ve uyarı yok.
- `services/xlsx_export.py`: `matrix_xlsx(state, test_method) -> bytes` (openpyxl): "Matris" (kimlik, metin, dil, öbek, öbek adı, yöntemler, test durumları, kapsandı, uyarı), "Test durumları" (anahtar, öbek, başlık, kapsadığı gereksinimler, tip, öncelik, ön koşul, test girdisi, varsayım, adım no, işlem, beklenen sonuç; her adım ayrı satır), "Uyarılar". Başlıklar Türkçe; kalın başlık satırı, dondurulmuş ilk satır, makul kolon genişlikleri.

Dışında: API ve kuyruk (paket 5, 6), arayüz (paket 8).

## Testler (önce yazılır)

- `tests/test_importing.py`: eşleme, temizlik, kimlik verme, çift kimlik ve boş metin hataları (satır numarası), dil algılama, sınır.
- `tests/test_importer.py`: csv (utf-8-sig, cp1254, `;` ayırıcı) ve xlsx okuma; `build_project` sonucu `analyze(state).stale` içinde embedding ve ağaç yok, her gereksinim tek öbekte, embed bir kez çağrıldı.
- `tests/test_matrix_view.py`: iki uyarı, kapsama, öbek adı yedeği.
- **Bitti testi** `tests/test_import_matrix_e2e.py`: altın set v0'ın 40 gereksinimi testte csv'ye yazılır → `build_project` (`services.fake_llm.FakeEmbed`) → `eval.stage_driver.drive` (`services.fake_llm.FakeComplete`) → `analyze` bayat düğüm bırakmaz → `matrix_rows` 40 satır, Test yöntemli her gereksinim kapsanmış → `matrix_xlsx` openpyxl ile açılır, "Matris" sayfasında 40 veri satırı ve test durumu sayfasında en az 40 satır. Aynı akış xlsx girdiyle bir kez daha.

## Kurallar

`core/` dosya, HTTP ya da veritabanı içe aktarmaz. Model çağrısı yok. Ücretli kaynak ve hakem yok. `make test`, `make lint` yeşil. Ayarlar `config/pipeline.yaml` `import:` bölümünden (`services.settings` üzerinden okunur).

## Uygulamada netleşenler

- `ImportError` alt sınıfı yerine `core.importing.RequirementImportError(ValueError)` (`row` alanı elektronik tablo satırı: başlık 1, ilk veri satırı 2); yerleşik `ImportError`'ı gölgelemez ve "modül içe aktarılamadı" anlamı taşımaz.
- `import:` ayarı için `core.settings.ImportSettings` ve `services.settings.load_import_settings` / `load_default_methods` eklendi; `build_project` bunları `import_settings` ve `default_methods` anahtar sözcükleriyle alır (verilmezse config'ten okur) ve `async`'tir (`embed` async).
- csv'de `csv.Sniffer` yalnızca ayırıcı için kullanılır; tırnak karakteri tahmini içinde tırnaklı sözcük olan hücrede (altın set KK-004) satırı bozduğu için tırnak `"` sabittir.
- Tohum dalında `worker/contracts.py`, bu plan ve `fake_llm` yoktu; ana oturumun dalıyla birleştirildi.
- `core/importing.py` `worker.contracts.ColumnMapping` içe aktarır (sözleşme modeli saf pydantic; dosya, HTTP ya da veritabanı yok).
- Matris satırları `matrix_rows` içinde düğüm durumundan canlı hesaplanır (`MATRIX_ROW` düğümü bayatken de görünüm doğru); xlsx metin hücreleri formül sayılmasın diye açıkça metin türünde yazılır.
