# RepoMentor AI – CV ve LinkedIn metinleri

Aşağıdaki metinler projede **gerçekten bulunan** özelliklere dayanır. Kendi katkınıza göre düzenleyin; GitHub ve demo bağlantılarını ekleyin.

## CV maddeleri

- Python ve Streamlit ile, GitHub deposu veya ZIP olarak yüklenen Python projelerini analiz eden ve önceliklendirilmiş geliştirme planı çıkaran bir kod analiz platformu geliştirdim.
- AST, Radon, Ruff ve Bandit'i birleştirerek 72 kurallık bir kural kataloğu oluşturdum: kod karmaşıklığı, tekrarlanan kod, gizli anahtar sızıntısı, SQL enjeksiyonu ve komut enjeksiyonu riskleri.
- Skoru yalnızca ölçülebilir kurallardan hesaplayan, her puanın gerekçesini gösteren ve proje büyüklüğüne göre normalize edilmiş şeffaf bir puanlama modeli tasarladım.
- Yerel Ollama, Groq ve Gemini'yi tek bir HTTP istemcisi arkasında birleştirerek tamamen ücretsiz çalışan bir LLM katmanı kurdum. Model çıktıları için JSON şeması, bozuk JSON onarımı ve ölçümlerle çelişen iddiaları eleyen kalite kapıları ekledim.
- Kullanıcı girdisini değişkenler ve fonksiyonlar boyunca izleyen, fonksiyon özetleriyle çalışan bir veri akışı (taint) analizi yazdım; SQL enjeksiyonu, komut enjeksiyonu ve SSRF gibi 9 açık türünü kaynaktan hedefe yoluyla raporluyor.
- Bilişsel karmaşıklık, yapısal kopya tespiti (AST normalleştirme) ve Tarjan algoritmasıyla döngüsel import tespitini sıfırdan uyguladım; SQALE yöntemiyle teknik borç notu hesapladım.
- Proje geneli bir çağrı grafiği kurarak kullanılmayan kodu ve hiçbir testin ulaşmadığı fonksiyonları testleri çalıştırmadan buldum; skorda test/fonksiyon oranının yerine bu statik test erişimini kullandım.
- Fonksiyon başına kontrol akış grafiği (try/finally, döngüler, match dahil) üzerine erişilemeyen kod ve kapatılmayan dosya/bağlantı analizleri yazdım; requests ve pandas dahil 27 açık kaynak kütüphanede elle doğrulanmış 6 gerçek hata buldu (ör. requests'te hiç kapatılmayan bir `ZipFile`).
- scikit-learn kodunda train/test ayrımından önce `fit` edilen ölçekleyicileri ve test verisine `fit` gibi veri sızıntılarını deyim sırasıyla izleyerek tespit eden bir analiz ve pandas anti-pattern kuralları geliştirdim.
- Jupyter Notebook kod hücrelerini tek bir sanal betiğe dizip bütün analizlerden geçiren ve bulguları hücre numarasına geri çeviren bir katman yazdım; hücreler arasındaki veri sızıntılarını yakalıyor.
- Pull request'lerde temel dalla karşılaştırıp skor farkını ve yeni bulguları yorum olarak yazan bir GitHub Action geliştirdim; skor düşüşünü kalite kapısı olarak kullanıyor.
- README'deki kurulum komutlarını çalıştırmadan projeye karşı doğrulayan bir denetleyici, Shannon entropisiyle adı geçmeyen API anahtarlarını bulan bir tarayıcı ve güvenli düzeltmeleri `git apply` ile uygulanabilir bir yama olarak üreten bir otomatik düzeltme modülü yazdım.
- ZIP Slip ve zip-bomb koruması, gizli değer maskeleme ve kodu hiç çalıştırmadan analiz eden güvenli bir yükleme hattı geliştirdim; 304 otomatik testi GitHub Actions'ta çalıştırdım ve aracın kendi kodunu analiz ettiği bir kalite kapısı (≥80/100) kurdum.

## LinkedIn – proje açıklaması (kısa)

Python projelerinin kod kalitesini, güvenlik risklerini, test ve dokümantasyon durumunu ölçen; sonuçları önceliklendirilmiş bir yol haritasına dönüştüren ve ücretsiz LLM'lerle yorumlayan açık kaynak analiz aracı. Python, Streamlit, AST, Radon, Bandit, Ruff, Ollama.

## LinkedIn – gönderi

🧭 Yeni projem: RepoMentor AI

Yapay zekâ ile kod yazmak artık kolay. Peki yazılan kod gerçekten kaliteli mi?

RepoMentor AI'a bir GitHub bağlantısı veya ZIP verdiğinizde:
• Kod karmaşıklığını, tekrar eden kodu ve lint sorunlarını ölçüyor
• Açıkta kalmış API anahtarlarını, eval / SQL enjeksiyonu gibi riskleri buluyor
• Kullanılan paket sürümlerindeki bilinen açıkları (CVE) ücretsiz OSV.dev veritabanından bulup güvenli sürümü öneriyor
• Hiç çağrılmayan fonksiyonları ve hiçbir testin ulaşmadığı kodu çağrı grafiğiyle buluyor
• Erken return ya da hata yolunda kapatılmayan dosya ve veritabanı bağlantılarını yakalıyor
• Makine öğrenmesi projelerinde train/test veri sızıntısını tespit ediyor (ölçülen başarıyı sessizce şişiren klasik hata)
• README'deki kurulum komutlarının gerçekten çalışıp çalışmayacağını kontrol ediyor
• Jupyter Notebook'ları hücre hücre inceliyor; hücreler arası veri sızıntısını yakalıyor
• GitHub Action olarak her pull request'e "skor 82 → 79, 2 yeni bulgu" yorumu yazıyor
• Projeyi tıklanabilir bir kod haritası olarak çiziyor; en riskli dosya kırmızı yanıyor
• Güvenlik açıklarını, kullanıcı girdisinden tehlikeli çağrıya uzanan bir saldırı yolu diyagramıyla gösteriyor
• Güvenli düzeltmeleri, kodunuza dokunmadan `git apply` ile uygulanacak bir yama olarak veriyor
• Test ve README durumunu değerlendiriyor
• 100 üzerinden, her puanını gerekçelendiren bir skor veriyor
• "İlk 30 dakikada / 2 saatte / 1 günde" yapılacaklar planı çıkarıyor
• CV ve LinkedIn metni öneriyor

Benim için en önemli tasarım kararı şuydu: ölçülebilen her şeyi kodla ölçmek (AST, Radon, Bandit, Ruff), yapay zekâyı ise yalnızca yorum için kullanmak. Skor hiçbir zaman LLM'e bağlı değil. Model, statik analizin ölçtüğüyle çelişen bir şey söylerse o öneri eleniyor.

Kural tabanlı analiz ücretsiz ve yapay zekâ varsayılan olarak kapalı. İstenirse bilgisayarda çalışan Ollama açılabiliyor; bu modda kod dışarı gönderilmiyor. Bulut sağlayıcıları da isteğe bağlı seçilebiliyor. Son beş raporu oturum içinde karşılaştırıp bulguların ve puanların değişimini görebiliyor, rapora özel görev planını takip edebiliyorum.

En keyifli kısım: araç kendi kodunu da analiz ediyor. İlk sürümde kendi kodumda 68 karmaşıklıkta bir fonksiyon buldu 😅 Yeniden düzenledikten sonra skor 96/100'e çıktı ve bu kontrol artık CI'da her push'ta çalışıyor.

Analizlerin çoğu hazır araç değil, kendi yazdığım algoritmalar: veri akışı (taint) analizi, çağrı grafiği, kontrol akış grafiği, bilişsel karmaşıklık, Tarjan ile döngü tespiti. Kontrol akışı analizini requests, pandas ve numpy dahil 27 açık kaynak kütüphanede denedim; ilk sürümün yanlış alarmlarını tek tek inceleyip giderdim, son sürümün bulduğu 6 sorunun hepsi gerçek hataydı.

Kullandığım teknolojiler: Python, Streamlit, AST, Radon, Bandit, Ruff, Ollama, pytest, GitHub Actions, Docker

🔗 GitHub: https://github.com/yes3760/repomentor-ai
🌐 Demo: [bağlantı]

#python #yazılım #yapayzeka #codequality #opensource #portfolio
