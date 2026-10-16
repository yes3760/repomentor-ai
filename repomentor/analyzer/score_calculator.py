"""Deterministic 0-100 scoring. The LLM never touches the score.

Every point added or removed is recorded as a ScoreFactor so the UI can show
exactly why a category got its score.
"""

from __future__ import annotations

from repomentor.analyzer.context import AnalysisContext
from repomentor.models.analysis_result import (
    CategoryScore,
    DocumentationReport,
    MLReport,
    ProjectInfo,
    QualityReport,
    ScoreFactor,
    ScoreReport,
    TestReport,
)
from repomentor.models.issue import Issue
from repomentor.utils.constants import CATEGORY_LABELS, LONG_FILE_LINES, SCORE_BANDS, SCORE_WEIGHTS
from repomentor.utils.text_utils import share_percent


class _Card:
    """Accumulates factors and clamps the result to 0-100."""

    def __init__(self, start: int) -> None:
        self.score = start
        self.factors: list[ScoreFactor] = [ScoreFactor("Başlangıç puanı", start)] if start else []

    def add(self, label: str, delta: int) -> None:
        if delta:
            self.score += delta
            self.factors.append(ScoreFactor(label, delta))

    def note(self, label: str) -> None:
        """Record a reason that explains a missing score without changing it."""
        self.factors.append(ScoreFactor(label, 0))

    def penalty(self, label: str, count: int, each: int, cap: int) -> None:
        if count:
            self.add(f"{label} ({count})", -min(count * each, cap))

    @property
    def value(self) -> int:
        return max(0, min(100, round(self.score)))


# (share of functions above which, penalty) – first match wins.
SHARE_STEPS = ((0.10, 20), (0.05, 12), (0.02, 6), (0.0, 3))


def _share_penalty(card: _Card, label: str, count: int, total: int) -> None:
    """Penalise by the share of affected functions, so big projects are not punished for size."""
    if not count or not total:
        return
    share = count / total
    penalty = next(p for threshold, p in SHARE_STEPS if share > threshold)
    card.add(f"{label}: {count}/{total} fonksiyon (%{share * 100:.0f})", -penalty)


def _lint_penalty(card: _Card, q: QualityReport) -> None:
    if not q.ruff_ran or not q.sloc:
        return
    density = q.ruff_total / max(q.sloc / 1000, 0.2)
    for limit, penalty, label in ((20, 15, "yüksek"), (8, 8, "orta"), (3, 3, "düşük")):
        if density > limit:
            card.add(f"Lint yoğunluğu {label} ({density:.0f} uyarı / 1000 satır)", -penalty)
            return


def _docstring_factor(card: _Card, doc: DocumentationReport) -> None:
    coverage = doc.docstring_coverage
    if coverage is None or doc.documentable_symbols < 6:
        return
    if coverage < 0.3:
        card.add(f"Docstring kapsamı düşük (%{coverage * 100:.0f})", -5)
    elif coverage >= 0.7:
        card.add(f"Docstring kapsamı iyi (%{coverage * 100:.0f})", +3)


