# Güvenlik politikası

## Desteklenen sürümler

| Sürüm | Güvenlik düzeltmesi |
|---|---|
| 1.2.x | ✅ |
| 1.2'den eski | ❌ |

## Açık bildirmek

Lütfen güvenlik açıkları için **herkese açık issue açmayın.** Bunun yerine GitHub'daki **Security → Report a vulnerability** bağlantısıyla ([doğrudan bağlantı](https://github.com/yes3760/repomentor-ai/security/advisories/new)) özel bir bildirim gönderin.

Bildirime şunları eklemeniz incelemeyi hızlandırır:

- etkilenen sürüm ve çalışma şekli (web arayüzü, komut satırı, Docker),
- açığı yeniden üretme adımları; mümkünse küçük bir örnek proje ya da ZIP dosyası,
- olası etki (ör. hangi verinin sızdığı ya da hangi kodun çalıştığı).

Bildirimler mümkün olan en kısa sürede incelenir. Düzeltme yayınlanana kadar ayrıntıları paylaşmamanızı rica ederiz. Bildiren kişi isterse sürüm notlarında adıyla teşekkür edilir.

## Kapsam

RepoMentor, başkalarının kodunu inceleyen bir araçtır; kendi güvenliği için önemli gördüğümüz durumlar:

- analiz edilen projedeki kodun herhangi bir yolla **çalıştırılması**,
- ZIP açma korumalarının aşılması: ZIP Slip (`../`, mutlak yol), sembolik bağlantı, dosya sayısı ve zip bombası sınırları,
- gizli değerlerin **maskelenmeden** rapora (Markdown, JSON, CSV) ya da yapay zekâ prompt'una sızması; `.env` ve anahtar dosyalarının yapay zekâya gönderilmesi,
- depodan gelen içerikle arayüzde HTML/JavaScript enjeksiyonu (XSS) veya CSV formül enjeksiyonu,
- OSV.dev'e paket adı ve sürümü dışında veri gönderilmesi,
- otomatik düzeltmenin analiz edilen dosyalara yazması ya da yamada görünmeyen bir değişiklik yapması.

Kapsam dışı:

- `examples/` altındaki demo projeler: hataları, açıklı paket sürümlerini ve sahte anahtarları **bilerek** içerir,
- analizin yanlış alarmları veya kaçırdığı bulgular: bunlar için normal bir issue açın,
- RepoMentor'un kullandığı paketlerdeki açıklar: önce ilgili projeye bildirin; sürüm yükseltmesi için issue açabilirsiniz.

## Kullanıcılar için notlar

- RepoMentor otomatik bir ön incelemedir; profesyonel bir güvenlik denetiminin yerine geçmez.
- Bulut yapay zekâ sağlayıcısı (Groq, Gemini, OpenRouter) seçildiğinde maskelenmiş kod parçaları o sağlayıcıya gönderilir. Kodun bilgisayarınızdan çıkmasını istemiyorsanız Ollama'yı kullanın ya da yapay zekâyı kapalı tutun.
- Bağımlılık taraması açıkken OSV.dev'e yalnızca paket adları ve sürümleri gider; `--no-osv` ile kapatılabilir.
