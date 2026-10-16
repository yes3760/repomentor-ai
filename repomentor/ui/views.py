"""One render function per results tab."""

from __future__ import annotations

from datetime import datetime
from math import ceil
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from repomentor.analyzer.comparison import compare_reports
from repomentor.analyzer.dependency_analyzer import coverage_text
from repomentor.analyzer.file_tree import render_tree
from repomentor.analyzer.finding_query import filter_findings, findings_csv
from repomentor.analyzer.readme_template import build_readme
from repomentor.analyzer.report_builder import CHECK_NAMES, DISCLAIMER, build_csv, build_json, build_markdown
from repomentor.models.analysis_result import AnalysisResult
from repomentor.models.issue import SEVERITY_LABELS, format_effort
from repomentor.ui import charts
from repomentor.ui.branding import logo_html
from repomentor.ui.components import (
    CATEGORY_NAMES,
    category_meters,
    checklist,
    code_composition_card,
    esc,
    facts,
    issue_list,
    safe_md,
    score_factors_grid,
    score_hero,
    severity_summary,
    strengths_card,
    tile,
)
from repomentor.ui.engine_views import (
    patch_download,
    render_code_health,
    render_data_science,
    render_fixes,
    render_readme_commands,
    render_test_reach,
)
from repomentor.ui.insight_views import render_clones, render_debt_and_hotspots, render_import_graph, render_taint_flows
from repomentor.ui.session import new_analysis, report_key, save_step
from repomentor.ui.visual_views import render_badge, render_code_map, render_flow_paths
from repomentor.utils.text_utils import share_percent, tr_number


def _ai_ok(r: AnalysisResult) -> bool:
    return r.ai is not None and r.ai.ok


def _tiles(values: list[tuple[str, object, str]]) -> None:
    for column, (label, value, note) in zip(st.columns(len(values)), values, strict=True):
        with column:
            tile(label, value, note)


def _yes_no(value: bool) -> str:
    return "Var" if value else "Yok"


# --- Overview -------------------------------------------------------------------------

def _why_score(r: AnalysisResult) -> None:
    with st.expander("Bu puanlar nasıl hesaplandı?", icon=":material/calculate:"):
        st.caption(DISCLAIMER)
        score_factors_grid(r.score.categories)


def _filtered_issues(r: AnalysisResult) -> None:
    st.markdown("#### Bulgular")
    severity_summary(r.issues)
    prefix = f"findings-{report_key()}"
    query = st.text_input("Bulgularda ara", placeholder="Dosya, kural veya bir anahtar kelime…", key=f"{prefix}-query", icon=":material/search:")
    left, middle, right = st.columns([2, 2, 1.6])
    severities = left.multiselect("Öncelik", list(SEVERITY_LABELS), format_func=SEVERITY_LABELS.get,
                                 placeholder="Tüm öncelikler", key=f"{prefix}-severity")
    categories = middle.multiselect("Kategori", list(CATEGORY_NAMES), format_func=CATEGORY_NAMES.get,
                                    placeholder="Tüm kategoriler", key=f"{prefix}-category")
    sort = right.selectbox("Sıralama", ["priority", "effort", "file"],
                           format_func={"priority": "Önce kritik olanlar", "effort": "Önce hızlı çözümler", "file": "Dosyaya göre"}.get,
                           key=f"{prefix}-sort")
    shown = filter_findings(r.issues, query, severities or None, categories or None, sort)
    st.caption(f"{len(shown)} / {len(r.issues)} bulgu · Bir bulgu birden fazla konum içerebilir.")
    if not shown:
        if r.issues:
            st.info("Bu filtrelerle eşleşen bulgu yok. Aramayı veya filtreleri değiştir.", icon=":material/search_off:")
        else:
            st.success("Bu analizin kurallarıyla bulgu tespit edilmedi.")
        return
    signature = (query, tuple(severities), tuple(categories), sort)
    if st.session_state.get(f"{prefix}-signature") != signature:
        st.session_state[f"{prefix}-page"] = 1
        st.session_state[f"{prefix}-signature"] = signature
    pages = ceil(len(shown) / 10)
    page = st.selectbox("Sayfa", list(range(1, pages + 1)),
                        format_func=lambda n: f"{n} / {pages}", key=f"{prefix}-page") if pages > 1 else 1
    st.download_button("Filtrelenen bulguları CSV indir", findings_csv(shown), "repomentor-bulgular.csv", "text/csv",
                       icon=":material/download:", key=f"{prefix}-csv")
    issue_list(shown[(page - 1) * 10:page * 10], "all")


