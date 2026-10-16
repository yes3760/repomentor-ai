"""Markdown, JSON and spreadsheet-friendly CSV exports of an AnalysisResult."""

from __future__ import annotations

import csv
import io
import json

from repomentor.analyzer.dependency_analyzer import coverage_text
from repomentor.analyzer.file_tree import render_tree
from repomentor.analyzer.finding_query import safe_csv_cell
from repomentor.analyzer.rules import SHORT_LABELS
from repomentor.analyzer.taint import KIND_LABELS, describe
from repomentor.models.analysis_result import AIInsights, AnalysisResult
from repomentor.models.issue import SEVERITY_LABELS, Issue, format_effort
from repomentor.utils.constants import APP_NAME, CATEGORY_LABELS
from repomentor.utils.text_utils import mask_secrets, share_percent, tr_number

DISCLAIMER = (
    "Bu skor, RepoMentor AI'ın statik kontrolleri ve temel proje kriterlerine göre hesaplanmıştır. "
    "Araç otomatik bir ön inceleme yapar; profesyonel bir güvenlik denetiminin veya kod incelemesinin yerine geçmez."
)
CHECK_NAMES = {
    "has_installation": "Kurulum adımları",
    "has_usage": "Kullanım / çalıştırma",
    "has_features": "Özellikler",
    "has_tech_stack": "Kullanılan teknolojiler",
    "has_screenshot": "Ekran görüntüsü",
    "has_code_blocks": "Kod / komut örnekleri",
    "has_license": "Lisans",
}


def _bar(score: int, width: int = 20) -> str:
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _yes_no(value: bool) -> str:
    return "evet" if value else "hayır"


def _ai(result: AnalysisResult) -> AIInsights | None:
    """AI insights only when the call succeeded."""
    return result.ai if result.ai is not None and result.ai.ok else None


def _header(result: AnalysisResult) -> list[str]:
    p, ai = result.project, _ai(result)
    return [
        f"# {APP_NAME} Analiz Raporu",
        "",
        f"**Proje:** {p.name}  ",
        f"**Kaynak:** {p.source_url or p.source.upper()}  ",
        f"**Proje türü:** {p.project_type}  ",
        f"**Teknolojiler:** {', '.join(p.technologies) or '-'}  ",
        f"**Analiz tarihi:** {result.analyzed_at} · süre {result.duration_seconds} sn  ",
        f"**Yapay zekâ:** {f'{ai.provider} / {ai.model}' if ai else 'Kullanılmadı (kural tabanlı rapor)'}",
        "",
        "## Proje Özeti",
        "",
        result.summary,
        "",
        *([f"> 🤖 **Yapay zekâ yorumu:** {ai.summary}", ""] if ai and ai.summary else []),
    ]


def _score_section(result: AnalysisResult) -> list[str]:
    out = [
        "## Genel Skor", "",
        f"### {result.score.overall}/100 — {result.score.band}", "",
        "| Kategori | Ağırlık | Puan | |", "|---|---:|---:|---|",
    ]
    out += [f"| {c.label} | %{c.weight * 100:.0f} | {c.score} | `{_bar(c.score)}` |" for c in result.score.categories]
    out += ["", f"> {DISCLAIMER}", ""]
    ai = _ai(result)
    ai_strengths = [x for x in (ai.strengths if ai else []) if x not in result.strengths]
    if result.strengths or ai_strengths:
        out += ["## Güçlü Yönler", ""] + [f"- {x}" for x in result.strengths]
        out += [f"- {x} _(yapay zekâ)_" for x in ai_strengths] + [""]
    return out


def _issue_block(issue: Issue) -> list[str]:
    locations = ", ".join(f"`{loc}`" for loc in issue.locations[:5]) or "-"
    more = f" (+{len(issue.locations) - 5} konum)" if len(issue.locations) > 5 else ""
    out = [
        f"#### {issue.title}",
        f"- **Kategori:** {issue.category} · **Kaynak:** {issue.source} · **Tahmini süre:** {issue.effort_label}",
        f"- **Konum:** {locations}{more}",
        f"- **Neden önemli:** {issue.explanation}",
        f"- **Öneri:** {issue.recommendation}",
    ]
    if issue.snippet:
        out += ["", "```", mask_secrets(issue.snippet), "```"]
    return out + [""]


