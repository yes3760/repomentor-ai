# Görev Takip API

FastAPI ve SQLite ile yazılmış, küçük ekipler için basit bir görev (todo) yönetim REST API'si.

![Swagger arayüzü](docs/screenshot.png)

## Özellikler

- Görev oluşturma, listeleme, güncelleme ve silme (CRUD)
- Görevleri duruma göre filtreleme (`todo`, `doing`, `done`)
- Pydantic ile istek doğrulama
- SQLite ile kalıcı veri saklama
- Otomatik Swagger dokümantasyonu (`/docs`)

## Kullanılan teknolojiler

Python 3.11+, FastAPI, Pydantic, SQLite, pytest, Docker, GitHub Actions

## Kurulum

```bash
git clone https://github.com/ornek/gorev-takip-api.git
cd gorev-takip-api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Kullanım

```bash
uvicorn app.main:app --reload
```

Tarayıcıda `http://localhost:8000/docs` adresini açın.

```bash
curl -X POST localhost:8000/tasks -H "Content-Type: application/json" -d '{"title": "README yaz"}'
```

## Testler

```bash
pytest
```

## Docker

```bash
docker build -t gorev-takip-api .
docker run -p 8000:8000 gorev-takip-api
```

## Lisans

MIT