def _ai_text(r: AnalysisResult, field_name: str, fallback):
    """AI value for `field_name` when the AI call succeeded and returned one, else the rule-based fallback."""
    value = getattr(r.ai, field_name, None) if _ai_ok(r) else None
    return value or fallback


def _overview_tiles(r: AnalysisResult) -> None:
    serious = sum(1 for i in r.issues if i.category == "security" and i.severity in {"critical", "high"})
    values = [
        ("Dosya", len(r.files), f"{r.quality.python_files} Python dosyası", "📂"),
        ("Kod satırı", tr_number(r.quality.sloc), f"{r.quality.functions} fonksiyon", "⌘"),
        ("Güvenlik", serious, "kritik / yüksek bulgu", "🛡"),
        ("Testler", r.tests.status, f"{r.tests.test_functions} test fonksiyonu", "🧪"),
    ]
    st.html('<div class="rm-stat-grid">' + "".join(
        f'<div class="rm-stat"><div><span class="rm-label">{esc(label)}</span>'
        f'<b>{esc(value)}</b><small>{esc(note)}</small></div>'
        f'<span class="rm-stat-icon" aria-hidden="true">{icon}</span></div>'
        for label, value, note, icon in values
    ) + '</div>')


def _identity_and_strengths(r: AnalysisResult) -> None:
    p = r.project
    st.markdown("#### Proje bilgileri")
    rows = [
        ("Tür", p.project_type),
        ("Framework", ", ".join(p.frameworks) or "-"),
        ("Veri tabanı", ", ".join(p.databases) or "-"),
        ("Test aracı", ", ".join(p.test_tools) or "Bulunamadı"),
        ("Giriş noktası", ", ".join(p.entry_points) or "Bulunamadı"),
        ("Docker / CI", f"Docker: {_yes_no(p.has_docker)} · CI: {_yes_no(p.has_ci)}"),
    ]
    if p.github:
        gh_stats = f"⭐ {p.github.get('stars', 0)} · 🍴 {p.github.get('forks', 0)} · 🐛 {p.github.get('open_issues', 0)} açık konu"
        rows.append(("GitHub", gh_stats))
    facts(rows)
    st.markdown("##### Olumlu tespitler")
    strengths_card(r.strengths[:6])
    ai_only = [s for s in _ai_text(r, "strengths", []) if s not in r.strengths]
    if ai_only:
        with st.expander("Yapay zekânın ek değerlendirmesi"):
            strengths_card(ai_only)


def render_overview(r: AnalysisResult) -> None:
    with st.container(border=True, key="score-overview"):
        left, right = st.columns([1, 1.65], gap="large")
        with left:
            score_hero(r.score, r.issues)
        with right:
            category_meters(r.score.categories)
    _why_score(r)
    _overview_tiles(r)
    render_debt_and_hotspots(r)
    render_code_map(r)
    findings, context = st.columns([1.65, 1], gap="large")
    with findings:
        st.markdown("#### Öncelikli bulgular")
        st.caption(f"{len(r.issues)} bulgunun ilk {min(3, len(r.issues))} tanesi · Tümü Bulgular bölümünde")
        issue_list(r.issues[:3], "top")
    with context:
        _identity_and_strengths(r)
    with st.expander("Analiz özeti", icon=":material/summarize:"):
        st.markdown(safe_md(r.summary))
    if ai_summary := _ai_text(r, "summary", None):
        with st.container(border=True):
            st.caption(f"Yapay zekâ yorumu · {r.ai.model}")
            st.markdown(safe_md(ai_summary))


# --- Quality ----------------------------------------------------------------------------

def _function_table(rows, sort_label: str) -> None:
    df = pd.DataFrame([{"Fonksiyon": f.name, "Dosya": f"{f.file}:{f.line}", "Bilişsel": f.cognitive, "Döngüsel": f.complexity,
                        "Satır": f.length, "Parametre": f.params} for f in rows])
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        sort_label: st.column_config.ProgressColumn(sort_label, format="%d", min_value=0, max_value=int(df[sort_label].max() or 1)),
    })


