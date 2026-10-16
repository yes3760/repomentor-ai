"""Rule-based project summary, strengths and CV / LinkedIn texts.

These are always produced so the app is fully useful without any LLM. When an
LLM is available its output replaces them, but these stay as the fallback.
Only facts the analyzers actually detected are claimed.
"""

from __future__ import annotations

from repomentor.models.analysis_result import (
    CareerTexts,
    DocumentationReport,
    ProjectInfo,
    QualityReport,
    ScoreReport,
    SecurityReport,
    TestReport,
)
from repomentor.models.issue import Issue
from repomentor.utils.text_utils import tr_number


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " ve " + items[-1]


def _type_after_stack(info: ProjectInfo) -> str:
    """Project type without a leading 'Python' when the stack sentence already names it."""
    phrase = _type_phrase(info)
    return phrase.removeprefix("Python ") if info.primary_language == "Python" else phrase


def _type_phrase(info: ProjectInfo) -> str:
    """Project type for use mid-sentence; proper nouns such as 'Python' keep their case."""
    text = info.project_type or "yazılım projesi"
    first = text.split()[0]
    return text if first[:1].isupper() and first not in {"Bilinmeyen"} else text[0].lower() + text[1:]


def build_summary(info: ProjectInfo, quality: QualityReport, score: ScoreReport, issues: list[Issue]) -> str:
    parts = []
    size = f"{quality.python_files} Python dosyası ve yaklaşık {tr_number(quality.sloc)} satır koddan oluşan" if quality.python_files else "Python kaynak dosyası içermeyen"
    techs = [t for t in info.frameworks + info.databases + info.ml_libraries[:3]]
    parts.append(f"**{info.name}**, {size} bir {_type_phrase(info)}.")
    if techs:
        parts.append(f"Öne çıkan teknolojiler: {_join(techs)}.")
    if info.github and info.github.get("description"):
        parts.append(f"Depo açıklaması: “{info.github['description']}”.")
    parts.append(f"Bu aracın kurallarına göre genel skor **{score.overall}/100** ({score.band}).")
    top = [i for i in sorted(issues, key=lambda i: i.sort_key) if i.severity in {"critical", "high"}][:3]
    if top:
        parts.append("Öncelikli konular: " + "; ".join(i.title.replace("`", "") for i in top) + ".")
    elif issues:
        parts.append("Kritik veya yüksek öncelikli bir bulgu yok; kalan öneriler iyileştirme niteliğinde.")
    return " ".join(parts)


def _mostly_simple(quality: QualityReport) -> bool:
    """Low average complexity is only a strength when no single function is far over the limits."""
    if not quality.functions or quality.very_hard_functions:
        return False
    return quality.avg_cognitive <= 5 and quality.hard_functions / quality.functions < 0.1


def build_strengths(info: ProjectInfo, quality: QualityReport, security: SecurityReport, docs: DocumentationReport, tests: TestReport, issues: list[Issue]) -> list[str]:
    coverage = docs.docstring_coverage or 0.0
    serious_security = any(i.category == "security" and i.severity in {"critical", "high"} for i in issues)
    candidates = [
        (docs.checks.get("has_installation") and docs.checks.get("has_usage"), "README kurulum ve kullanım adımlarını içeriyor."),
        (tests.test_functions >= 3, f"Otomatik testler mevcut ({tests.test_functions} test fonksiyonu)."),
        (tests.ci_runs_tests, "Testler CI üzerinde otomatik çalışıyor."),
        (info.has_docker, "Docker desteği var; ortam bağımsız çalıştırılabilir."),
        (_mostly_simple(quality), f"Fonksiyonlar genel olarak sade (ortalama bilişsel karmaşıklık {tr_number(quality.avg_cognitive)})."),
        (quality.functions and quality.avg_function_length <= 20 and not quality.long_functions,
         f"Fonksiyonlar kısa ve odaklı (ortalama {tr_number(quality.avg_function_length)} satır, 50 satırı aşan yok)."),
        (not serious_security, "Kritik veya yüksek seviyeli güvenlik bulgusu tespit edilmedi."),
        (security.gitignore_covers_env, "`.env` dosyası `.gitignore` ile korunuyor."),
        (docs.license_file, "Lisans dosyası mevcut."),
        (info.dependency_files, f"Bağımlılıklar tanımlı ({', '.join(info.dependency_files[:2])})."),
        (coverage >= 0.6 and docs.documentable_symbols >= 6, f"Docstring kapsamı yüksek (%{coverage * 100:.0f})."),
        (not quality.duplicates and quality.python_files >= 3, "Belirgin tekrarlanan kod bloğu yok."),
    ]
    return [text for condition, text in candidates if condition][:8]