def _issues_section(result: AnalysisResult) -> list[str]:
    out = ["## Bulgular", ""]
    if not result.issues:
        out += ["Herhangi bir sorun tespit edilmedi. 🎉", ""]
    for severity, label in SEVERITY_LABELS.items():
        group = [i for i in result.issues if i.severity == severity]
        if group:
            out += [f"### {label} öncelik ({len(group)})", ""]
            for issue in group:
                out += _issue_block(issue)
    ai = _ai(result)
    if ai and ai.extra_issues:
        out += ["### Yapay zekâ tarafından önerilen ek konular", "", "_Bu öneriler modelin yorumudur; doğrulayarak uygulayın._", ""]
        out += [
            f"- **[{SEVERITY_LABELS[i.severity]}] {i.title}** ({i.file or 'genel'}, ~{i.effort_label}): {i.explanation} → {i.recommendation}"
            for i in ai.extra_issues
        ]
        out.append("")
    return out


def _quality_section(result: AnalysisResult) -> list[str]:
    q = result.quality
    mi = q.avg_maintainability if q.avg_maintainability is not None else "-"
    out = [
        "## Kod Kalitesi", "",
        "| Metrik | Değer |", "|---|---|",
        f"| Python dosyası | {q.python_files} |",
        f"| Toplam satır / kod satırı | {q.total_lines} / {q.sloc} |",
        f"| Fonksiyon / sınıf | {q.functions} / {q.classes} |",
        f"| Ortalama fonksiyon uzunluğu | {q.avg_function_length} satır |",
        f"| Ortalama döngüsel / bilişsel karmaşıklık | {q.avg_complexity} / {q.avg_cognitive} |",
        f"| Eşiği aşan fonksiyon (bilişsel ≥ 15 veya döngüsel ≥ 11) | {q.hard_functions + q.very_hard_functions} |",
        f"| Ortalama Maintainability Index | {mi} |",
        f"| Tip ipucu kapsamı | {_percent(q.type_hint_coverage)} |",
        f"| Ruff uyarısı | {q.ruff_total if q.ruff_ran else 'çalıştırılmadı'} |",
        f"| Tekrarlanan blok / yapısal kopya | {len(q.duplicates)} / {len(q.clones)} |",
        "",
    ]
    if q.most_complex:
        out += ["**En zor fonksiyonlar**", "", "| Fonksiyon | Dosya | Bilişsel | Döngüsel | Satır |", "|---|---|---:|---:|---:|"]
        out += [f"| `{f.name}` | `{f.file}:{f.line}` | {f.cognitive} | {f.complexity} | {f.length} |" for f in q.most_complex[:5]]
        out.append("")
    if q.clones:
        out += ["**Yapısal kopyalar** (isimler / değerler farklı, yapı aynı)", ""]
        out += [f"- {' ↔ '.join(f'`{m}`' for m in clone.members)} (~{clone.lines} satır)" for clone in q.clones[:5]]
        out.append("")
    return out + _code_health_lines(result) + _data_science_lines(result)


def _code_health_lines(result: AnalysisResult) -> list[str]:
    unused, flow = result.usage.unused, result.quality.flow
    out = [f"- Kullanılmayan fonksiyon / sınıf (çağrı grafiği): **{len(unused)}**"]
    out += [f"  - `{u.name}` ({u.file}:{u.line})" for u in unused[:10]]
    out.append(f"- Kontrol akışı (erişilemeyen kod, kapatılmayan kaynak): **{len(flow)}**")
    out += [f"  - {SHORT_LABELS[f.rule]}: `{f.file}:{f.line}` `{f.function}()` — {f.detail}" for f in flow[:10]]
    return out + [""]


def _data_science_lines(result: AnalysisResult) -> list[str]:
    ds = result.data_science
    if not ds.applicable:
        return []
    out = ["### Veri Bilimi Kontrolleri", "", f"- Veri sızıntısı ve pandas bulguları: **{len(ds.findings)}**"]
    out += [f"  - {SHORT_LABELS[f.rule]}: `{f.file}:{f.line}` — {f.detail}" for f in ds.findings[:15]]
    return out + [""]


def _percent(value: float | None) -> str:
    return "-" if value is None else f"%{share_percent(value)}"


def _flow_lines(result: AnalysisResult) -> list[str]:
    flows = result.security.taint_flows
    out = [f"- Veri akışı analizi: {result.security.taint_functions} fonksiyon incelendi, "
           f"**{len(flows)}** doğrulanmış kaynak → hedef akışı bulundu."]
    for flow in flows[:10]:
        local = " _(yerel girdi)_" if not flow.remote else ""
        out.append(f"  - **{KIND_LABELS[flow.kind]}**{local}: {describe(flow)}")
    return out