def render_quality(r: AnalysisResult) -> None:
    q = r.quality
    if not q.python_files:
        st.info("Projede Python dosyası bulunamadı; kod kalitesi analizi yapılamadı.")
        return
    mi = tr_number(q.avg_maintainability)
    hints = f"%{q.type_hint_coverage * 100:.0f}" if q.type_hint_coverage is not None else "-"
    _tiles([
        ("Ort. bilişsel", tr_number(q.avg_cognitive, 1), f"okuma zorluğu · {q.hard_functions + q.very_hard_functions} fonksiyon eşik üstü"),
        ("Ort. döngüsel", tr_number(q.avg_complexity, 2), "fonksiyon başına karar yolu"),
        ("Maintainability", mi, "Radon MI (0-100, yüksek iyi)"),
        ("Tip ipucu", hints, f"{q.annotated}/{q.annotatable} parametre ve dönüş"),
        ("Tekrar / kopya", f"{len(q.duplicates)} / {len(q.clones)}", "satır bazlı / yapısal"),
    ])
    code_composition_card(q)
    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("##### Karmaşıklık dağılımı")
        st.altair_chart(charts.complexity_chart(q.complexity_distribution), width="stretch")
        st.caption("Bantlar bu aracın basit değerlendirme ölçeğidir: 1-5 düşük, 6-10 orta, 11-20 yüksek, 21+ refactor önerilir.")
    with right:
        st.markdown("##### En zor fonksiyonlar")
        st.caption("Bilişsel: okuma zorluğu (15 üstü zor) · Döngüsel: test edilecek yol sayısı (11 üstü yüksek)")
        if q.most_complex:
            _function_table(q.most_complex[:8], "Bilişsel")
        st.markdown("##### En uzun fonksiyonlar")
        if q.longest_functions:
            _function_table(q.longest_functions[:5], "Satır")

    with st.expander(f"Dosya bazında Maintainability Index ({len(q.maintainability)} dosya)"):
        st.dataframe(pd.DataFrame(q.maintainability).rename(columns={"file": "Dosya", "mi": "MI", "rank": "Sınıf", "lines": "Satır"}), hide_index=True, width="stretch")
        st.caption("Radon sınıfları: A (20-100) kolay bakım, B (10-19) orta, C (0-9) zor.")
    if q.ruff_by_code:
        with st.expander(f"Ruff lint özeti ({q.ruff_total} uyarı)"):
            st.dataframe(pd.DataFrame([{"Kural": c, "Adet": v["count"], "Mesaj": v["message"], "Örnek": v["sample"]} for c, v in q.ruff_by_code.items()]), hide_index=True, width="stretch")
    if q.duplicates:
        with st.expander(f"Tekrarlanan kod blokları ({len(q.duplicates)})"):
            for block in q.duplicates:
                st.markdown(f"**~{block.lines} satır** · " + " ↔ ".join(f"`{o}`" for o in block.occurrences))
                st.code(block.preview, language="python")
    render_clones(q)
    render_code_health(r)
    render_data_science(r)
    st.markdown("#### Kalite bulguları")
    issue_list(r.issues_by_category("quality"), "quality")


# --- Security ---------------------------------------------------------------------------

def _dependency_table(r: AnalysisResult) -> None:
    deps = r.dependencies
    rows = [
        {
            "Paket": pkg.name, "Sürüm": pkg.version, "Ciddiyet": SEVERITY_LABELS[pkg.severity],
            "Açık": len(pkg.vulnerabilities), "Güvenli sürüm": pkg.fixed_version or "henüz yok",
            "İlk kayıt": pkg.vulnerabilities[0].url, "Dosya": f"{pkg.file}:{pkg.line}" if pkg.line else pkg.file,
        }
        for pkg in deps.vulnerable
    ]
    st.dataframe(
        pd.DataFrame(rows), hide_index=True,
        column_config={
            "Açık": st.column_config.NumberColumn(format="%d"),
            "İlk kayıt": st.column_config.LinkColumn(display_text=r"https://osv\.dev/vulnerability/(.+)"),
        },
        alt="Bilinen güvenlik açığı içeren bağımlılıklar ve güvenli sürümleri",
    )
    with st.expander(f"Tüm kayıtlar ({deps.vulnerability_count})", icon=":material/list:"):
        for pkg in deps.vulnerable:
            st.markdown(f"**`{pkg.name}=={pkg.version}`**")
            st.markdown("\n".join(
                f"- [{v.id}]({v.url}) · {SEVERITY_LABELS[v.severity]}"
                f"{' · ' + v.cve if v.cve else ''} · düzeltme: `{v.fixed or 'yok'}` — {safe_md(v.summary)}"
                for v in pkg.vulnerabilities
            ))