def _cv_bullets(info: ProjectInfo, quality: QualityReport, tests: TestReport, docs: DocumentationReport, modular: bool) -> list[str]:
    main_stack = [info.primary_language or "Python"] + info.frameworks[:2]
    ml = [m for m in info.ml_libraries if m not in {"NumPy", "Matplotlib"}][:3]
    ci = " ve GitHub Actions ile her değişiklikte otomatik çalışmasını sağladım" if tests.ci_runs_tests else ""
    sloc = tr_number(quality.sloc)
    candidates = [
        (True, f"{_join(main_stack)} kullanarak {_type_after_stack(info)} geliştirdim."),
        (info.databases, f"{_join(info.databases[:2])} ile veri saklama ve sorgulama katmanını oluşturdum."),
        (ml, f"{_join(ml)} {'kütüphanesini' if len(ml) == 1 else 'kütüphanelerini'} kullanarak veri işleme / modelleme akışını kurdum."),
        (quality.python_files >= 4 and modular and quality.sloc >= 500, f"Yaklaşık {sloc} satırlık kodu modüler bir klasör yapısıyla organize ettim."),
        (tests.test_functions >= 5, f"{_join(info.test_tools[:1] or ['pytest'])} ile {tests.test_functions} otomatik test yazdım{ci}."),
        (info.has_docker, "Uygulamayı Docker ile container'laştırarak farklı ortamlarda aynı şekilde çalışmasını sağladım."),
        (docs.readme_words >= 200, "Kurulum ve kullanım adımlarını içeren kapsamlı bir proje dokümantasyonu hazırladım."),
    ]
    return [text for condition, text in candidates if condition][:5]


def _hashtag(name: str) -> str:
    return "#" + "".join(ch for ch in name.lower() if ch.isalnum())


def _linkedin_post(info: ProjectInfo, tests: TestReport) -> str:
    main_stack = [info.primary_language or "Python"] + info.frameworks[:2]
    lines = [f"🚀 Yeni projem: {info.name}", "", f"{_join(main_stack)} kullanarak bir {_type_after_stack(info)} geliştirdim."]
    if description := (info.github or {}).get("description"):
        lines += ["", f"Ne yapıyor? {description}"]
    lines += ["", "Kullandığım teknolojiler:", *[f"• {t}" for t in info.technologies[:8]]]
    extras = [label for ok, label in (
        (tests.test_functions, f"{tests.test_functions} otomatik test"),
        (info.has_docker, "Docker desteği"),
        (tests.ci_runs_tests, "CI/CD"),
    ) if ok]
    if extras:
        lines += ["", f"Kalite tarafında: {_join(extras)}."]
    hashtags = ["#python", *[_hashtag(t) for t in info.frameworks[:3]], "#yazılım", "#portfolio"]
    lines += ["", "Geri bildirimlerinize açığım! 👇", info.source_url or "[GitHub bağlantısı]", "", " ".join(dict.fromkeys(hashtags))]
    return "\n".join(lines)


def build_career_texts(info: ProjectInfo, quality: QualityReport, tests: TestReport, docs: DocumentationReport, modular: bool = False) -> CareerTexts:
    main_stack = [info.primary_language or "Python"] + info.frameworks[:2]
    return CareerTexts(
        project_title=(info.github or {}).get("description") or info.name,
        cv_bullets=_cv_bullets(info, quality, tests, docs, modular),
        linkedin_post=_linkedin_post(info, tests),
        linkedin_short=f"{_join(main_stack)} ile geliştirdiğim {info.name} projesinde {_type_after_stack(info)} tasarımı ve geliştirmesi üzerine çalıştım.",
        source="rule",
    )
