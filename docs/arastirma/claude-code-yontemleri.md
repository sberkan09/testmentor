# Araştırma notu: Claude Code'un verimlilik yöntemleri bize yarar mı

Tarih: 19 Kasım 2026. Durum: ilk tur; "doğrulanacaklar" bölümü açık.

## Kısa cevap

Evet. Claude Code'un verimliliği modele özgü bir numaradan değil, üç mühendislik alışkanlığından geliyor ve üçü de yerel modelle çalışan bu uygulamaya taşınabiliyor:

1. Önek cache'ini bozmamak.
2. Modelin gördüğü bağlamı küçük tutmak.
3. Her üretimi doğrulamak.

Claude Code'un prompt cache'i ile vLLM'in önek cache'i aynı ilkeyle çalışır: isteğin başı daha önce işlenmiş bir istekle birebir aynıysa o kısım yeniden hesaplanmaz. Bu yüzden Claude Code ekibinin cache için koyduğu kurallar bize doğrudan uyar.

Soru iki türlü okunabilir: yöntemleri ürüne taşımak ve geliştirme sürecinde kullanmak. İkisi de aşağıda.

## Ürüne taşınan yöntemler

### 1. Önek cache'i

Claude Code her isteği kararlıdan değişkene doğru dizer: sistem prompt'u ve araç tanımları, proje bağlamı, konuşma. Önekte herhangi bir değişiklik, sonrasındaki her şeyin yeniden işlenmesine yol açar. Ekibin yaşadığı gerçek kırılmalar şunlardı: sabit sistem prompt'una sızan bir zaman damgası, araçların her istekte farklı sırada gelmesi, araç parametrelerindeki küçük değişiklikler.

Bizdeki karşılığı:

- Prompt sırası tasarımda zaten böyle: sistem talimatı, proje kartı, şema ve örnekler, getirilen parçalar, gereksinimler.
- Yeni kural: ilk üç katmana tarih, sayaç ya da kullanıcı adı girmez; listeler deterministik sıralanır. `CLAUDE.md` içinde kurala bağlandı.
- Yeni kural: durum değişikliği öneke değil sona yazılır. Claude Code güncellemeleri sistem prompt'unu değiştirerek değil, bir sonraki mesaja ekleyerek iletir. Bizde kullanıcı düzeltmeleri, sabit testler ve ek talimatlar prompt'un sonuna eklenir.
- Yeni kural: tüm aşamalar tek modelle çalışır. Cache model başınadır; Claude Code'da oturum ortasında model değiştirmek tüm cache'i yeniden kurdurur. Sınıflandırma için küçük bir yardımcı model kullanmak hem cache'i böler hem bellek harcar.
- Yeni kural: yan çağrılar ana öneki paylaşır. Claude Code özetleme çağrısını ayrı bir sistem prompt'uyla değil, ana konuşmanın önekini aynen kullanıp talimatı sona ekleyerek yapar; böylece çağrı cache'ten okur. Bizde öbek adı, doğrulama yöntemi ve onarım çağrıları test üretimiyle aynı sistem talimatını ve proje kartını kullanır.
- Yeni deney (D12): önek ısıtma. Claude Code, aynı önekli ajanları aynı anda başlatırken ilki cache'i yazana kadar diğerlerini kısa süre bekletir. Bizde bir projenin 20 öbeği aynı anda kuyruğa girer; ilk çağrı öneki işleyene kadar diğerlerini bekletmek, 20 çağrının aynı öneki ayrı ayrı hesaplamasını önleyebilir.
- Yeni kural: cache isabet oranı izlenir. Claude Code ekibi oranı sistem sağlığı gibi izler ve düşüşü olay sayar. Bizde sunum motorunun önek cache ölçümleri proje ve aşama bazında kaydedilir.

### 2. Bağlam yönetimi

Anthropic'in bağlam mühendisliği yazısının ana fikri: bağlam büyüdükçe modelin içindeki bilgiyi doğru hatırlama yeteneği düşer; amaç, istenen sonucu veren en küçük ve en yoğun token kümesini bulmaktır.

Bizdeki karşılığı:

- Öbek sınırı (25 gereksinim) ve parça sayısı (ilk 6–8) bu yüzden var. D7 ve D9 doğru değerleri ölçecek.
- Yeni kural: artımlı yeniden üretimde mevcut testler tam metin olarak değil, başlık ve kapsama özeti olarak verilir. Claude Code bağlam dolduğunda önce eski araç çıktılarını temizler, sonra özetler; aynı mantık.
- Her öbek ayrı çağrıdır ve yalnızca yapılandırılmış sonuç döner. Bu, Claude Code'un alt ajan kalıbıdır: iş ayrı bağlamda yapılır, ana bağlama yalnızca özet döner.
- Gerektiğinde yükleme: Claude Code becerilerin yalnızca kısa tanımını baştan yükler, içeriği kullanılınca getirir. Bizde aşama talimatları yalnızca o aşamanın prompt'una girer; proje kartı kısa kalır, belge içeriği aramayla gelir.
- Arama stratejisi: Claude Code kod için önceden hesaplanmış indeks kullanmaz, çünkü kod sık değişir ve indeks bayatlar. Bizim proje belgelerimiz kararlıdır, bu yüzden önceden hesaplanmış indeks doğru seçimdir. Yazının "karma strateji" dediği şey bizim tasarımımız: bir kısmı baştan (proje kartı), kalanı aramayla.
- Yeni kural: ön işleme koda bırakılır. Claude Code'da kancalar veriyi model görmeden önce süzer. Bizde içe almada tekrar eden kalıp metin ve biçim artıkları kodla temizlenir.