def _dependency_section(r: AnalysisResult) -> None:
    deps = r.dependencies
    st.markdown("##### Bağımlılık açıkları")
    st.caption(f"OSV.dev · {coverage_text(deps)}")
    if not deps.enabled:
        st.info("Bağımlılık taraması bu analizde kapalıydı. Yan menüden açıp yeniden analiz edebilirsiniz.", icon=":material/info:")
    elif deps.error:
        st.warning(f"Tarama yapılamadı: {deps.error}", icon=":material/cloud_off:")
    elif deps.vulnerable:
        _dependency_table(r)
    elif deps.checked:
        st.success("Sürümü sabitlenmiş paketlerde bilinen açık bulunmadı.", icon=":material/verified_user:")
    if deps.unpinned:
        st.caption("Sürümü sabitlenmediği için kontrol edilemeyenler: " + ", ".join(f"`{name}`" for name in deps.unpinned[:12])
                   + (" …" if len(deps.unpinned) > 12 else "") + ". Kilit dosyası (`uv lock`, `poetry lock`) veya `==` sürümleri ekleyin.")


def render_security(r: AnalysisResult) -> None:
    s, deps = r.security, r.dependencies
    dep_value = deps.vulnerability_count if deps.ran else "-"
    dep_note = f"{len(deps.vulnerable)} pakette" if deps.ran else ("kapalı" if not deps.enabled else "kontrol edilemedi")
    _tiles([
        ("Doğrulanmış akış", len(s.taint_flows), "girdi → tehlikeli çağrı"),
        ("Olası gizli anahtar", s.secrets_found, "kodda / yapılandırmada"),
        ("Riskli çağrı", s.dangerous_calls, "eval, shell, SQL, pickle…"),
        ("Bağımlılık açığı", dep_value, dep_note),
        ("Bandit", s.bandit_issues if s.bandit_ran else "-", "ek bulgu" if s.bandit_ran else (s.bandit_error or "çalıştırılmadı")),
        (".env koruması", "Var" if s.gitignore_covers_env else "Yok", ".gitignore içinde .env"),
    ])
    st.markdown("##### Güvenlik kontrol listesi")
    checklist([
        (".gitignore dosyası mevcut", s.has_gitignore),
        (".env ortam dosyaları .gitignore ile hariç tutulmuş", s.gitignore_covers_env),
        ("Depoda takip edilen açık .env dosyası bulunmuyor", not s.env_committed),
        ("Kod içinde sabitlenmiş gizli anahtar / parola tespit edilmedi", s.secrets_found == 0),
        ("Yüksek riskli çağrı (eval, exec, shell=True, pickle) tespit edilmedi", s.dangerous_calls == 0),
        ("Sabitlenmiş bağımlılıklarda bilinen açık yok (OSV.dev)", deps.ran and not deps.vulnerable),
        ("Kullanıcı girdisi tehlikeli bir çağrıya ulaşmıyor (veri akışı)", not s.taint_flows),
    ])
    render_taint_flows(r)
    render_flow_paths(r)
    _dependency_section(r)
    if s.env_committed:
        st.warning("Depoda takip edilen ortam dosyaları: " + ", ".join(f"`{p}`" for p in s.env_committed))
    st.info(
        "Bu bulgular **potansiyel risk** olarak işaretlenmiştir; kesin güvenlik açığı anlamına gelmez. "
        "Örneğin `eval()` yalnızca kullanıcı girdisi ulaşabiliyorsa tehlikelidir. Raporlarda anahtar değerleri maskelenir.",
        icon="ℹ️",
    )
    issue_list(r.issues_by_category("security"), "security", "Bu kontrollerde güvenlik bulgusu tespit edilmedi. Bu, projenin açık içermediği anlamına gelmez.")


# --- Tests -------------------------------------------------------------------------------

