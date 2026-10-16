"""Orchestrates the full analysis: rules first, optional LLM interpretation last."""

from __future__ import annotations

import time
from typing import Callable

from repomentor.ai.llm_analyzer import run_ai_analysis
from repomentor.ai.providers import LLMConfig
from repomentor.analyzer.autofix import build_fixes
from repomentor.analyzer.career import build_career_texts, build_strengths, build_summary
from repomentor.analyzer.cfg import analyze_flow
from repomentor.analyzer.context import AnalysisContext
from repomentor.analyzer.dependency_analyzer import analyze_dependencies
from repomentor.analyzer.documentation_analyzer import analyze_documentation
from repomentor.analyzer.file_tree import scan_project
from repomentor.analyzer.import_graph import analyze_imports, cycle_issues
from repomentor.analyzer.insights import hotspots, technical_debt
from repomentor.analyzer.ml_analyzer import analyze_data_science
from repomentor.analyzer.organization_analyzer import analyze_organization
from repomentor.analyzer.project_detector import detect_project
from repomentor.analyzer.quality_analyzer import analyze_quality
from repomentor.analyzer.repository_loader import LoadedProject
from repomentor.analyzer.roadmap import build_roadmap
from repomentor.analyzer.score_calculator import calculate_score
from repomentor.analyzer.security_analyzer import analyze_security
from repomentor.analyzer.test_analyzer import analyze_tests
from repomentor.analyzer.usage_analyzer import analyze_usage
from repomentor.models.analysis_result import AIInsights, AnalysisResult, CareerTexts
from repomentor.utils.constants import APP_VERSION

Progress = Callable[[str, float], None]


def _noop(_: str, __: float) -> None:
    pass


def _language_warning(primary: str | None) -> list[str]:
    if not primary or primary in {"Python", "Jupyter Notebook"}:
        return []
    return [
        f"Projenin ana dili {primary} görünüyor. Bu sürüm derin analizi yalnızca Python için yapar; "
        "README, güvenlik (gizli anahtar) ve organizasyon kontrolleri yine de uygulandı."
    ]


def run_rules(loaded: LoadedProject, progress: Progress, run_tools: bool = True, check_dependencies: bool = True) -> AnalysisContext:
    """Every deterministic check. Fast, offline, and the only input to the score."""
    progress("Dosyalar taranıyor ve gereksiz klasörler filtreleniyor…", 0.05)
    project = scan_project(loaded.root)
    progress("Proje türü ve teknolojiler tespit ediliyor…", 0.15)
    info = detect_project(project, loaded.name, loaded.source, loaded.source_url, loaded.github)
    warnings = project.warnings + _language_warning(info.primary_language)
    if not project.files:
        warnings.append("Projede analiz edilecek dosya bulunamadı.")

    progress("README ve dokümantasyon inceleniyor…", 0.25)
    docs, issues = analyze_documentation(project, info)
    progress("Test yapısı inceleniyor…", 0.32)
    tests, test_issues = analyze_tests(project, info)
    progress("Güvenlik taraması yapılıyor (gizli anahtarlar, veri akışı analizi, Bandit)…", 0.42)
    security, security_issues = analyze_security(project, loaded.source, run_tools=run_tools)
    if check_dependencies:
        progress("Bağımlılıklar bilinen açıklara karşı kontrol ediliyor (OSV.dev)…", 0.5)
    dependencies, dependency_issues = analyze_dependencies(project, enabled=check_dependencies)
    progress("Kod kalitesi ölçülüyor (Radon, Ruff, AST, kontrol akışı)…", 0.58)
    quality, quality_issues = analyze_quality(project, run_tools=run_tools)
    quality.flow, flow_issues = analyze_flow(project)
    quality_issues += flow_issues
    progress("Modül bağımlılık grafiği kuruluyor…", 0.64)
    imports = analyze_imports(project)
    quality_issues += cycle_issues(imports)
    progress("Çağrı grafiği kuruluyor: kullanılmayan kod ve test erişimi…", 0.67)
    usage, usage_issues = analyze_usage(project, library=info.project_type == "Python kütüphanesi / paketi")
    quality_issues += usage_issues
    data_stack = bool({"pandas", "scikit-learn"} & set(info.ml_libraries))
    if data_stack:
        progress("Veri bilimi kontrolleri: veri sızıntısı ve pandas kalıpları…", 0.69)
    data_science, data_science_issues = analyze_data_science(project, data_stack)
    quality_issues += data_science_issues

    issues += test_issues + security_issues + dependency_issues + quality_issues + analyze_organization(project, info)
    issues.sort(key=lambda i: i.sort_key)
    warnings += [w for w in (security.bandit_error, quality.ruff_error) if w]
    if dependencies.error:
        warnings.append(f"Bağımlılık açığı taraması yapılamadı: {dependencies.error} Diğer kontroller etkilenmedi.")
    return AnalysisContext(project, info, docs, tests, security, quality, issues, warnings, dependencies, imports, usage, data_science)


