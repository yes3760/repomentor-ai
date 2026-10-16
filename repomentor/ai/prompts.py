"""Prompt text and the JSON contract the model must follow."""

from __future__ import annotations

SYSTEM_PROMPT = """Sen deneyimli bir yazılım mimarı ve code review uzmanısın.

Görevin: sana verilen proje analiz verilerini (statik analiz sonuçları, dosya ağacı, README ve seçilmiş kod parçaları) inceleyerek geliştiriciye açık, uygulanabilir ve teknik olarak ölçülü öneriler sunmak.

Kurallar:
- Yalnızca sana verilen verilere dayan. Görmediğin bir dosya veya kod hakkında kesin iddia kurma.
- Potansiyel riskleri kesin güvenlik açığı gibi sunma; "olabilir", "potansiyel" gibi ifadeler kullan.
- Statik analizin zaten bulduğu sorunları tekrar etme; bunlar "already_found_issues" listesinde. Sen yorum gerektiren, kodu okuyarak görülebilen ek sorunlara odaklan (mimari, sorumluluk ayrımı, hata yönetimi, isimlendirme, okunabilirlik).
- Her öneri için dosya, gerekçe ve somut çözüm belirt. Dosya adı yalnızca dosya ağacında geçen bir yol olabilir.
- Önerileri önem sırasına göre sırala.
- Gereksiz teknik jargon kullanma; junior bir geliştiricinin anlayacağı netlikte yaz.
- CV ve LinkedIn metinlerinde yalnızca projede gerçekten tespit edilen teknolojileri ve özellikleri kullan; abartma, uydurma metrik ekleme.
- CV maddelerini birinci tekil şahıs ve geçmiş zamanla yaz (ör. "FastAPI ve SQLite kullanarak REST API geliştirdim.", "pytest ile birim testleri yazdım."); "geliştirmektedir" gibi üçüncü şahıs kullanma.
- Tüm metinleri Türkçe yaz. Kısa ve öz ol; her alan için verilen uzunluğu aşma.
- Yanıtı YALNIZCA geçerli JSON olarak döndür; JSON dışında hiçbir şey yazma."""

def _text(description: str, max_length: int) -> dict:
    return {"type": "string", "description": description, "maxLength": max_length}


def _list(description: str, max_items: int, max_length: int = 220) -> dict:
    return {"type": "array", "items": {"type": "string", "maxLength": max_length}, "maxItems": max_items, "description": description}


# Length limits keep answers short; Ollama enforces them while decoding, so a
# slow local model cannot ramble for minutes or return truncated JSON.
OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": _text("Projenin ne yaptığını ve genel durumunu anlatan 2-4 cümle.", 600),
        "architecture_review": _text("Mimari / klasör yapısı / sorumluluk ayrımı değerlendirmesi, 2-4 cümle.", 700),
        "readability_review": _text("Kodun okunabilirliği ve isimlendirme hakkında 1-3 cümle.", 400),
        "strengths": _list("3-4 güçlü yön.", 4),
        "issues": {
            "type": "array",
            "maxItems": 3,
            "description": "Statik analizin bulmadığı en fazla 3 ek sorun.",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 100},
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "category": {"type": "string", "enum": ["security", "quality", "testing", "documentation", "organization", "runnable"]},
                    "file": {"type": "string", "maxLength": 120},
                    "explanation": {"type": "string", "maxLength": 300},
                    "recommendation": {"type": "string", "maxLength": 300},
                    "estimated_minutes": {"type": "integer"},
                },
                "required": ["title", "severity", "category", "explanation", "recommendation", "estimated_minutes"],
            },
        },
        "readme_suggestions": _list("README için 2-3 somut iyileştirme önerisi.", 3),
        "next_steps": _list("Öncelik sırasına göre 3-5 sonraki adım.", 5),
        "cv_bullets": _list("CV için 3-4 madde, birinci tekil şahıs geçmiş zaman ('geliştirdim').", 4, 200),
        "linkedin_short": _text("LinkedIn proje bölümü için 1-2 cümlelik açıklama.", 300),
        "linkedin_post": _text("LinkedIn gönderisi: problem, çözüm, teknolojiler, kapanış; 60-110 kelime.", 900),
    },
    "required": ["summary", "architecture_review", "strengths", "issues", "next_steps", "cv_bullets", "linkedin_short", "linkedin_post"],
}

USER_PROMPT_TEMPLATE = """Aşağıdaki proje analiz verilerini incele ve belirtilen JSON formatında yanıt ver.

## Proje bilgisi ve statik analiz özeti (JSON)
{context_json}

## Dosya ağacı
```
{file_tree}
```

## README (maskelenmiş, kısaltılmış olabilir)
```
{readme}
```

## Seçilmiş kod parçaları (gizli değerler maskelenmiştir)
{snippets}

## Beklenen JSON alanları
{schema_hint}
"""

SCHEMA_HINT = """{
  "summary": "...",
  "architecture_review": "...",
  "readability_review": "...",
  "strengths": ["..."],
  "issues": [{"title": "...", "severity": "high|medium|low", "category": "security|quality|testing|documentation|organization|runnable", "file": "dosya/yolu.py", "explanation": "neden önemli", "recommendation": "nasıl düzeltilir", "estimated_minutes": 30}],
  "readme_suggestions": ["..."],
  "next_steps": ["..."],
  "cv_bullets": ["..."],
  "linkedin_short": "...",
  "linkedin_post": "..."
}"""
