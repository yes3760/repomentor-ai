"""The rule catalogue: every finding RepoMentor can report, in one place.

Analyzers decide *whether* a rule fires and *where*; the wording, severity,
category and effort estimate live here. Texts may contain `{placeholders}`
filled from the `values` passed to `make_issue`.
"""

from __future__ import annotations

from dataclasses import dataclass

from repomentor.models.issue import Category, Issue, Location, Severity

POTENTIAL_NOTE = " Bu bulgu potansiyel risk olarak işaretlenmiştir; kesin güvenlik açığı anlamına gelmez."


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: Severity
    category: Category
    explanation: str
    recommendation: str
    effort: int


_RULES = [
    # --- Documentation -----------------------------------------------------------------
    Rule("DOC001", "README dosyası yok", "high", "documentation",
         "README, projeyi açan herkesin ilk gördüğü sayfadır. Yoksa projenin ne yaptığı, nasıl kurulduğu ve çalıştırıldığı anlaşılmaz; işe alım yapan biri büyük ihtimalle projeyi kapatır.",
         "Kök dizine README.md ekleyin: proje açıklaması, özellikler, kurulum, çalıştırma komutu, ekran görüntüsü ve kullanılan teknolojiler. README sekmesindeki hazır taslağı kullanabilirsiniz.", 45),
    Rule("DOC002", "README çok kısa", "medium", "documentation",
         "README yalnızca {words} kelime. Okuyan kişi projenin amacını ve nasıl kullanılacağını anlamakta zorlanır.",
         "Projenin hangi problemi çözdüğünü 2-3 cümleyle anlatın; ardından özellikler, kurulum ve kullanım bölümlerini ekleyin.", 30),
    Rule("DOC003", "README'de 'Kurulum adımları' bölümü eksik", "medium", "documentation",
         "Projeyi klonlayan biri bağımlılıkları nasıl kuracağını bilemez.",
         "`python -m venv .venv` ve `pip install -r requirements.txt` gibi adım adım kurulum komutları ekleyin.", 10),
    Rule("DOC004", "README'de 'Kullanım / çalıştırma' bölümü eksik", "medium", "documentation",
         "Uygulamanın nasıl başlatılacağı belirtilmemiş; çalıştırmak deneme-yanılma gerektirir.",
         "Çalıştırma komutunu (örn. `streamlit run app.py` / `python main.py`) ve örnek bir kullanım senaryosunu yazın.", 15),
    Rule("DOC005", "README'de 'Özellikler' bölümü eksik", "low", "documentation",
         "Projenin neler yapabildiği bir bakışta görünmüyor.",
         "Madde işaretli kısa bir 'Özellikler' bölümü ekleyin.", 10),
    Rule("DOC006", "README'de 'Ekran görüntüsü / demo' bölümü eksik", "low", "documentation",
         "Görsel içerik, projenin 10 saniyede anlaşılmasını sağlar; portföyde en çok dikkat çeken kısımdır.",
         "Bir ekran görüntüsü veya kısa bir GIF ekleyin (`docs/screenshot.png`).", 15),
    Rule("DOC007", "README'de 'Kullanılan teknolojiler' bölümü eksik", "low", "documentation",
         "Kullanılan teknolojiler listelenmemiş; okuyan kişi projenin teknik kapsamını hemen göremez.",
         "'Kullanılan teknolojiler' başlığı altında dil, framework ve önemli kütüphaneleri listeleyin.", 5),
    Rule("DOC008", "Lisans dosyası yok", "low", "documentation",
         "Lisans olmadan, kodu başkalarının hangi koşullarda kullanabileceği belirsizdir; açık kaynak projelerde standart beklentidir.",
         "GitHub'da 'Add file → Create new file → LICENSE' ile MIT gibi bir lisans şablonu ekleyin.", 5),
    Rule("DOC009", "Ortam değişkenleri belgelenmemiş (.env.example yok)", "medium", "runnable",
         "Kod ortam değişkenleri okuyor fakat hangi değişkenlerin gerektiği bir yerde listelenmemiş. Proje başka bir bilgisayarda büyük ihtimalle ilk denemede çalışmaz.",
         "Gerçek değerler olmadan bir `.env.example` dosyası ekleyin (örn. `API_KEY=`) ve README'de nasıl doldurulacağını anlatın.", 10),
    Rule("DOC011", "README'deki {count} komut bu projede çalışmaz", "medium", "documentation",
         "README'yi izleyen kişi bu adımlarda hata alır: {commands}. Kurulum talimatı çalışmayan bir proje, ilk izlenimde "
         "\"bakımsız\" görünür.",
         "Komutları projenin bugünkü dosya ve modül adlarına göre güncelleyin; her değişiklikten sonra README'deki adımları "
         "temiz bir klonda bir kez deneyin.", 15),
    Rule("DOC010", "Docstring kapsamı düşük (%{percent})", "low", "quality",
         "{total} public fonksiyon/sınıfın yalnızca {documented} tanesinde açıklama (docstring) var. Kodu okuyan kişi fonksiyonların amacını tahmin etmek zorunda kalıyor.",
         "Önce dışarıdan çağrılan ana fonksiyonlara bir satırlık docstring ekleyin: ne yapar, ne döndürür.", 60),

    # --- Testing --------------------------------------------------------------------------
    Rule("TST001", "Test dosyası bulunamadı", "high", "testing",
         "Otomatik test olmadan, yapılan her değişiklikte projenin hâlâ çalıştığından emin olmanın yolu elle denemektir. Testler ayrıca işe alımda 'profesyonel çalışma alışkanlığı' sinyali verir.",
         "`tests/` klasörü oluşturun, `pip install pytest` ile pytest kurun ve en kritik 3-5 fonksiyon için `test_*.py` dosyalarında basit testler yazın. `pytest` komutuyla çalıştırın.", 120),
    Rule("TST002", "Test sayısı çok az ({count} test)", "medium", "testing",
         "Test altyapısı var fakat kapsam çok dar; hataların büyük kısmı yakalanmaz.",
         "Her ana modül için en az bir 'mutlu yol' ve bir 'hatalı girdi' testi ekleyin.", 90),
    Rule("TST003", "Test kapsamı kaynak koda göre düşük", "low", "testing",
         "{functions} public fonksiyona karşılık {tests} test var (oran {ratio}).",
         "`pytest --cov` ile hangi modüllerin test edilmediğini görün ve en riskli modüllerden başlayın.", 180),
    Rule("TST004", "Testler CI'da otomatik çalışmıyor", "low", "testing",
         "Testler yalnızca elle çalıştırıldığında unutulur. GitHub Actions ile her push'ta otomatik çalışmaları ücretsizdir (public depolar için).",
         "`.github/workflows/tests.yml` ekleyin: Python kurulumu, `pip install -r requirements.txt`, `pytest`.", 20),

    Rule("TST005", "Testlerin hiç ulaşmadığı {count} public fonksiyon (statik kapsam %{percent})", "low", "testing",
         "Çağrı grafiğinde testlerden başlayan hiçbir yol bu fonksiyonlara varmıyor: {names}. Bunlardaki bir hata testlerle yakalanamaz. "
         "Bu oran kodu çalıştırmadan hesaplanan bir tahmindir; gerçek satır kapsamı için `pytest --cov` kullanın.",
         "En çok kullanılan ve en karmaşık olanlardan başlayarak bu fonksiyonlar için test yazın.", 30),

    # --- Organization / runnable ----------------------------------------------------------
    Rule("ORG001", "Bağımlılık dosyası yok (requirements.txt / pyproject.toml)", "high", "runnable",
         "Projeyi çalıştırmak için hangi paketlerin kurulması gerektiği belirtilmemiş. Başka biri (veya 6 ay sonraki siz) projeyi çalıştıramaz.",
         "Sanal ortamda `pip freeze > requirements.txt` çalıştırın, sonra listeyi yalnızca doğrudan kullandığınız paketlere indirin.", 10),
    Rule("ORG002", "{count} bağımlılığın sürümü sabitlenmemiş", "low", "runnable",
         "Sürüm belirtilmeyen paketler her kurulumda en son sürümle gelir; yeni bir sürüm projeyi habersizce bozabilir.",
         "Çalıştığını bildiğiniz sürümleri yazın, örn. `streamlit>=1.40,<2` veya `pip freeze` çıktısındaki `==` sürümleri.", 10),
    Rule("ORG003", "Belirgin bir giriş noktası (main.py / app.py) yok", "medium", "runnable",
         "Projenin hangi dosyadan başlatılacağı belli değil; okuyan kişi doğru dosyayı tahmin etmek zorunda.",
         "Başlangıç dosyasını `main.py` veya `app.py` olarak adlandırın ve `if __name__ == \"__main__\":` bloğu ekleyin; README'de çalıştırma komutunu yazın.", 15),
    Rule("ORG004", "Tüm Python dosyaları kök dizinde", "low", "organization",
         "{count} kaynak dosya tek seviyede duruyor; projenin hangi parçalardan oluştuğu klasör yapısından anlaşılmıyor.",
         "Dosyaları sorumluluklarına göre paketlere ayırın (örn. `app/`, `services/`, `utils/`) ve testleri `tests/` klasörüne taşıyın.", 45),
    Rule("ORG005", "Docker desteği yok", "info", "runnable",
         "Dockerfile, uygulamanın her bilgisayarda aynı şekilde çalışmasını sağlar ve deploy'u kolaylaştırır.",
         "`python:3.12-slim` tabanlı basit bir Dockerfile ekleyin; `pip install -r requirements.txt` ve başlatma komutunu yazın.", 60),
    Rule("ORG006", "Desteklenen Python sürümü belirtilmemiş", "info", "runnable",
         "Hangi Python sürümüyle çalıştığı bilinmeyen projeler, eski veya çok yeni sürümlerde beklenmedik hatalar verebilir.",
         "README'ye 'Python 3.10+' gibi bir not ekleyin veya `pyproject.toml` içinde `requires-python` / kökte `.python-version` dosyası kullanın.", 5),
    Rule("ORG008", "Döngüsel import: {cycle}", "medium", "organization",
         "Bu modüller birbirini içe aktarıyor. Python ilk import'ta modülü yarım yüklenmiş hâliyle kullanır; sıra değişince "
         "`ImportError` ya da `AttributeError` verir. Modüller ayrıca birbirinden bağımsız test edilemez ve değiştirilemez.",
         "Ortak kullanılan parçayı üçüncü bir modüle taşıyın, bağımlılığı tek yöne çevirin (ör. `models` hiçbir şeyi import etmesin) "
         "ya da son çare olarak import'u kullanıldığı fonksiyonun içine alın.", 45),
    Rule("ORG007", "Proje yalnızca Jupyter Notebook'lardan oluşuyor", "info", "organization",
         "Notebook içerikleri bu sürümde kod kalitesi analizine dahil edilmiyor. Ayrıca yeniden kullanılabilir kod notebook'larda saklı kalır.",
         "Tekrar kullanılan fonksiyonları `.py` modüllerine taşıyıp notebook'tan import edin.", 60),

    # --- Security: secrets & configuration -------------------------------------------------
    Rule("SEC001", "Kaynak kodda {label} bulundu", "critical", "security",
         "Bilinen bir anahtar formatıyla eşleşen değer kod deposunda duruyor. GitHub'a gönderilen anahtarlar botlar tarafından dakikalar içinde taranıp kötüye kullanılabilir." + POTENTIAL_NOTE,
         "1) Anahtarı sağlayıcının panelinden hemen iptal edip yenileyin (rotate). 2) Değeri `.env` dosyasına taşıyıp `os.getenv()` ile okuyun. 3) `.env`'i `.gitignore`'a ekleyin. 4) Git geçmişinden de temizleyin (git filter-repo / BFG).", 20),
    Rule("SEC002", "Kod içinde sabit (hardcoded) parola / API anahtarı olabilir", "high", "security",
         "{count} yerde KEY/TOKEN/SECRET/PASSWORD isimli bir değişkene doğrudan metin atanmış. Bu değerler depo ile birlikte herkese açık hâle gelir." + POTENTIAL_NOTE,
         "Değerleri `.env` dosyasına taşıyın, `python-dotenv` ile yükleyip `os.getenv('API_KEY')` şeklinde okuyun; depoya yalnızca boş bir `.env.example` koyun.", 10),
    Rule("SEC007", "{count} yerde anahtara benzeyen rastgele metin", "medium", "security",
         "Değişken adı bir sır olduğunu söylemiyor ama değer istatistiksel olarak rastgele görünüyor (Shannon entropisi yüksek): "
         "{examples}. API anahtarları ve token'lar çoğu zaman böyle görünür." + POTENTIAL_NOTE,
         "Değer bir anahtar veya token ise `.env` dosyasına taşıyıp `os.getenv()` ile okuyun ve sağlayıcıdan yenileyin; "
         "değilse (ör. sabit bir kimlik) adını `..._id` gibi anlamını belirten bir şekilde koyun.", 15),
    Rule("SEC003", "ZIP içinde dolu bir {name} dosyası var", "low", "security",
         ".gitignore bu dosyayı kapsıyor, yani GitHub'a gönderilmiyor. Ancak ZIP'i başkalarıyla paylaşırsanız içindeki gerçek anahtarlar da paylaşılır.",
         "Projeyi ZIP olarak paylaşmadan önce `.env` dosyasını arşivden çıkarın. (İçeriği bu analizde yapay zekâya gönderilmedi.)", 2),
    Rule("SEC004", "Gizli bilgiler içeren {name} dosyası depoda", "critical", "security",
         "Ortam değişkeni dosyası değerleriyle birlikte depoya eklenmiş. İçindeki parola ve API anahtarları depoyu görebilen herkes tarafından okunabilir." + POTENTIAL_NOTE,
         "Dosyayı depodan kaldırın (`git rm --cached .env`), `.gitignore`'a `.env` satırını ekleyin, içindeki tüm anahtarları yenileyin ve yerine değersiz bir `.env.example` koyun.", 15),
    Rule("SEC005", ".gitignore dosyası yok", "medium", "organization",
         "`.gitignore` olmadan sanal ortam klasörleri, `__pycache__`, `.env` gibi gizli veya gereksiz dosyalar kolayca depoya eklenir.",
         "GitHub'ın hazır Python `.gitignore` şablonunu kök dizine ekleyin ve içinde `.env` satırı olduğundan emin olun.", 5),
    Rule("SEC006", ".gitignore, .env dosyasını kapsamıyor", "high", "security",
         "Proje ortam değişkenleri kullanıyor fakat `.gitignore` içinde `.env` yok. İlk `git add .` komutunda gizli anahtarlar depoya girebilir.",
         "`.gitignore` dosyasına `.env` satırını ekleyin.", 2),

    # --- Security: vulnerable dependencies (OSV.dev) -----------------------------------------
    Rule("DEP001", "`{name}=={version}` sürümünde {count} bilinen güvenlik açığı", "high", "security",
         "OSV.dev veritabanına göre kullandığınız sürüm yayımlanmış açıklar içeriyor: {advisories}. Bu açıklar herkese açık "
         "olduğu için saldırganlar tarafından kolayca hedeflenebilir.",
         "`{name}` paketini en az `{fix}` sürümüne yükseltin (`pip install -U \"{name}>={fix}\"`), sabitlediğiniz dosyayı "
         "güncelleyin ve testlerinizi çalıştırın.", 15),

    # --- Security: confirmed data flows (taint analysis) ---------------------------------------
    Rule("TNT001", "Kullanıcı girdisi `eval`/`exec`'e ulaşıyor (kod enjeksiyonu)", "critical", "security",
         "Veri akışı analizi bu girdinin hiçbir temizleme yapılmadan kod olarak çalıştırıldığını gösteriyor: {flow}. "
         "Saldırgan sunucuda istediği Python kodunu çalıştırabilir.",
         "`eval`/`exec` kullanmayın. Sayısal ifade için `ast.literal_eval`, hesaplama için güvenli bir ifade ayrıştırıcı, "
         "seçim için izin verilen değerlerden oluşan bir sözlük kullanın.", 30),
    Rule("TNT002", "Kullanıcı girdisi kabuk komutuna ulaşıyor (komut enjeksiyonu)", "critical", "security",
         "Veri akışı: {flow}. Girdiye `; rm -rf /` gibi bir ek yapılırsa sunucuda komut çalışır.",
         "`subprocess.run([...], shell=False)` ile argümanları liste olarak verin; girdiyi izin listesine göre doğrulayın, "
         "gerekirse `shlex.quote()` kullanın.", 30),
    Rule("TNT003", "Kullanıcı girdisi SQL sorgusuna gömülüyor (SQL enjeksiyonu)", "critical", "security",
         "Veri akışı: {flow}. `' OR '1'='1` gibi bir girdi tüm tabloyu okuyabilir veya silebilir.",
         "Parametreli sorgu kullanın: `cursor.execute('... WHERE ad = ?', (ad,))`. ORM kullanıyorsanız filtre metotlarını tercih edin.", 25),
    Rule("TNT004", "Kullanıcı girdisi dosya yolunu belirliyor (dizin aşımı)", "high", "security",
         "Veri akışı: {flow}. `../../etc/passwd` gibi bir girdiyle izin verilmeyen dosyalar okunabilir veya silinebilir.",
         "Dosya adını `os.path.basename` / `werkzeug.utils.secure_filename` ile temizleyin, `Path.resolve()` sonrası "
         "beklenen klasörün içinde kaldığını kontrol edin veya Flask'ta `send_from_directory` kullanın.", 30),
    Rule("TNT005", "Kullanıcı girdisi güvensiz biçimde nesneye dönüştürülüyor", "critical", "security",
         "Veri akışı: {flow}. `pickle`/`yaml.load` yüklerken nesne kodu çalıştırır; dışarıdan gelen veriyle bu doğrudan kod çalıştırmadır.",
         "Dış veri için JSON kullanın; YAML için `yaml.safe_load`. Pickle'ı yalnızca kendi ürettiğiniz ve imzaladığınız veriyle kullanın.", 45),
    Rule("TNT006", "Kullanıcı girdisi şablon olarak işleniyor (SSTI)", "critical", "security",
         "Veri akışı: {flow}. Jinja şablonu olarak işlenen girdi `{{{{ config }}}}` gibi ifadelerle sunucu bilgilerini sızdırabilir, kod çalıştırabilir.",
         "Girdiyi şablona metin olarak verin: `render_template('sayfa.html', ad=ad)`; `render_template_string` ile birleştirmeyin.", 20),
    Rule("TNT007", "Kullanıcı girdisi istek atılan adresi belirliyor (SSRF)", "high", "security",
         "Veri akışı: {flow}. Sunucu, saldırganın seçtiği adrese (ör. iç ağ, bulut meta veri servisi) istek atabilir.",
         "Adresin alan adını izin listesiyle doğrulayın; mümkünse yalnızca yol kısmını kullanıcıdan alın.", 30),
    Rule("TNT008", "Kullanıcı girdisi yönlendirme adresini belirliyor (açık yönlendirme)", "medium", "security",
         "Veri akışı: {flow}. Güvenilir sitenizin bağlantısı, kullanıcıyı oltalama sitesine yönlendirmek için kullanılabilir.",
         "Yalnızca uygulama içi göreli yollara (`/` ile başlayan, `//` ile başlamayan) veya izin listesindeki adreslere yönlendirin.", 15),
    Rule("TNT009", "Kullanıcı girdisi kaçışsız HTML olarak gösteriliyor (XSS)", "medium", "security",
         "Veri akışı: {flow}. Girdideki `<script>` etiketi diğer kullanıcıların tarayıcısında çalışabilir.",
         "HTML'i kaçışlayın (`html.escape`) ya da `unsafe_allow_html` / `Markup` / `mark_safe` kullanmadan metin olarak gösterin.", 15),

    # --- Security: dangerous calls (AST) ---------------------------------------------------
    Rule("SEC010", "`eval()` / `exec()` kullanımı", "high", "security",
         "`eval`/`exec` verilen metni Python kodu olarak çalıştırır. Kullanıcı girdisi buraya ulaşırsa saldırgan sunucuda istediği kodu çalıştırabilir." + POTENTIAL_NOTE,
         "Matematiksel ifade veya veri ayrıştırmak için `ast.literal_eval`, `json.loads` ya da açık bir eşleme (dict) kullanın.", 20),
    Rule("SEC011", "Güvenilmeyen veriyle `pickle` / `marshal` yükleme", "medium", "security",
         "`pickle.load(s)` yüklerken nesne oluşturma kodunu çalıştırır; dışarıdan gelen bir pickle dosyası kod çalıştırma riskidir." + POTENTIAL_NOTE,
         "Dışarıdan gelen veri için JSON gibi veri-tabanlı formatlar kullanın; pickle'ı yalnızca kendi ürettiğiniz dosyalarda kullanın.", 30),
    Rule("SEC012", "`yaml.load()` güvenli yükleyici olmadan çağrılmış", "medium", "security",
         "`yaml.load` varsayılan/tam yükleyiciyle Python nesneleri oluşturabilir." + POTENTIAL_NOTE,
         "`yaml.safe_load()` kullanın veya `Loader=yaml.SafeLoader` verin.", 5),
    Rule("SEC013", "Kabuk (shell) üzerinden komut çalıştırma", "high", "security",
         "`shell=True`, `os.system` veya `os.popen` komutu kabukta çalıştırır; komuta karışan kullanıcı girdisi komut enjeksiyonuna yol açabilir." + POTENTIAL_NOTE,
         "`subprocess.run([...], shell=False)` ile argümanları liste olarak verin; kullanıcı girdisini komut metnine eklemeyin.", 15),
    Rule("SEC014", "SQL sorgusu metin birleştirmeyle oluşturulmuş", "high", "security",
         "f-string, `%` veya `+` ile oluşturulan SQL sorguları, girdiye göre SQL enjeksiyonuna açıktır." + POTENTIAL_NOTE,
         "Parametreli sorgu kullanın: `cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))`.", 20),
    Rule("SEC015", "TLS sertifika doğrulaması kapatılmış (`verify=False`)", "medium", "security",
         "Sertifika doğrulaması kapalıyken trafik araya girme (man-in-the-middle) saldırılarına açıktır." + POTENTIAL_NOTE,
         "`verify=False` parametresini kaldırın; özel sertifika gerekiyorsa `verify='/yol/ca.pem'` verin.", 5),
    Rule("SEC016", "Hata ayıklama (debug) modu açık bırakılmış", "medium", "security",
         "Flask/Django debug modu üretimde hata ayrıntılarını ve hatta etkileşimli konsolu dışarı açabilir." + POTENTIAL_NOTE,
         "Debug ayarını ortam değişkeninden okuyun: `debug=os.getenv('DEBUG') == '1'`.", 5),
    Rule("SEC017", "Zayıf hash algoritması (MD5 / SHA1)", "low", "security",
         "MD5 ve SHA1 çakışmalara karşı güvenli değildir; parola veya imza için kullanılmamalıdır." + POTENTIAL_NOTE,
         "Parolalar için `bcrypt`/`argon2`, genel amaçlı hash için `hashlib.sha256` kullanın.", 10),

    # --- Code quality ------------------------------------------------------------------------
    Rule("QLT001", "`{name}()` çok karmaşık (bilişsel {cognitive} · döngüsel {complexity})", "medium", "quality",
         "Bilişsel karmaşıklık {cognitive}: okurken akılda tutulması gereken iç içe yapı yükü (15 üstü zor kabul edilir). "
         "Döngüsel karmaşıklık {complexity}: test edilmesi gereken bağımsız yol sayısı (11 üstü yüksek). Bu fonksiyonu "
         "değiştirmek ve test etmek zor; hata saklamaya müsait.",
         "İç içe if/for bloklarını ayrı, isimli yardımcı fonksiyonlara bölün; erken `return` (guard clause) ile iç içeliği azaltın.", 45),
    Rule("QLT011", "{count} fonksiyon daha yüksek karmaşıklıkta", "low", "quality",
         "Bilişsel karmaşıklığı 15 veya döngüsel karmaşıklığı 11 ve üzeri olan başka fonksiyonlar da var.",
         "Önce en çok değişen veya hata veren fonksiyonlardan başlayarak sadeleştirin.", 60),
    Rule("QLT002", "`{name}()` çok uzun ({length} satır)", "low", "quality",
         "{limit} satırı aşan fonksiyonlar genellikle birden fazla iş yapar; okunması, test edilmesi ve yeniden kullanılması zorlaşır.",
         "Fonksiyonun yaptığı adımları (örn. veri okuma → işleme → kaydetme) ayrı fonksiyonlara çıkarın.", 30),
    Rule("QLT003", "{count} fonksiyon çok fazla parametre alıyor", "low", "quality",
         "{limit}'dan fazla parametre, fonksiyonun çok fazla sorumluluk taşıdığına işaret eder ve çağrıları hataya açık hâle getirir.",
         "İlişkili parametreleri bir `dataclass` veya ayar nesnesinde toplayın.", 30),
    Rule("QLT004", "`{path}` çok büyük ({lines} satır)", "medium", "organization",
         "Tek dosyada çok fazla kod, birden fazla sorumluluğun bir araya toplandığını gösterir ve gezinmeyi zorlaştırır.",
         "Dosyayı sorumluluklara göre modüllere ayırın (örn. `services/`, `utils/`, `ui/`).", 120),
    Rule("QLT005", "`{path}` bakımı zor (Maintainability Index {mi})", "medium", "quality",
         "Radon Maintainability Index; satır sayısı, karmaşıklık ve Halstead hacminden hesaplanır. 10'un altı bu ölçekte 'bakımı zor' (C) sınıfıdır.",
         "Dosyadaki en karmaşık fonksiyonları bölerek ve tekrar eden kodu ortak fonksiyonlara çıkararak başlayın.", 120),
    Rule("QLT006", "{count} dosya Python olarak ayrıştırılamadı", "high", "quality",
         "Bu dosyalarda sözdizimi hatası var (veya Python 2 sözdizimi kullanılıyor). Çalıştırıldıklarında hata verirler ve analiz dışında kaldılar.",
         "Hata mesajındaki satırı düzeltin; Python 2 kodu ise `print x` → `print(x)` gibi Python 3 sözdizimine geçirin.", 15),
    Rule("QLT007", "{count} adet çıplak `except:` bloğu", "low", "quality",
         "`except:` her hatayı (Ctrl+C dahil) yakalar ve hataları sessizce yutarak hata ayıklamayı çok zorlaştırır.",
         "Beklediğiniz hata türünü yakalayın (`except ValueError:`) ve hatayı en azından loglayın.", 5),
    Rule("QLT008", "{count} yerde `global` değişken kullanımı", "low", "quality",
         "Global durum, fonksiyonların davranışını görünmez biçimde birbirine bağlar; test etmeyi ve hata bulmayı zorlaştırır.",
         "Durumu fonksiyon parametresi/dönüş değeri olarak taşıyın veya bir sınıf içinde toplayın.", 45),
    Rule("QLT009", "{count} tekrarlanan kod bloğu (~{lines} satır)", "low", "quality",
         "Kopyala-yapıştır kod, bir hatanın birden çok yerde düzeltilmesini gerektirir; biri unutulduğunda tutarsızlık oluşur.",
         "Tekrarlanan bloğu parametre alan tek bir fonksiyona çıkarın ve her yerden onu çağırın.", 20),
    Rule("QLT013", "{count} fonksiyon yapısal olarak aynı (yalnızca isimler / değerler farklı)", "low", "quality",
         "Bu fonksiyonların sözdizimi ağacı, değişken adları ve sabit değerler dışında birebir aynı: {members}. "
         "Değişkenleri yeniden adlandırılmış kopyalar metin karşılaştırmasıyla bulunamaz; bir hata birinde düzeltilip diğerinde unutulur.",
         "Ortak mantığı tek bir fonksiyona çıkarın; farklılaşan değerleri parametre olarak verin.", 30),
    Rule("QLT014", "Erişilemeyen kod ({count} yer)", "medium", "quality",
         "Kontrol akış grafiğine göre bu satırlara hiçbir yoldan ulaşılamıyor; `return`, `raise`, `break`, `continue`, "
         "`sys.exit()` ya da hep aynı sonucu veren bir koşuldan sonra geliyorlar: {detail}. Çoğu zaman unutulmuş bir mantık "
         "hatasıdır: çalıştığı sanılan kod aslında hiç çalışmaz.",
         "Kodun çalışması gerekiyorsa akışı düzeltin (örneğin erken `return`'ü koşula bağlayın); gerekmiyorsa silin.", 10),
    Rule("QLT015", "Kapatılmayan dosya / bağlantı ({count} yer)", "medium", "quality",
         "`with` olmadan açılan kaynak en az bir yolda (erken `return` ve `except` yolları dahil) kapatılmıyor: {detail}. "
         "Açık kalan dosya tanıtıcıları ve veritabanı bağlantıları uzun çalışan uygulamalarda tükenir, yazılan veri diske "
         "aktarılmayabilir. sqlite3'te `with conn:` bağlantıyı kapatmaz, yalnızca işlemi commit eder.",
         "`with open(...) as f:` kullanın; bağlantılar için `with contextlib.closing(sqlite3.connect(...)) as conn:`. "
         "`with` her yolda, hata olsa bile kapatır.", 15),
    Rule("DEAD001", "{count} kullanılmayan fonksiyon / sınıf", "low", "quality",
         "Çağrı grafiğine göre hiçbir giriş noktasından (modül kodu, route'lar, testler, betikler) ulaşılamıyor: {names}. "
         "Kullanılmayan kod okuyanı yanıltır, bakım yükü getirir ve testlerde gereksiz yere yer kaplar.",
         "Silmeden önce dinamik bir kullanım (string ile çağrı, eklenti kaydı, `getattr`) olmadığını kontrol edin; "
         "yoksa silin. Git geçmişi zaten saklar.", 10),
    # --- Data science -------------------------------------------------------------------------
    Rule("LEAK001", "Veri sızıntısı: ön işleme, veri bölünmeden önce tüm veriye uygulanıyor", "high", "quality",
         "Ölçekleyici/kodlayıcı gibi istatistik öğrenen bir adım tüm veriye `fit` edilmiş ve aynı veri sonra eğitim/test olarak "
         "bölünmüş: {detail}. Test verisinin ortalaması, varyansı veya kategorileri eğitime sızar; ölçülen başarı gerçek başarıdan "
         "yüksek çıkar ve model gerçek veride hayal kırıklığı yaratır.",
         "Önce böl, sonra `fit` et: `X_train = scaler.fit_transform(X_train)`, `X_test = scaler.transform(X_test)`. Çapraz doğrulamada "
         "adımları `make_pipeline(StandardScaler(), model)` içine alın; böylece her katmanda yalnızca eğitim kısmı öğrenilir.", 30),
    Rule("LEAK002", "Veri sızıntısı: test verisine `fit` uygulanıyor", "high", "quality",
         "Test verisi yalnızca değerlendirme içindir; ona `fit` edilen her şey test verisini görmüş olur: {detail}.",
         "Test verisinde yalnızca `transform` / `predict` kullanın; ölçekleyiciyi ve modeli eğitim verisine `fit` edin.", 15),
    Rule("PD001", "`iterrows()` ile satır satır döngü ({count} yer)", "low", "quality",
         "`iterrows()` her satır için yeni bir Series oluşturur; vektörel işlemlerden yüzlerce kat yavaştır ve veri tiplerini bozar: {detail}.",
         "Sütun işlemleri kullanın (`df['c'] = df['a'] * df['b']`), koşullar için `np.where` / `df.loc[mask, 'c'] = …`; "
         "döngü şartsa `itertuples()` kullanın.", 30),
    Rule("PD002", "Satır bazlı `apply(axis=1)` ({count} yer)", "low", "quality",
         "`apply(axis=1)` arka planda Python döngüsüdür: {detail}. Büyük verilerde vektörel karşılığından çok yavaştır.",
         "Fonksiyonu sütun işlemleriyle yeniden yazın; ayrık durumlar için `np.select` kullanın.", 30),
    Rule("PD003", "Zincirli indeksleme ile atama ({count} yer)", "medium", "quality",
         "`df['a'][maske] = değer` gibi zincirli atamalar çoğu zaman bir kopyayı değiştirir; asıl DataFrame **sessizce değişmez** "
         "(SettingWithCopyWarning): {detail}.",
         "Tek adımda atayın: `df.loc[maske, 'a'] = değer`.", 10),
    Rule("PD004", "`DataFrame.append` kullanımı ({count} yer)", "high", "quality",
         "`DataFrame.append` pandas 2.0'da kaldırıldı; bu satırlar güncel pandas ile `AttributeError` verir: {detail}.",
         "Satırları bir listede toplayıp sonda tek seferde `pd.concat(parcalar, ignore_index=True)` yapın.", 20),
    Rule("PD005", "Döngü içinde `pd.concat` ile büyütme ({count} yer)", "low", "quality",
         "Her turda tüm DataFrame yeniden kopyalanır; süre satır sayısının karesiyle büyür: {detail}.",
         "Parçaları listeye ekleyin, döngüden sonra tek bir `pd.concat` çağırın.", 20),
    Rule("PD006", "`range(len(df))` ile satır döngüsü ({count} yer)", "low", "quality",
         "Satırlara `iloc`/`loc` ile tek tek erişmek pandas'ın vektörel gücünü kullanmaz: {detail}.",
         "İşlemi sütunlar üzerinde yapın; gerekiyorsa `itertuples()` ile gezin.", 30),
    Rule("QLT010", "{count} adet TODO/FIXME notu", "info", "quality",
         "Çok sayıda açık not, yarım kalmış işlere işaret eder.",
         "Notları GitHub Issues'a taşıyın ve koddan temizleyin.", 20),
]