def score_quality(q: QualityReport, doc: DocumentationReport, unused: int = 0, ml: MLReport | None = None) -> _Card:
    """Start at 100 and subtract for complexity, size, duplication, lint and missing docs."""
    if not q.python_files:
        card = _Card(50)
        card.note("Python dosyası yok; nötr puan verildi")
        return card
    card = _Card(100)
    _share_penalty(card, "Karmaşık fonksiyon (bilişsel ≥ 15 veya döngüsel ≥ 11)", q.hard_functions, q.functions)
    card.penalty("Çok karmaşık fonksiyon (bilişsel ≥ 30 veya döngüsel ≥ 21)", q.very_hard_functions, 8, 24)
    _share_penalty(card, "50+ satırlık fonksiyon", q.long_functions, q.functions)
    card.penalty("Bakımı zor dosya (MI < 10)", sum(1 for m in q.maintainability if m["rank"] == "C"), 6, 18)
    card.penalty("Ayrıştırılamayan dosya", len(q.syntax_errors), 10, 30)
    card.penalty("Tekrarlanan kod bloğu / yapısal kopya", len(q.duplicates) + len(q.clones), 2, 10)
    card.penalty("Kullanılmayan fonksiyon / sınıf", unused, 1, 6)
    findings = ml.findings if ml else []
    card.penalty("Veri sızıntısı (model sonuçlarını geçersiz kılar)", sum(f.rule.startswith("LEAK") for f in findings), 10, 20)
    card.penalty("pandas anti-pattern'i", sum(f.rule.startswith("PD") for f in findings), 2, 8)
    card.penalty("Erişilemeyen kod", sum(f.rule == "QLT014" for f in q.flow), 3, 9)
    card.penalty("Kapatılmayan dosya / bağlantı", sum(f.rule == "QLT015" for f in q.flow), 3, 9)
    card.penalty("Çıplak except", q.bare_excepts, 2, 10)
    _lint_penalty(card, q)
    _docstring_factor(card, doc)
    return card


SEVERITY_PENALTY = {"critical": 35, "high": 18, "medium": 8, "low": 3, "info": 0}


