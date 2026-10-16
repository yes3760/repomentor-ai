# Değişiklik günlüğü

Bu projedeki önemli değişiklikler burada tutulur. Biçim [Keep a Changelog](https://keepachangelog.com/tr-TR/1.1.0/) önerisini, sürüm numaraları [Semantic Versioning](https://semver.org/lang/tr/) kurallarını izler.

## [Yayınlanmamış]

### Eklendi

- **Jupyter Notebook desteği** (`notebooks.py`): kod hücreleri sırasıyla tek bir sanal betiğe dizilip bütün analizlerden geçer; hücreler arası veri sızıntısı ve veri akışı yakalanır, notebook'lara yazılmış anahtarlar taranır, bulgular "hücre N, satır M" olarak gösterilir. IPython komutları satır kaydırmadan nötrlenir; başka dile geçen ve ayrıştırılamayan hücreler atlanıp raporlanır. Yeni `churn-notebook` örnek projesi.
- **Pull request özeti** (`pr_report.py`): `--baseline` ile iki sürüm karşılaştırılır; `--format pr` skor farkını, kategori puanlarını, yeni ve giderilen bulguları kısa bir Markdown'da verir. `--max-drop` skor düşüşü için kalite kapısıdır. GitHub Actions içinde skor ve fark adım çıktısına yazılır.
- Pull request şablonu (`.github/pull_request_template.md`): test adımları ve kontrol listesi.
- **Etkileşimli kod haritası** (`code_map.py`): klasör → dosya treemap'i; alan satır sayısı, renk risk / bilişsel yük / bulgular. Dosya başına risk artık bütün dosyalar için hesaplanıyor (`file_risks`); "önce bu dosyalara bakın" listesi de aynı hesabı kullanıyor.
- **Saldırı yolu diyagramı**: her doğrulanmış veri akışı kaynak → değişkenler → tehlikeli çağrı grafiği olarak çiziliyor.
- **README rozeti** (`badge.py`): shields.io bağlantısı ve indirilebilir SVG; Portföy sekmesinde.
- Şeffaf arka planlı yeni logolar: koyu zeminler için açık yazılı (`assets/repomentor-logo.png`), açık zeminler için koyu yazılı (`assets/repomentor-logo-light.png`); README GitHub temasına göre doğru olanı gösterir.
- **Doğrulanmış güvenlik düzeltmeleri** (`security_fixes.py`): doğrulanmış SQL enjeksiyonu akışları parametreli sorguya (`?` / `%s`, sürücüye göre), komut enjeksiyonu akışları kabuksuz argüman listesine (`subprocess.run([...])`) çevrilip düzeltme yamasına eklenir. Her düzeltme uygulandıktan sonra veri akışı analizi yeniden çalıştırılır; akış kapanmıyorsa düzeltme atılır. Güvenlik sekmesinde saldırı yolunun altında, PR yorumunda 🔧 işaretiyle gösterilir.
- **GitHub Action** (`action.yml`): pull request'lerde temel dalla karşılaştırıp tek bir yorumu günceller, raporu iş özetine ekler, `min-score` / `max-drop` kapılarını uygular. Bu depo kendi PR'larında kullanır.

### Düzeltildi

- Yapay zekâ ayarları: Ollama'yı başlattıktan ya da model indirdikten sonra liste 5 dakika boyunca güncellenmiyordu; Ollama artık her seferinde canlı sorgulanır ve "Yeniden dene" düğmesi var.
- Sağlayıcı adları dar kenar çubuğunda kesiliyordu; adlar kısaltıldı, açıklamalar altta gösteriliyor. Açma anahtarıyla aynı işi yapan "Kapalı" seçeneği kaldırıldı.
- "`ollama pull` ile model indirin" uyarısı artık yalnızca model yoksa ya da seçili model küçükse gösteriliyor. Anahtar alanı ham ortam değişkeni adı yerine "API anahtarı" olarak görünüyor; hatalı anahtarda uyarı veriliyor.
- Yüzdeler eksik bir şey kaldığında %100'e (ya da %0'a) yuvarlanıyordu (ör. "2 fonksiyona test ulaşmıyor, statik kapsam %100"); artık "%99,7" gibi gösteriliyor.
- Notebook projelerine "main.py / app.py giriş noktası yok" önerisi artık verilmiyor; notebook kendi giriş noktasıdır.
- Örnek projelerde analiz ilerlemesi dar düğme sütunu yerine satırın altında tam genişlikte gösteriliyor; yapay zekâ adımının token sayacı artık görünüyor.

## [1.2.0] - 2026-10-16

### Eklendi