RULES: dict[str, Rule] = {rule.id: rule for rule in _RULES}

# Short names for per-location findings shown in tables (the rule titles carry counts).
SHORT_LABELS = {
    "QLT014": "Erişilemeyen kod", "QLT015": "Kapatılmayan kaynak",
    "LEAK001": "Veri sızıntısı: bölmeden önce fit", "LEAK002": "Veri sızıntısı: test verisine fit",
    "PD001": "iterrows() döngüsü", "PD002": "apply(axis=1)", "PD003": "Zincirli indeksle atama",
    "PD004": "DataFrame.append", "PD005": "Döngüde pd.concat", "PD006": "range(len(df)) döngüsü",
}


def make_issue(
    rule_id: str,
    locations: list[Location] | None = None,
    values: dict | None = None,
    **overrides,
) -> Issue:
    """Build an Issue from the catalogue; `overrides` replace any Issue field."""
    rule = RULES[rule_id]
    values = values or {}
    fields = {
        "rule_id": rule.id,
        "title": rule.title.format(**values),
        "severity": rule.severity,
        "category": rule.category,
        "explanation": rule.explanation.format(**values),
        "recommendation": rule.recommendation.format(**values),
        "effort_minutes": rule.effort,
        "locations": locations or [],
    }
    fields.update(overrides)
    return Issue(**fields)
