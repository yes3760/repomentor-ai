"""Build a compact, masked context, ask the LLM, and validate the answer.

The model receives a summary of the static analysis rather than the whole
repository: it is cheaper, fits free-tier token limits, and lets the model
spend its attention on interpretation instead of counting.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import PurePosixPath

from repomentor.ai.prompts import OUTPUT_SCHEMA, SCHEMA_HINT, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from repomentor.ai.providers import LLMConfig, LLMError, TokenProgress, chat_json
from repomentor.ai.response_parser import ParseError, extract_json, normalise_response
from repomentor.analyzer.context import AnalysisContext
from repomentor.analyzer.file_tree import ProjectFiles, render_tree
from repomentor.analyzer.rules import SHORT_LABELS
from repomentor.models.analysis_result import AIInsights, CareerTexts, ProjectInfo, QualityReport, ScoreReport
from repomentor.utils.text_utils import mask_secrets, truncate

NEVER_SEND = (".env", "secrets", "credentials", "id_rsa", ".pem", ".key", ".p12", "service-account", "serviceaccount")


def is_sendable(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return not any(marker in name for marker in NEVER_SEND)


def select_snippets(project: ProjectFiles, info: ProjectInfo, quality: QualityReport, budget: int) -> list[tuple[str, str]]:
    """Pick the files that best explain the project: entry points, hot spots, biggest modules."""
    ordered: list[str] = []

    def add(path: str | None) -> None:
        if path and path in project.texts and path not in ordered and is_sendable(path) and not project.is_test(path):
            ordered.append(path)

    for path in info.entry_points:
        add(path)
    for fn in quality.most_complex[:4]:
        add(fn.file)
    for path in sorted(project.source_python_files, key=lambda p: -len(project.texts[p]))[:6]:
        add(path)

    snippets: list[tuple[str, str]] = []
    remaining = budget
    per_file = max(budget // max(min(len(ordered), 4), 1), 1200)
    for path in ordered:
        if remaining < 600:
            break
        content = truncate(mask_secrets(project.texts[path]), min(per_file, remaining))
        snippets.append((path, content))
        remaining -= len(content) + len(path) + 20
    return snippets


def _engine_facts(ctx: AnalysisContext) -> dict:
    """Call graph, control flow, data-science and README-command results, as labels (never source lines)."""
    reach = ctx.usage.test_reach
    return {
        "static_test_reach": round(reach, 2) if reach is not None else None,
        "unused_functions": [u.name for u in ctx.usage.unused[:8]],
        "control_flow_findings": [f"{SHORT_LABELS[f.rule]}: {f.function}() ({f.file})" for f in ctx.quality.flow[:5]],
        "data_science_findings": [f"{SHORT_LABELS[f.rule]} ({f.file})" for f in ctx.data_science.findings[:6]],
        "broken_readme_commands": [mask_secrets(b.command) for b in ctx.docs.broken_commands[:5]],
    }


def _context_json(ctx: AnalysisContext, score: ScoreReport) -> dict:
    """Facts and metrics the model should reason about (no source code)."""
    q, t, d, info = ctx.quality, ctx.tests, ctx.docs, ctx.info
    coverage = d.docstring_coverage
    return {
        "project_name": info.name,
        "project_type": info.project_type,
        "technologies": info.technologies,
        "github_description": (info.github or {}).get("description"),
        "entry_points": info.entry_points,
        "metrics": {
            "python_files": q.python_files,
            "source_lines": q.sloc,
            "functions": q.functions,
            "classes": q.classes,
            "avg_function_length": q.avg_function_length,
            "avg_cyclomatic_complexity": q.avg_complexity,
            "avg_maintainability_index": q.avg_maintainability,
            "test_files": len(t.test_files),
            "test_functions": t.test_functions,
            "docstring_coverage": round(coverage, 2) if coverage is not None else None,
            "avg_cognitive_complexity": q.avg_cognitive,
            "confirmed_taint_flows": [f"{f.kind}: {f.source} -> {f.sink}" for f in ctx.security.taint_flows[:5]],
            "import_cycles": [" -> ".join(c) for c in ctx.imports.cycles[:3]],
            **_engine_facts(ctx),
        },
        "readme_checks": d.checks,
        "rule_based_score": {"overall": score.overall, **{c.key: c.score for c in score.categories}},
        "already_found_issues": [
            {"title": i.title.replace("`", ""), "severity": i.severity, "file": i.file}
            for i in sorted(ctx.issues, key=lambda i: i.sort_key)[:15]
        ],
    }


def build_prompt(ctx: AnalysisContext, score: ScoreReport, budget_chars: int) -> str:
    """User prompt within `budget_chars`: facts JSON, file tree, README and code snippets (all masked)."""
    context = _context_json(ctx, score)
    project, readme_path = ctx.project, ctx.docs.readme_path
    file_tree = truncate(render_tree([p for p in project.paths if is_sendable(p)], max_entries=120), max(budget_chars // 8, 1500))
    readme = truncate(mask_secrets(project.text(readme_path) or ""), max(budget_chars // 6, 1500)) if readme_path else "(README yok)"
    fixed = len(json.dumps(context, ensure_ascii=False)) + len(file_tree) + len(readme) + len(SCHEMA_HINT) + 600
    snippets = select_snippets(project, ctx.info, ctx.quality, max(budget_chars - fixed, 2000))
    snippet_text = "\n\n".join(f"### {path}\n```python\n{code}\n```" for path, code in snippets) or "(Python kaynak dosyası yok)"
    return USER_PROMPT_TEMPLATE.format(
        context_json=json.dumps(context, ensure_ascii=False, indent=1),
        file_tree=file_tree,
        readme=readme,
        snippets=snippet_text,
        schema_hint=SCHEMA_HINT,
    )


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower().replace("`", "")) if len(w) > 2 and not w.isdigit()}


def is_duplicate(title: str, known_titles: list[str], threshold: float = 0.5) -> bool:
    """Small models often repeat findings they were told about; drop near-copies."""
    words = _tokens(title)
    if not words:
        return True
    for known in known_titles:
        other = _tokens(known)
        if other and len(words & other) / len(words | other) >= threshold:
            return True
    return False


# Checks the static analysis always performs. An AI "issue" about one of these
# is either a duplicate (check failed) or contradicts measured facts (check
# passed), so it is dropped in both cases.
STATIC_CHECKS = [
    "README dosyası yok", "README eksik", "Test dosyası bulunamadı", "Test yok", "Lisans dosyası yok",
    ".gitignore dosyası yok", "Bağımlılık dosyası yok requirements.txt", "Docker desteği yok",
    "Testler CI'da otomatik çalışmıyor", "Ortam değişkenleri belgelenmemiş .env.example yok",
    "Desteklenen Python sürümü belirtilmemiş", "Docstring kapsamı düşük",
]

FIRST_PERSON_PAST = re.compile(r"(?:d|t)(?:ı|i|u|ü)m\b[.!]?\s*$")


def is_cv_style(bullets: list[str]) -> bool:
    """CV bullets should read 'geliştirdim', not 'geliştirmektedir'."""
    hits = sum(bool(FIRST_PERSON_PAST.search(b.strip())) for b in bullets)
    return len(bullets) >= 2 and hits >= len(bullets) * 0.6


WEB_FRAMEWORKS = {"FastAPI", "Flask", "Django", "Starlette", "Sanic", "aiohttp", "Tornado"}


def _no_serious_security(ctx: AnalysisContext, score: ScoreReport) -> bool:
    return not any(i.category == "security" and i.severity in {"critical", "high"} for i in ctx.issues)


# A claim matching the pattern is kept only when the measured facts support it.
# Small models happily write "I stored secrets safely in .env" for a repo whose
# committed .env is the top security finding; these checks stop that.
CLAIM_CHECKS = (
    (re.compile(r"test|pytest|unittest", re.I), lambda ctx, score: ctx.tests.test_functions > 0),
    (re.compile(r"docker|container", re.I), lambda ctx, score: ctx.info.has_docker),
    (re.compile(r"\bci\b|ci/cd|github actions|sürekli entegrasyon", re.I), lambda ctx, score: ctx.info.has_ci),
    (re.compile(r"güvenli|güvenlik|\.env|gizli bilgi|şifrele|secure", re.I), _no_serious_security),
    (re.compile(r"\bapi\b|endpoint", re.I), lambda ctx, score: bool(set(ctx.info.frameworks) & WEB_FRAMEWORKS)),
    (re.compile(r"okunabil|temiz|kaliteli|iyi yapılandır|düzenli|modüler|readable|clean", re.I),
     lambda ctx, score: score.category("quality").score >= 75),
    (re.compile(r"dokümantasyon|readme|belgele", re.I), lambda ctx, score: score.category("documentation").score >= 70),
)


def is_supported(text: str, ctx: AnalysisContext, score: ScoreReport) -> bool:
    """False when the text claims something the static analysis measured as missing or bad."""
    return all(check(ctx, score) for pattern, check in CLAIM_CHECKS if pattern.search(text))


def unique(items: list[str], limit: int) -> list[str]:
    kept: list[str] = []
    for item in items:
        if not is_duplicate(item, kept, threshold=0.6):
            kept.append(item)
    return kept[:limit]


def _ask(config: LLMConfig, prompt: str, known_paths: set[str], on_tokens: TokenProgress | None) -> dict:
    raw = chat_json(config, SYSTEM_PROMPT, prompt, schema=OUTPUT_SCHEMA, on_tokens=on_tokens)
    try:
        return normalise_response(extract_json(raw), known_paths)
    except ParseError:
        # One retry with a blunt reminder; small models usually comply the second time.
        raw = chat_json(config, SYSTEM_PROMPT, prompt + "\n\nÖNEMLİ: Yalnızca geçerli JSON döndür.", schema=OUTPUT_SCHEMA, on_tokens=on_tokens)
        return normalise_response(extract_json(raw), known_paths)


def _insights(insights: AIInsights, data: dict, ctx: AnalysisContext, score: ScoreReport) -> AIInsights:
    """Copy validated fields and apply the quality gates (dedupe, contradiction and claim filters)."""
    insights.summary = mask_secrets(data["summary"])
    insights.architecture_review = data["architecture_review"]
    insights.readability_review = data["readability_review"]
    insights.strengths = unique([x for x in data["strengths"] if is_supported(x, ctx, score)], 5)
    insights.readme_suggestions = unique(data["readme_suggestions"], 4)
    insights.next_steps = unique(data["next_steps"], 6)
    known = [i.title for i in ctx.issues] + STATIC_CHECKS
    insights.extra_issues = [i for i in data["issues"] if not is_duplicate(i.title, known)]
    if not any([insights.summary, insights.architecture_review, insights.strengths, insights.extra_issues]):
        insights.error = "Model anlamlı bir içerik döndürmedi."
    return insights


def _top_up(bullets: list[str], fallback: CareerTexts | None, limit: int = 4) -> list[str]:
    """Fill up to `limit` bullets with template bullets that say something new."""
    for extra in fallback.cv_bullets if fallback else []:
        if len(bullets) >= limit:
            break
        if not is_duplicate(extra, bullets, threshold=0.4):
            bullets.append(extra)
    return bullets


def _linkedin_texts(data: dict, ctx: AnalysisContext, score: ScoreReport, fallback: CareerTexts | None) -> tuple[str, str]:
    short, post = data["linkedin_short"], data["linkedin_post"]
    if not fallback:
        return short, post
    if not short or not is_supported(short, ctx, score):
        short = fallback.linkedin_short
    weak_post = len(post.split()) < 40 or is_duplicate(post, [short], threshold=0.6) or not is_supported(post, ctx, score)
    return short, fallback.linkedin_post if weak_post else post


def _career(data: dict, ctx: AnalysisContext, score: ScoreReport, fallback: CareerTexts | None) -> CareerTexts | None:
    """AI career texts, keeping only claims the analysis supports and topping up from the template."""
    bullets = [b for b in data["cv_bullets"] if is_supported(b, ctx, score)]
    if not is_cv_style(bullets):
        return None
    short, post = _linkedin_texts(data, ctx, score, fallback)
    return CareerTexts(project_title=ctx.info.name, cv_bullets=_top_up(bullets, fallback), linkedin_post=post, linkedin_short=short, source="ai")


def run_ai_analysis(
    config: LLMConfig,
    ctx: AnalysisContext,
    score: ScoreReport,
    on_tokens: TokenProgress | None = None,
    fallback_career: CareerTexts | None = None,
) -> tuple[AIInsights, CareerTexts | None]:
    """Never raises: failures are reported inside AIInsights.error so the
    rule-based report is always delivered."""
    insights = AIInsights(provider=config.spec.label, model=config.model)
    started = time.perf_counter()
    try:
        data = _ask(config, build_prompt(ctx, score, config.context_chars), set(ctx.project.paths), on_tokens)
    except (LLMError, ParseError) as exc:
        insights.error = str(exc)
        data = None
    except Exception as exc:  # network stack / unexpected provider payloads
        insights.error = f"Yapay zekâ analizi başarısız oldu: {exc.__class__.__name__}"
        data = None
    insights.duration_seconds = round(time.perf_counter() - started, 1)
    if data is None:
        return insights, None
    return _insights(insights, data, ctx, score), _career(data, ctx, score, fallback_career)