- **Çağrı grafiği** (`call_graph.py`, `usage_analyzer.py`): hiçbir giriş noktasından ulaşılmayan fonksiyon ve sınıflar (`DEAD001`) ile hiçbir testin çağırmadığı fonksiyonlar (`TST005`). Test skoru artık test/fonksiyon oranı yerine testlerin çağrı grafiğinde ulaştığı fonksiyon oranını kullanır.
- **Kontrol akış grafiği** (`cfg.py`): erişilemeyen kod (`QLT014`) ve erken `return` ya da `except` yolunda kapatılmayan dosya, veritabanı bağlantısı, soket ve arşivler (`QLT015`). `def db(): return sqlite3.connect(...)` gibi proje içi kaynak fabrikaları da izlenir.
- **Veri bilimi kontrolleri** (`ml_analyzer.py`): veri bölünmeden önce `fit` (`LEAK001`), test verisine `fit` (`LEAK002`) ve pandas anti-pattern'leri (`PD001`–`PD006`). Yeni `churn-model` örnek projesi.
- **README komut doğrulayıcı** (`readme_commands.py`, `DOC011`): README'deki komutların projede çalışıp çalışmayacağı, hiçbir komut çalıştırılmadan kontrol edilir.
- **Entropi ile anahtar tespiti** (`entropy.py`, `SEC007`): adı "key" ya da "token" olmayan rastgele anahtarlar.
- **Otomatik düzeltme yaması** (`autofix.py`): `yaml.safe_load`, çıplak `except`, `.gitignore`, `.env.example` ve Ruff'ın güvenli düzeltmeleri. Arayüzde indirilebilir `.patch`, komut satırında `--fix-patch`. Proje dosyalarına hiçbir zaman yazılmaz.
- Arayüz ve Markdown raporuna yeni bölümler: kullanılmayan kod, kontrol akışı, veri bilimi, statik test erişimi, README komutları, düzeltme yaması.
- `CONTRIBUTING.md`, `SECURITY.md` ve bu dosya.

### Değişti

- Veri akışı analizi koruma koşullarını tanır: `isdigit`, `isalnum`, `re.fullmatch`, `is_relative_to` veya sabit bir listeye üyelik kontrolünden sonra değişken temiz sayılır. `startswith` yetersiz bir kontrol olduğu için bilinçli olarak sayılmaz.
- Yapay zekâ bağlamına yeni analizlerin sonuçları eklendi (yalnızca etiketler; kaynak kod satırı gönderilmez).
- JSON raporu düzeltme yamasının diff gövdesini içermez; yama ayrı indirilir.

## [1.1.0] - 2026-10-15

### Eklendi

- **Bağımlılık açığı taraması (OSV.dev):** sürümü kesin paketler ve kilit dosyaları (`poetry.lock`, `uv.lock`, `Pipfile.lock`, `pdm.lock`), CVSS v3 puanı, tüm açıkları kapatan en küçük güvenli sürüm. `--no-osv` ve yan menü ayarıyla kapatılabilir.
- **Veri akışı (taint) analizi:** kullanıcı girdisinin 9 tehlikeli hedef türüne ulaşması, fonksiyon özetleriyle fonksiyonlar ve modüller arası.
- Bilişsel karmaşıklık, yapısal kopya tespiti ve tip ipucu kapsamı.
- Modül bağımlılık grafiği, Tarjan algoritmasıyla döngüsel import tespiti, Ca / Ce / kararsızlık ölçütleri.
- SQALE yöntemiyle teknik borç notu (A–E) ve riskli dosya sıralaması.
- Oturum içi rapor geçmişi (son 5 rapor) ve iki raporu karşılaştırma.

### Değişti

- Arayüz yeniden tasarlandı: açık/koyu tema, bölüm gezinmesi, mobil yerleşim.

## [1.0.0] - 2026-10-15

### Eklendi

- Public GitHub bağlantısı veya ZIP ile Python proje analizi; proje türü, framework ve teknoloji tespiti.
- AST, Radon, Ruff ve Bandit üzerine kural kataloğu; her puanı gerekçelendirilen 100 puanlık skor.
- Önceliklendirilmiş bulgular, "ilk 30 dakika / 2 saat / 1 gün" yol haritası, README taslağı, CV ve LinkedIn metinleri.
- İsteğe bağlı ücretsiz yapay zekâ yorumu: Ollama (yerel), Groq, Gemini, OpenRouter. Skor yapay zekâya bağlı değildir.
- Markdown, JSON ve CSV rapor; komut satırı ve `--min-score` ile CI kalite kapısı.
- Güvenli yükleme: proje kodu çalıştırılmaz, ZIP Slip ve zip-bomb korumaları, raporlarda gizli değer maskeleme.