def _debt_section(result: AnalysisResult) -> list[str]:
    debt = result.debt
    out = [
        "## Teknik Borç ve Öncelikli Dosyalar", "",
        f"- Teknik borç: **{format_effort(debt.minutes)}** · borç oranı %{tr_number(debt.ratio * 100, 1)} · bakım notu **{debt.rating}**",
        "- Yöntem: SQALE (SonarQube'un kullandığı model); düzeltme süreleri, kodu yazma maliyetine (satır başına 30 dk) oranlanır. "
        "A ≤ %5, B ≤ %10, C ≤ %20, D ≤ %50, E > %50.",
        "",
    ]
    if result.hotspots:
        out += ["| Dosya | Risk | Bulgu | Bilişsel yük | Satır | Neden |", "|---|---:|---:|---:|---:|---|"]
        out += [f"| `{h.file}` | {h.risk} | {h.issues} | {h.cognitive} | {h.lines} | {', '.join(h.reasons)} |" for h in result.hotspots]
        out.append("")
    return out


def _architecture_lines(result: AnalysisResult) -> list[str]:
    graph = result.imports
    out = ["## Modül Bağımlılıkları", "",
           f"- {len(graph.modules)} modül, {len(graph.edges)} import ilişkisi "
           f"({sum(e.lazy for e in graph.edges)} tanesi fonksiyon içinde, tembel).",
           f"- Döngüsel import: **{len(graph.cycles)}**"]
    out += [f"  - `{' → '.join(cycle)}`" for cycle in graph.cycles[:5]]
    busiest = [m for m in graph.modules if m.fan_in + m.fan_out][:5]
    if busiest:
        out += ["", "| Modül | Ca (kullanan) | Ce (kullandığı) | Kararsızlık |", "|---|---:|---:|---:|"]
        out += [f"| `{m.name}` | {m.fan_in} | {m.fan_out} | {m.instability:.2f} |" for m in busiest]
    return out + [""]


def _dependency_lines(result: AnalysisResult) -> list[str]:
    deps = result.dependencies
    out = [f"- Bağımlılık açıkları (OSV.dev): {coverage_text(deps)}"]
    if not deps.vulnerable:
        return out
    out += ["", "| Paket | Sürüm | Açık | En yüksek ciddiyet | Güvenli sürüm | Kayıtlar |", "|---|---|---:|---|---|---|"]
    for pkg in deps.vulnerable:
        links = ", ".join(f"[{v.id}]({v.url})" for v in pkg.vulnerabilities[:4])
        more = f" +{len(pkg.vulnerabilities) - 4}" if len(pkg.vulnerabilities) > 4 else ""
        out.append(
            f"| `{pkg.name}` | {pkg.version} | {len(pkg.vulnerabilities)} | {SEVERITY_LABELS[pkg.severity]} "
            f"| {pkg.fixed_version or 'henüz yok'} | {links}{more} |"
        )
    return out


def _security_and_tests_section(result: AnalysisResult) -> list[str]:
    s, t = result.security, result.tests
    bandit = f"çalıştı, {s.bandit_issues} ek bulgu" if s.bandit_ran else "çalıştırılmadı"
    return [
        "## Güvenlik", "",
        f"- Olası gizli anahtar: **{s.secrets_found}**",
        f"- Riskli fonksiyon çağrısı: **{s.dangerous_calls}**",
        f"- Bandit: {bandit}",
        f"- .gitignore: {'var' if s.has_gitignore else 'yok'} · .env kapsanıyor: {_yes_no(s.gitignore_covers_env)}",
        *_flow_lines(result),
        *_dependency_lines(result),
        "",
        "## Testler", "",
        f"- Durum: **{t.status}** · test dosyası: {len(t.test_files)} · test fonksiyonu: {t.test_functions}",
        f"- Test aracı: {', '.join(t.frameworks) or 'bulunamadı'} · CI'da test: {_yes_no(t.ci_runs_tests)}",
        *_reach_lines(result),
        "",
    ]


def _reach_lines(result: AnalysisResult) -> list[str]:
    usage = result.usage
    if usage.test_reach is None:
        return []
    out = [f"- Statik test erişimi: **{_percent(usage.test_reach)}** ({usage.test_reached}/{usage.test_total} fonksiyona "
           "testlerden bir çağrı zinciriyle ulaşılıyor)"]
    if usage.untested:
        more = f" +{len(usage.untested) - 10}" if len(usage.untested) > 10 else ""
        out.append("  - Hiçbir testin ulaşmadığı: " + ", ".join(f"`{u.name}`" for u in usage.untested[:10]) + more)
    return out


def _readme_and_architecture_section(result: AnalysisResult) -> list[str]:
    checks, ai = result.documentation.checks, _ai(result)
    out = ["## README Kontrol Listesi", ""]
    out += [f"- [{'x' if checks.get(k) else ' '}] {label}" for k, label in CHECK_NAMES.items()]
    out += _command_lines(result)
    if ai and ai.readme_suggestions:
        out += ["", "**README önerileri (yapay zekâ):**", ""] + [f"- {x}" for x in ai.readme_suggestions]
    out.append("")
    out += _architecture_lines(result)
    if ai and ai.architecture_review:
        out += ["## Mimari Değerlendirme", "", ai.architecture_review, ""]
        out += [ai.readability_review, ""] if ai.readability_review else []
    return out


