# Katkı rehberi

RepoMentor AI'a katkı vermek istediğiniz için teşekkürler. Hata bildirimleri, yanlış alarm örnekleri, yeni kural önerileri ve pull request'ler [GitHub üzerinden](https://github.com/yes3760/repomentor-ai/issues) memnuniyetle karşılanır. Issue ve PR'larda Türkçe ya da İngilizce yazabilirsiniz.

## Geliştirme ortamı

Gereksinim: Python 3.11 veya üstü.

```bash
git clone https://github.com/yes3760/repomentor-ai.git
cd repomentor-ai
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Yapay zekâ özellikleri isteğe bağlıdır; geliştirme için anahtar gerekmez.

## Değişiklik göndermeden önce

```bash
ruff check .
pytest
python -m repomentor . --min-score 80 --no-osv
```

Son komut RepoMentor'un kendi kodunu analiz eder ve skor 80'in altına düşerse hata verir. CI aynı adımları Python 3.11, 3.12 ve 3.13'te çalıştırır.

## Tasarım ilkeleri

Bu ilkeler projenin güvenilirliğini taşır; değiştiren bir öneri varsa önce bir issue'da tartışalım.

- **Analiz edilen kod asla çalıştırılmaz.** Dosyalar yalnızca okunur ve `ast` ile ayrıştırılır. Alt süreç olarak yalnızca Ruff ve Bandit çalışır.
- **Skor yalnızca deterministik kurallardan gelir.** Yapay zekâ yorum yapar, skoru değiştiremez.
- **Kesinlik, kapsamdan önce gelir.** Emin olunamayan durumda raporlamayın: yanlış bir uyarı, kaçırılan bir bulgudan daha çok güven kaybettirir.
- **Gizli değerler dışarı çıkmaz.** Raporlarda maskelenir; `.env`, sertifika ve anahtar dosyaları yapay zekâya gönderilmez.
- **Testler ağa çıkmaz.** OSV.dev istekleri `tests/conftest.py` içindeki sahte istemciyle karşılanır.
- **Sıfır maliyet.** Yalnızca ücretsiz araçlar ve ücretsiz katmanı olan servisler kullanılır.
- **Kendi ilacını içer.** RepoMentor'un kendi kodunda veri akışı bulgusu, kullanılmayan kod, erişilemeyen kod ve bozuk README komutu olmaması testlerle güvence altındadır.

## Yeni bir kural eklemek

1. `repomentor/analyzer/rules.py` içindeki kataloğa bir `Rule(...)` ekleyin: kimlik (ör. `QLT016`), başlık, ciddiyet, kategori, neden önemli olduğu, çözüm önerisi ve tahmini düzeltme süresi (dakika). Metinlerde `{count}` gibi yer tutucular kullanılabilir.
2. İlgili analizörde bulguyu `make_issue("QLT016", konumlar, değerler)` ile üretin.
3. Kural skoru etkileyecekse `score_calculator.py` içinde gerekçesi görünen bir ceza ekleyin.
4. En az bir **pozitif** (bulunmalı) ve bir **negatif** (doğru kod işaretlenmemeli) test yazın. `tests/conftest.py` içindeki `make_project` fikstürü geçici bir proje kurar.
5. Gerekirse arayüze (`repomentor/ui/engine_views.py`) ve Markdown raporuna (`repomentor/analyzer/report_builder.py`) ekleyin.

## Yeni bir analiz algoritması

- `repomentor/analyzer/` altında ayrı bir modül olarak yazın ve `pipeline.py` içindeki `run_rules` fonksiyonuna bağlayın.
- Yanlış alarm oranını gerçek kodda ölçün (ör. sanal ortamdaki popüler kütüphaneler üzerinde) ve sonucu PR açıklamasına yazın.
- Fonksiyonları küçük tutun. Bilişsel karmaşıklığı 15 veya döngüsel karmaşıklığı 11 ve üstü olan fonksiyonların oranı, projenin kendi skorunu düşürür.

## Örnek projeler

`examples/` altındaki projeler hataları **bilerek** içerir ve testler bu hatalara dayanır; lütfen düzeltmeyin. Yeni bir analizi göstermek için örneklere ekleme yaparsanız README'deki listeyi de güncelleyin.

## Commit ve pull request

- Küçük ve tek konulu PR'lar tercih edilir.
- Kullanıcıya görünen metinler Türkçe; kod, isimler, yorumlar ve docstring'ler İngilizcedir.
- `CHANGELOG.md` dosyasının "Yayınlanmamış" bölümüne bir satır ekleyin.

## Hata bildirmek

- **Yanlış alarm veya kaçırılan bulgu:** en küçük kod örneğiyle ve beklediğiniz sonuçla bir issue açın.
- **RepoMentor'da bir güvenlik açığı:** herkese açık issue açmayın; [SECURITY.md](SECURITY.md) dosyasındaki adımları izleyin.