def score_security(issues: list[Issue]) -> _Card:
    card = _Card(100)
    for issue in sorted((i for i in issues if i.category == "security"), key=lambda i: i.sort_key):
        base = SEVERITY_PENALTY[issue.severity]
        if issue.confidence == "low":
            base //= 2
        extra = min(issue.count - 1, 3) * max(base // 4, 1) if base else 0
        card.add(f"{issue.title}", -(base + extra))
    return card


def _reach_factor(card: _Card, t: TestReport, reach: float | None) -> None:
    """How much of the code the tests can reach (call graph); the raw test/function ratio when unknown."""
    if reach is None:
        if t.ratio >= 0.5:
            card.add(f"Test / fonksiyon oranı iyi ({t.ratio:.2f})", 15)
        elif t.ratio >= 0.2:
            card.add(f"Test / fonksiyon oranı orta ({t.ratio:.2f})", 8)
        return
    label = f"Testler fonksiyonların %{share_percent(reach)}'ine ulaşıyor (statik)"
    if reach >= 0.7:
        card.add(label, 15)
    elif reach >= 0.4:
        card.add(label, 8)
    else:
        card.note(label)


def score_testing(t: TestReport, has_python: bool, reach: float | None = None) -> _Card:
    card = _Card(0)
    if not has_python or t.source_functions == 0:
        card = _Card(50)
        card.note("Test edilecek Python fonksiyonu yok; nötr puan verildi")
        return card
    if not t.test_files:
        card.note("Test dosyası yok")
        if t.frameworks:
            card.add("Test aracı bağımlılıklarda var", 10)
        return card
    card.add(f"{len(t.test_files)} test dosyası var", 40)
    if t.test_functions >= 10:
        card.add(f"{t.test_functions} test fonksiyonu", 20)
    elif t.test_functions >= 3:
        card.add(f"{t.test_functions} test fonksiyonu", 10)
    _reach_factor(card, t, reach)
    if t.ci_runs_tests:
        card.add("Testler CI'da otomatik çalışıyor", 15)
    if t.has_conftest or t.has_coverage_config:
        card.add("pytest yapılandırması / coverage ayarı", 10)
    return card


def score_documentation(d: DocumentationReport) -> _Card:
    card = _Card(0)
    if not d.has_readme:
        card.note("README yok")
        if d.license_file:
            card.add("Lisans dosyası", 5)
        return card
    card.add("README mevcut", 20)
    points = {
        "has_installation": ("Kurulum bölümü", 15),
        "has_usage": ("Kullanım bölümü", 15),
        "has_features": ("Özellikler bölümü", 10),
        "has_code_blocks": ("Komut / kod örnekleri", 10),
        "has_screenshot": ("Ekran görüntüsü", 10),
        "has_tech_stack": ("Teknoloji listesi", 5),
        "has_license": ("Lisans bilgisi", 5),
    }
    for key, (label, value) in points.items():
        if d.checks.get(key):
            card.add(label, value)
    if d.readme_words >= 250:
        card.add(f"Yeterli uzunluk ({d.readme_words} kelime)", 10)
    elif d.readme_words < 80:
        card.add(f"Çok kısa ({d.readme_words} kelime)", -10)
    return card


def score_organization(ctx: AnalysisContext) -> _Card:
    """Points for the structural basics a reviewer looks for first; circular imports cost points."""
    project, info, sec, d, t = ctx.project, ctx.info, ctx.security, ctx.docs, ctx.tests
    sources = project.source_python_files
    no_huge_files = not any(project.texts[p].count("\n") > LONG_FILE_LINES for p in sources)
    checks = [
        (bool(info.dependency_files), "Bağımlılık dosyası", 20),
        (sec.has_gitignore, ".gitignore", 15),
        (bool(sources) and (len(sources) < 8 or any("/" in p for p in sources)), "Anlamlı klasör / modül yapısı", 20),
        (bool(sources) and no_huge_files, f"{LONG_FILE_LINES}+ satırlık dosya yok", 15),
        (bool(d.license_file), "Lisans dosyası", 10),
        (d.has_env_example or not sec.env_committed, "Gizli ayarlar koddan ayrı", 10),
        (any(p.startswith(("tests/", "test/")) for p in t.test_files), "Testler ayrı klasörde", 10),
    ]
    card = _Card(0)
    for passed, label, points in checks:
        if passed:
            card.add(label, points)
    card.penalty("Döngüsel import", len(ctx.imports.cycles), 10, 20)
    return card


def score_runnable(info: ProjectInfo, d: DocumentationReport) -> _Card:
    card = _Card(0)
    if info.dependency_files:
        card.add("Bağımlılık dosyası", 30)
    if info.entry_points:
        card.add(f"Giriş noktası: {info.entry_points[0]}", 25)
    elif info.project_type == "Python kütüphanesi / paketi":
        card.add("Paket yapısı (giriş noktası gerekmez)", 25)
    if d.checks.get("has_usage") and d.checks.get("has_installation"):
        card.add("README'de kurulum ve çalıştırma adımı", 20)
    elif d.checks.get("has_usage") or d.checks.get("has_installation"):
        card.add("README'de kısmi kurulum/çalıştırma bilgisi", 10)
    if info.python_version:
        card.add(f"Python sürümü belirtilmiş ({info.python_version})", 5)
    if info.has_docker:
        card.add("Docker desteği", 10)
    if info.has_ci:
        card.add("CI yapılandırması", 10)
    return card


def score_band(score: int) -> str:
    return next(label for threshold, label in SCORE_BANDS if score >= threshold)


def calculate_score(ctx: AnalysisContext) -> ScoreReport:
    """Weighted 0-100 score from the rule-based findings only (never from the LLM)."""
    cards = {
        "quality": score_quality(ctx.quality, ctx.docs, len(ctx.usage.unused), ctx.data_science),
        "security": score_security(ctx.issues),
        "testing": score_testing(ctx.tests, bool(ctx.project.python_files), ctx.usage.test_reach),
        "documentation": score_documentation(ctx.docs),
        "organization": score_organization(ctx),
        "runnable": score_runnable(ctx.info, ctx.docs),
    }
    categories = [
        CategoryScore(key=key, label=CATEGORY_LABELS[key], score=card.value, weight=SCORE_WEIGHTS[key], factors=card.factors)
        for key, card in cards.items()
    ]
    overall = round(sum(c.score * c.weight for c in categories))
    return ScoreReport(overall=overall, band=score_band(overall), categories=categories)