### 3. Doğrulama döngüsü

Claude Code'un çalışma döngüsü üç adımdır: bağlam topla, uygula, sonucu doğrula. Resmî öneri, modele her iş için sonucu sınayabileceği bir hedef vermektir.

Bizdeki karşılığı:

- Her üretimi kod doğrular: şema, kapsama, adım yapısı. Hata varsa yalnızca hatalı kısım için onarım çağrısı yapılır.
- Onaylı kip, Claude Code'un plan kipinin karşılığıdır: pahalı iş başlamadan önce plan (öbekler) görülür.
- Geri alma: Claude Code'da önceki tura dönmek, zaten cache'lenmiş öneke dönmektir. Bizde geri alma içerik adresli cache'ten anında gelir.
- Yeni kural: kullanım dökümü. Claude Code token kullanımını kaynağa göre döker ve öneri üretir. Bizde aşama ve proje başına token, iptal edilen çağrı ve cache isabeti kaydedilir; D11 bu veriyi kullanır.

## Taşınmayanlar

- Araç arama ve ertelenmiş araç tanımları: uygulamamızda model araç çağırmıyor. İleride araç kullanan modüller eklenirse yeniden bakılır.
- Cache ömrü ve boşta özetleme: Claude API'sinde cache 5 dakika ya da 1 saatte düşer. Yerel sunucuda süre sınırı yoktur; cache bellek dolunca boşalır. Bizim riskimiz süre değil, aynı anda çok projenin belleği paylaşmasıdır.
- Ajan takımları: resmî dokümana göre plan kipinde yaklaşık 7 kat token harcar. Geliştirmede kullanılmayacak.

## Geliştirme sürecine uygulananlar

Bunlar `CLAUDE.md` içinde kurala bağlandı.

- Paket başına tek oturum, paketler arasında `/clear`. Eski bağlam her mesajda yeniden gönderilir.
- Model oturum başında seçilir. Oturum ortasında model değiştirmek cache'i sıfırlar; `opusplan` ayarı da plan kipine her giriş çıkışta model değiştirir. Bu yüzden "Opus tasarlar, Sonnet yazar" kuralı ayrı oturumlar olarak uygulanır.
- `CLAUDE.md` kısa tutulur (resmî öneri 200 satırın altı). Ayrıntılı iş akışları paket dosyalarında durur ve yalnızca gerektiğinde okunur.
- Gürültülü işler (test koşusu, uzun günlük) alt ajana verilir.
- Karmaşık paketlere plan kipinde başlanır; yanlış yöne giden pahalı iş böyle önlenir.
- Komut satırı aracı olan işte MCP yerine o kullanılır; araç listesi bağlam harcamaz.
- Özetleme talimatı `CLAUDE.md` içinde tanımlıdır.

## Doğrulanacaklar

- vLLM aynı anda gelen aynı önekli istekleri tek batch içinde paylaştırıyor mu, yoksa ısıtma gerçekten gerekli mi. D12 ölçer.
- vLLM ve SGLang'in önek cache ölçümlerinin adları ve istek bazında cache'ten gelen token sayısını bildirip bildirmedikleri. Paket 0'da güncel dokümandan bakılacak.
- Düşünme kipini aşamalar arasında açıp kapatmak yerel motorda öneki bozuyor mu. Claude Code'da çoğu modelde efor seviyesi değişimi cache'i bozuyor; yerelde sohbet şablonuna bağlı. D3 sırasında ölçülecek.
- Proje kartı değiştiğinde tüm önek yeniden işlenir. Kart değişikliğini öneke dokunmadan, sona eklenen bir "kart güncellemesi" olarak verip toplu yenilemeyi sonraya bırakmak mümkün mü; kalite etkisi ölçülmeli.

## Kaynaklar

- [How Claude Code uses prompt caching](https://code.claude.com/docs/en/prompt-caching)
- [Manage costs effectively](https://code.claude.com/docs/en/costs.md)
- [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)
- [Lessons from building Claude Code: Prompt caching is everything](https://claude.com/blog/lessons-from-building-claude-code-prompt-caching-is-everything)
- [Effective context engineering for AI agents](https://anthropic.com/engineering/effective-context-engineering-for-ai-agents)