def render_tests(r: AnalysisResult) -> None:
    t = r.tests
    _tiles([
        ("Durum", t.status, "bu aracın ölçeğine göre"),
        ("Test dosyası", len(t.test_files), ", ".join(t.frameworks) or "test aracı yok"),
        ("Test fonksiyonu", t.test_functions, f"{t.source_functions} public fonksiyona karşı"),
        ("Test / fonksiyon", tr_number(round(t.ratio, 2), 2), "0,3 ve üzeri iyi bir başlangıç"),
        ("Statik erişim", "-" if r.usage.test_reach is None else f"%{share_percent(r.usage.test_reach)}", "testlerin ulaştığı fonksiyonlar"),
    ])
    checklist([
        ("Testler CI'da (ör. GitHub Actions) otomatik çalışıyor", t.ci_runs_tests),
        ("pytest yapılandırması (conftest.py)", t.has_conftest),
        ("Kapsam (coverage) ayarı", t.has_coverage_config),
    ])
    if t.ci_files:
        st.caption("Tespit edilen CI iş akışı dosyaları: " + ", ".join(f"`{p}`" for p in t.ci_files))
    render_test_reach(r)
    if t.test_files:
        with st.expander(f"Test dosyaları ({len(t.test_files)})"):
            st.markdown("\n".join(f"- `{p}`" for p in t.test_files))
    issue_list(r.issues_by_category("testing"), "testing")


# --- README ------------------------------------------------------------------------------

def render_readme(r: AnalysisResult) -> None:
    d = r.documentation
    coverage = f"%{d.docstring_coverage * 100:.0f}" if d.docstring_coverage is not None else "-"
    _tiles([
        ("README", d.readme_path or "Yok", f"{d.readme_words} kelime"),
        ("Lisans", d.license_file or "Yok", "LICENSE dosyası"),
        (".env.example", _yes_no(d.has_env_example), "ortam değişkeni şablonu"),
        ("Docstring kapsamı", coverage, f"{d.documented_symbols}/{d.documentable_symbols} public sembol"),
    ])
    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("##### README kontrol listesi")
        checklist([(label, bool(d.checks.get(key))) for key, label in CHECK_NAMES.items()])
        st.markdown("##### Proje standartları ve belgeler")
        checklist([
            ("Lisans dosyası (LICENSE)", bool(d.license_file)),
            ("Ortam değişkeni şablonu (.env.example)", d.has_env_example),
            ("Katkı rehberi (CONTRIBUTING.md)", d.has_contributing),
            ("Sürüm geçmişi (CHANGELOG.md)", d.has_changelog),
        ])
    with right:
        st.markdown("##### Hazır README taslağı")
        st.caption("Tespit edilen teknolojiler, kurulum ve çalıştırma komutlarıyla doldurulmuş bir başlangıç şablonu.")
        readme = build_readme(r)
        st.download_button("README.md taslağını indir", readme, file_name="README.md", mime="text/markdown", icon="📝")
        with st.expander("Önizleme"):
            st.code(readme, language="markdown")
    render_readme_commands(r)
    if _ai_ok(r) and r.ai.readme_suggestions:
        st.markdown("##### Yapay zekâ önerileri")
        st.markdown("\n".join(f"- {safe_md(x)}" for x in r.ai.readme_suggestions))
    issue_list(r.issues_by_category("documentation"), "docs")


# --- Architecture -------------------------------------------------------------------------

def _structure_facts(r: AnalysisResult) -> None:
    p = r.project
    github = f"⭐ {p.github.get('stars', 0)} · {p.github.get('license') or 'lisans yok'}" if p.github else "-"
    rows = [
        ("Proje türü", p.project_type),
        ("Ana dil", p.primary_language or "-"),
        ("Python sürümü", p.python_version or "Belirtilmemiş"),
        ("Giriş noktası", ", ".join(p.entry_points) or "Bulunamadı"),
        ("Bağımlılık dosyası", ", ".join(p.dependency_files) or "Yok"),
        ("ML / veri", ", ".join(p.ml_libraries) or "-"),
        ("GitHub", github),
    ]
    if p.github and p.github.get("topics"):
        rows.append(("Konular (Topics)", ", ".join(p.github["topics"][:8])))
    facts(rows)