def _command_lines(result: AnalysisResult) -> list[str]:
    d = result.documentation
    if not d.commands_checked:
        return []
    out = ["", f"- README komutları: {d.commands_checked} komut kontrol edildi, **{len(d.broken_commands)}** tanesi çalışmaz"]
    return out + [f"  - `{b.command}` (satır {b.line}): {b.problem}" for b in d.broken_commands[:10]]


def _fixes_section(result: AnalysisResult) -> list[str]:
    fixes = result.fixes
    if not fixes.files:
        return []
    out = ["## Otomatik Düzeltmeler", "",
           f"{fixes.change_count} güvenli değişiklik hazır. `repomentor-fixes.patch` dosyasını (uygulamadaki \"Raporu indir\" menüsü "
           "veya CLI'da `--fix-patch`) inceleyip proje klasöründe `git apply repomentor-fixes.patch` ile uygulayın.", ""]
    for fix in fixes.files:
        out.append(f"- `{fix.path}`" + (" (yeni dosya)" if fix.new_file else ""))
        out += [f"  - {change}" for change in fix.changes]
    return out + [""]


def _roadmap_section(result: AnalysisResult) -> list[str]:
    out = ["## Öncelikli Yol Haritası", ""]
    for phase in result.roadmap:
        total = sum(step.effort_minutes for step in phase.steps)
        out += [f"### {phase.label} (toplam ~{format_effort(total)})", ""]
        out += [f"- [ ] {step.title} _({format_effort(step.effort_minutes)})_" for step in phase.steps[:10]]
        out.append("")
    ai = _ai(result)
    if ai and ai.next_steps:
        out += ["**Yapay zekânın önerdiği sonraki adımlar:**", ""]
        out += [f"{n}. {x}" for n, x in enumerate(ai.next_steps, 1)] + [""]
    return out


def _career_and_footer(result: AnalysisResult) -> list[str]:
    c = result.career
    out = ["## CV ve LinkedIn", "", "### CV maddeleri", ""] + [f"- {b}" for b in c.cv_bullets]
    out += ["", "### LinkedIn proje açıklaması", "", c.linkedin_short, "", "### LinkedIn gönderisi", "", c.linkedin_post, ""]
    if result.warnings:
        out += ["## Uyarılar", ""] + [f"- {w}" for w in result.warnings] + [""]
    out += [
        "<details><summary>Dosya ağacı</summary>", "",
        "```", render_tree([f.path for f in result.files]), "```", "",
        "</details>", "",
        "---",
        f"_{APP_NAME} v{result.version} ile oluşturuldu. {DISCLAIMER}_",
    ]
    return out


def build_markdown(result: AnalysisResult) -> str:
    sections = (
        _header, _score_section, _debt_section, _issues_section, _quality_section,
        _security_and_tests_section, _readme_and_architecture_section, _roadmap_section, _fixes_section, _career_and_footer,
    )
    return "\n".join(line for section in sections for line in section(result))


def build_json(result: AnalysisResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str)


def build_csv(result: AnalysisResult) -> str:
    """One row per finding, including project identity and all category scores.

    A report without findings still has one project row. AI suggestions carry
    their own source label and never change the deterministic scores.
    """
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow([
        "Proje", "Analiz tarihi", "Proje kaynağı", "Genel skor (0-100)", "Değerlendirme",
        *[f"{c.label} (0-100)" for c in result.score.categories],
        "Kural", "Öncelik", "Kategori", "Başlık", "Konumlar", "Neden önemli",
        "Çözüm önerisi", "Tahmini süre (dakika)", "Bulgu kaynağı", "Güven düzeyi", "Konum sayısı",
    ])
    project = [
        result.project.name, result.analyzed_at, result.project.source_url or result.project.source,
        result.score.overall, result.score.band, *[c.score for c in result.score.categories],
    ]
    ai = _ai(result)
    issues = [*result.issues, *(ai.extra_issues if ai else [])]
    for issue in issues or [None]:
        finding = [
            issue.rule_id, SEVERITY_LABELS[issue.severity], CATEGORY_LABELS.get(issue.category, issue.category),
            issue.title, "; ".join(str(loc) for loc in issue.locations), issue.explanation,
            issue.recommendation, issue.effort_minutes, issue.source, issue.confidence,
            max(issue.count, len(issue.locations)),
        ] if issue else ["", "", "", "Bulgu tespit edilmedi", "", "", "", "", "", "", ""]
        writer.writerow([safe_csv_cell(mask_secrets(str(value))) for value in [*project, *finding]])
    # UTF-8 BOM lets spreadsheet applications detect Turkish characters correctly.
    return "\ufeff" + stream.getvalue()