def _run_ai(llm: LLMConfig, ctx: AnalysisContext, score, career: CareerTexts, progress: Progress) -> tuple[AIInsights, CareerTexts | None]:
    label = f"Yapay zekâ yorumu alınıyor ({llm.model})…"
    progress(f"{label} Yerel modellerde bu adım 1-2 dakika sürebilir.", 0.75)

    def on_tokens(count: int) -> None:
        share = min(count / llm.output_tokens, 1.0)
        progress(f"{label} {count} token yazıldı (en fazla {llm.output_tokens})", 0.75 + 0.2 * share)

    ai, ai_career = run_ai_analysis(llm, ctx, score, on_tokens, fallback_career=career)
    if ai.error:
        ctx.warnings.append(f"Yapay zekâ analizi tamamlanamadı, kural tabanlı rapor gösteriliyor. Neden: {ai.error}")
    return ai, ai_career


def analyze_project(
    loaded: LoadedProject,
    llm: LLMConfig | None = None,
    progress: Progress | None = None,
    run_tools: bool = True,
    check_dependencies: bool = True,
) -> AnalysisResult:
    """Run the rule-based analysis, score it, and optionally add the LLM interpretation.

    `check_dependencies` sends dependency names and exact versions (never code) to OSV.dev.
    """
    progress = progress or _noop
    started = time.perf_counter()
    ctx = run_rules(loaded, progress, run_tools, check_dependencies)

    progress("Skor hesaplanıyor…", 0.7)
    score = calculate_score(ctx)
    modular = any("/" in p for p in ctx.project.source_python_files)
    career = build_career_texts(ctx.info, ctx.quality, ctx.tests, ctx.docs, modular=modular)
    ai = None
    if llm is not None:
        ai, ai_career = _run_ai(llm, ctx, score, career, progress)
        career = ai_career or career

    progress("Otomatik düzeltme yaması hazırlanıyor…", 0.96)
    fixes = build_fixes(ctx.project, ctx.issues, run_tools)
    progress("Rapor hazırlanıyor…", 0.97)
    return AnalysisResult(
        project=ctx.info,
        files=ctx.project.files,
        documentation=ctx.docs,
        tests=ctx.tests,
        security=ctx.security,
        quality=ctx.quality,
        issues=ctx.issues,
        score=score,
        roadmap=build_roadmap(ctx.issues),
        career=career,
        summary=build_summary(ctx.info, ctx.quality, score, ctx.issues),
        strengths=build_strengths(ctx.info, ctx.quality, ctx.security, ctx.docs, ctx.tests, ctx.issues),
        ai=ai,
        warnings=ctx.warnings,
        duration_seconds=round(time.perf_counter() - started, 1),
        version=APP_VERSION,
        dependencies=ctx.dependencies,
        imports=ctx.imports,
        usage=ctx.usage,
        data_science=ctx.data_science,
        fixes=fixes,
        debt=technical_debt(ctx.issues, ctx.quality.sloc),
        hotspots=hotspots(ctx.quality, ctx.issues),
    )