def _ai_review(r: AnalysisResult) -> None:
    if r.ai is None:
        st.info("Mimari yorum için yan menüden ücretsiz bir yapay zekâ sağlayıcısı seçin (ör. Ollama).", icon="🤖")
        return
    if not _ai_ok(r):
        return
    st.markdown("##### Mimari değerlendirme (yapay zekâ)")
    if not r.ai.architecture_review:
        st.caption("Model bu analizde mimari yorum döndürmedi. Daha büyük bir model (ör. `qwen2.5-coder:7b`) veya Groq daha ayrıntılı sonuç verir.")
        return
    st.markdown(safe_md(r.ai.architecture_review))
    if r.ai.readability_review:
        st.markdown("##### Okunabilirlik")
        st.markdown(safe_md(r.ai.readability_review))


def _ai_extra_issues(r: AnalysisResult) -> None:
    if _ai_ok(r) and r.ai.extra_issues:
        st.markdown("#### Yapay zekânın önerdiği ek konular")
        st.caption("Bunlar modelin yorumudur ve skora dahil edilmez; uygulamadan önce doğrulayın.")
        issue_list(r.ai.extra_issues, "ai")


def render_architecture(r: AnalysisResult) -> None:
    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("##### Tespit edilen yapı")
        _structure_facts(r)
    with right:
        st.markdown("##### Dil dağılımı (satır)")
        if r.project.languages:
            st.altair_chart(charts.language_chart(r.project.languages), width="stretch")
    render_import_graph(r)
    _ai_review(r)
    with st.expander(f"Dosya gezgini ({len(r.files)} dosya)", icon=":material/folder_open:"):
        query = st.text_input("Dosya ara", placeholder="Örn. app/ veya .py", key=f"files-{report_key()}-query")
        files = [f for f in r.files if query.casefold() in f.path.casefold()]
        st.caption(f"{len(files)} / {len(r.files)} dosya · Tam proje kaynak kodu rapor geçmişinde tutulmaz.")
        if files:
            st.dataframe(pd.DataFrame([{
                "Dosya": f.path, "Dil": f.language or "Diğer", "Satır": f.lines,
                "Boyut (KB)": round(f.size / 1024, 2),
                "Durum": f.skipped_reason or ("Okundu" if f.lines else "İçerik metriği yok"),
            } for f in files]), hide_index=True, width="stretch")
            st.code(render_tree([f.path for f in files]), language=None)
        else:
            st.info("Aramayla eşleşen dosya yok.")
    if r.project.dependencies:
        with st.expander(f"Bağımlılıklar ({len(r.project.dependencies)})"):
            st.markdown(", ".join(f"`{d}`" for d in r.project.dependencies))
    _ai_extra_issues(r)
    st.markdown("#### Organizasyon ve çalıştırılabilirlik bulguları")
    issue_list([i for i in r.issues if i.category in {"organization", "runnable"}], "org")


# --- Roadmap -------------------------------------------------------------------------------

def render_roadmap(r: AnalysisResult) -> None:
    render_fixes(r)
    if not r.roadmap:
        st.success("Yol haritasına eklenecek bir iş yok.")
    report_id = report_key()
    completed = st.session_state.get("completed_steps", {}).get(report_id, set())
    done = total = done_minutes = total_minutes = 0
    export = [f"# {r.project.name} — geliştirme planı", "", "İşaretler görev takibi içindir; analiz skorunu değiştirmez.", ""]
    for phase_index, phase in enumerate(r.roadmap):
        minutes = sum(s.effort_minutes for s in phase.steps)
        total_minutes += minutes
        st.html(
            f"<div class='rm-phase-card'><h3>{esc(phase.label)}</h3>"
            f"<span class='rm-phase-time'>⏱ toplam ~{esc(format_effort(minutes))}</span></div>"
        )
        export += [f"## {phase.label}", ""]
        for step_index, step in enumerate(phase.steps):
            step_id = f"{phase.key}:{step_index}:{step.rule_id}:{step.file}"
            widget_key = f"roadmap-{report_id}-{phase_index}-{step_index}"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = step_id in completed
            label = f"{SEVERITY_LABELS[step.severity]} · {step.title} ({format_effort(step.effort_minutes)})"
            checked = st.checkbox(safe_md(label), key=widget_key, on_change=save_step, args=(report_id, step_id, widget_key))
            done += checked
            total += 1
            if checked:
                done_minutes += step.effort_minutes
            export.append(f"- [{'x' if checked else ' '}] {step.title} (~{format_effort(step.effort_minutes)})")
            if step.file:
                st.caption(f"↳ {step.file}")
        export.append("")
    if total:
        remaining = max(0, total_minutes - done_minutes)
        st.progress(done / total, text=f"İlerleme: {done}/{total} adım tamamlandı · Kalan tahmini süre: ~{format_effort(remaining)}")
        st.caption("Görevler bu rapora özel ve yalnızca bu oturumda saklanır. Tamamlandı işareti skoru değiştirmez; sonucu görmek için projeyi yeniden analiz et.")
        st.download_button("İşaretlediğim planı indir", "\n".join(export), "repomentor-yol-haritasi.md", "text/markdown",
                           icon=":material/checklist:")
    if _ai_ok(r) and r.ai.next_steps:
        st.markdown("#### Yapay zekânın önerdiği sonraki adımlar")
        st.markdown("\n".join(f"{n}. {safe_md(x)}" for n, x in enumerate(r.ai.next_steps, 1)))


# --- Career --------------------------------------------------------------------------------

def render_career(r: AnalysisResult) -> None:
    c = r.career
    source = f"yapay zekâ ({r.ai.model})" if c.source == "ai" and r.ai else "şablon (yalnızca tespit edilen teknolojiler kullanıldı)"
    st.caption(f"Kaynak: {source}. Kendi katkınıza göre düzenleyin; yapmadığınız bir şeyi yazmayın.")
    st.markdown("##### CV maddeleri")
    st.code("\n".join(f"• {b}" for b in c.cv_bullets), language=None, wrap_lines=True)
    st.markdown("##### LinkedIn – proje açıklaması")
    st.code(c.linkedin_short, language=None, wrap_lines=True)
    st.markdown("##### LinkedIn – gönderi")
    st.code(c.linkedin_post, language=None, wrap_lines=True)
    st.caption("Kod kutularının sağ üstündeki simgeyle tek tıkla kopyalayabilirsiniz.")
    render_badge(r)


# --- Downloads ------------------------------------------------------------------------------

def render_downloads(r: AnalysisResult) -> None:
    slug = "".join(ch if ch.isalnum() else "-" for ch in r.project.name.lower()).strip("-") or "proje"
    st.download_button("Markdown raporu", build_markdown(r), file_name=f"repomentor-{slug}.md", mime="text/markdown", icon=":material/description:", type="primary", width="stretch")
    st.download_button("CSV raporu", build_csv(r), file_name=f"repomentor-{slug}.csv", mime="text/csv; charset=utf-8", icon=":material/table_view:", width="stretch")
    st.download_button("JSON raporu", build_json(r), file_name=f"repomentor-{slug}.json", mime="application/json", icon=":material/data_object:", width="stretch")
    st.download_button("README taslağı", build_readme(r), file_name="README.md", mime="text/markdown", icon=":material/article:", width="stretch")
    if r.fixes.files:
        patch_download(r, "downloads", width="stretch")


def _report_label(report: AnalysisResult) -> str:
    date = datetime.fromisoformat(report.analyzed_at).astimezone(ZoneInfo("Europe/Istanbul"))
    return f"{report.project.name} · {report.score.overall}/100 · {date:%H:%M:%S}"


def render_comparison(r: AnalysisResult) -> None:
    st.markdown("#### Gelişimini ölç")
    st.caption("Önceki raporu seç; skor ve bulguların nasıl değiştiğini gör.")
    history = st.session_state.get("history", {})
    options = [key for key in reversed(history) if key != report_key()]
    if not options:
        st.info("Karşılaştırma için ikinci bir analiz gerekli. Projeni geliştirdikten sonra yeniden analiz et veya başka bir örneği dene.", icon=":material/compare_arrows:")
        st.button("Yeni analiz başlat", on_click=new_analysis, icon=":material/add:")
        return
    selected = st.selectbox("Referans rapor", options, format_func=lambda key: _report_label(history[key]),
                            key=f"compare-{report_key()}")
    previous = history[selected]
    comparison = compare_reports(previous, r)
    if not comparison.same_project:
        st.warning("Farklı projeleri karşılaştırıyorsun. Bu farklar tek bir projenin gelişimini göstermez.")
    if previous.version != r.version:
        st.warning("Raporlar farklı RepoMentor sürümleriyle üretilmiş; ölçüm kuralları değişmiş olabilir.")
    score, added, resolved = st.columns(3)
    score.metric("Genel skor", f"{r.score.overall}/100", f"{comparison.score_delta:+d} puan")
    added.metric("Yeni görünen bulgu", len(comparison.added))
    resolved.metric("Artık görünmeyen bulgu", len(comparison.resolved))
    st.dataframe(pd.DataFrame(comparison.categories), hide_index=True, width="stretch", column_config={
        "Önceki": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
        "Şimdiki": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
        "Fark": st.column_config.NumberColumn(format="%+d"),
    })
    st.caption(f"{comparison.unchanged} bulgu eşleşti. Eşleştirme kural ve dosyaya göredir; satır kaymaları yeni bulgu sayılmaz. "
               "Bulgu gruplarının sayısı karşılaştırılır; grup içindeki konum sayısı ve önem düzeyi değişiklikleri ayrıca incelenmelidir. "
               "Tarama kapsamı veya araç değişiklikleri de fark oluşturabilir.")
    left, right = st.columns(2)
    with left:
        st.markdown("##### Yeni görünenler")
        issue_list(comparison.added, "added", "Yeni görünen bulgu yok.")
    with right:
        st.markdown("##### Artık görünmeyenler")
        if comparison.resolved:
            with st.expander(f"{len(comparison.resolved)} bulguyu incele"):
                issue_list(comparison.resolved, "resolved")
        else:
            st.info("Artık görünmeyen bulgu yok.")


def render_technical(r: AnalysisResult) -> None:
    sections = [("Kod kalitesi", render_quality), ("Güvenlik", render_security), ("Testler", render_tests),
                ("README", render_readme), ("Mimari & dosyalar", render_architecture)]
    for tab, (_, render) in zip(st.tabs([name for name, _ in sections]), sections, strict=True):
        with tab:
            render(r)


TABS = (
    ("Genel bakış", render_overview),
    ("Bulgular", _filtered_issues),
    ("Teknik analiz", render_technical),
    ("Yol haritası", render_roadmap),
    ("Portföy", render_career),
    ("Karşılaştır", render_comparison),
)


def render_result(r: AnalysisResult) -> None:
    st.html(f'<div class="rm-mobile-brand">{logo_html()}</div>')
    st.html('''<div class="rm-topbar"><div class="rm-breadcrumb">İncelemeler <span>/</span> Analiz raporu</div>
      <span class="rm-top-meta">Statik inceleme raporu</span></div>''')
    title, actions = st.columns([3, 1], vertical_alignment="center")
    date = datetime.fromisoformat(r.analyzed_at).astimezone(ZoneInfo("Europe/Istanbul"))
    source = {"github": "GitHub", "zip": "ZIP arşivi", "demo": "Örnek proje", "local": "Yerel proje"}.get(r.project.source, r.project.source)
    with title:
        st.html(f'''<div class="rm-report-heading">
          <div class="rm-report-title-row">
            <h1>{esc(r.project.name)}</h1>
            <span class="rm-report-score-pill">{r.score.overall}/100 · {esc(r.score.band)}</span>
          </div>
          <div class="rm-report-meta">
            <span>📦 {esc(source)}</span>
            <span>🕒 {date:%d.%m.%Y %H:%M}</span>
            <span>⚡ {r.duration_seconds:g} sn</span>
            <span>🔎 {len(r.issues)} bulgu</span>
          </div></div>''')
    with actions:
        with st.popover("Raporu indir", icon=":material/download:", width="stretch"):
            render_downloads(r)
    st.html('<div class="rm-techline">' + "".join(f"<span>{esc(t)}</span>" for t in r.project.technologies[:8]) + '</div>')
    if r.warnings:
        with st.expander(f"Analiz notları · {len(r.warnings)}", icon=":material/info:", expanded=True):
            for warning in r.warnings:
                st.warning(warning)
    if _ai_ok(r):
        st.caption(f"Yapay zekâ yorumu: {r.ai.provider} / {r.ai.model} · {r.ai.duration_seconds:g} sn · Skora dahil edilmez.")
    selected = st.segmented_control("Rapor bölümü", [name for name, _ in TABS], default=TABS[0][0],
                                    key=f"report-section-{report_key()}", label_visibility="collapsed")
    render = dict(TABS).get(selected, render_overview)
    render(r)
