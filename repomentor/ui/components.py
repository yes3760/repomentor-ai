"""Reusable Streamlit building blocks.

Anything that came from the analysed repository or from the model is
untrusted: it is HTML-escaped before going into `st.html`, and markdown
images/links are stripped before going into `st.markdown`.
"""

from __future__ import annotations

import html
import re

import streamlit as st

from repomentor.models.analysis_result import CategoryScore, QualityReport, ScoreReport
from repomentor.models.issue import SEVERITY_LABELS, Issue, format_effort
from repomentor.ui.styles import SEVERITY_ICON, SEVERITY_STATUS, STATUS
from repomentor.utils.text_utils import tr_number

CATEGORY_NAMES = {
    "security": "Güvenlik",
    "quality": "Kod kalitesi",
    "testing": "Test",
    "documentation": "Dokümantasyon",
    "organization": "Organizasyon",
    "runnable": "Çalıştırılabilirlik",
}
SOURCE_NAMES = {"rule": "kural", "ast": "AST", "bandit": "Bandit", "ruff": "Ruff", "radon": "Radon", "taint": "veri akışı", "osv": "OSV.dev", "ai": "yapay zekâ"}
MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MD_LINK = re.compile(r"\[([^\]]+)\]\((?:https?:)?//[^)]*\)")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def safe_md(text: str) -> str:
    """Neutralise remote images and links in untrusted markdown (tracking pixels, phishing)."""
    text = MD_IMAGE.sub("", text or "")
    return MD_LINK.sub(r"\1", text)


def band_status(score: int) -> tuple[str, str]:
    if score >= 75:
        return STATUS["good"], "✔"
    if score >= 60:
        return STATUS["warning"], "!"
    return STATUS["critical"], "✖"


def _letter_grade(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"


def score_hero(score: ScoreReport, issues: list[Issue] | None = None) -> None:
    color, _ = band_status(score.overall)
    grade = _letter_grade(score.overall)
    circumference = 289.0
    offset = round(circumference * (1.0 - max(0, min(100, score.overall)) / 100.0), 2)
    ticks = "".join(f'<i><b style="width:{max(0, min(100, (score.overall - n * 10) * 10))}%"></b></i>' for n in range(10))
    effort_html = ""
    if issues is not None:
        if issues:
            quick = sum(1 for i in issues if i.effort_minutes <= 15)
            total_mins = sum(i.effort_minutes for i in issues)
            effort_html = (
                f'<div class="rm-effort-pills">'
                f'<span class="rm-effort-pill">⚡ {quick} hızlı çözüm (≤15 dk)</span>'
                f'<span class="rm-effort-pill">⏱ ~{esc(format_effort(total_mins))} toplam iş yükü</span>'
                f'</div>'
            )
        else:
            effort_html = '<div class="rm-effort-pills"><span class="rm-effort-pill">✔ Açık bulgu tespit edilmedi</span></div>'
    st.html(f"""
<div class="rm-card rm-score-card">
  <div class="rm-label">Genel skor</div>
  <div class="rm-score-gauge-wrap">
    <svg class="rm-gauge-svg" viewBox="0 0 112 112" aria-hidden="true">
      <circle class="rm-gauge-bg" cx="56" cy="56" r="46"></circle>
      <circle class="rm-gauge-fill" cx="56" cy="56" r="46" stroke="{color}"
        stroke-dasharray="{circumference}" stroke-dashoffset="{offset}"></circle>
    </svg>
    <div class="rm-score-meta-col">
      <div class="rm-score-value">{score.overall}<small>/ 100</small></div>
      <div class="rm-score-badges">
        <span class="rm-grade-pill">SINIF {grade}</span>
        <span class="rm-band" style="border-color:color-mix(in srgb, {color} 38%, transparent);background:color-mix(in srgb, {color} 12%, transparent)">
          <span class="rm-dot" style="background:{color}"></span>{esc(score.band)}
        </span>
      </div>
    </div>
  </div>
  <div class="rm-score-scale" role="meter" aria-label="Genel skor" aria-valuenow="{score.overall}" aria-valuemin="0" aria-valuemax="100">{ticks}</div>
  {effort_html}
  <p class="rm-score-note">Altı kategorinin ağırlıklı ortalaması.<br>Yapay zekâ yorumu skoru etkilemez.</p>
</div>""")


def category_meters(categories: list[CategoryScore]) -> None:
    boxes = "".join(
        f"""<div class="rm-cat-box" title="{esc(c.label)}: {c.score}/100 (ağırlık %{c.weight * 100:.0f})">
  <div class="rm-cat-box-top">
    <div class="rm-cat-name">{esc(c.label)}<span>%{c.weight * 100:.0f}</span></div>
    <div class="rm-cat-val" style="color:{'var(--rm-accent)' if c.score >= 75 else band_status(c.score)[0]}">{c.score}</div>
  </div>
  <div class="rm-meter" role="meter" aria-label="{esc(c.label)}" aria-valuenow="{c.score}" aria-valuemin="0" aria-valuemax="100">
    <div style="width:{c.score}%;background:{'var(--rm-accent)' if c.score >= 75 else band_status(c.score)[0]}"></div>
  </div>
</div>"""
        for c in categories
    )
    st.html(f'<div class="rm-card rm-category-card"><div class="rm-label">Kategori puanları (6 Boyut)</div><div class="rm-cat-grid">{boxes}</div></div>')


def score_factors_grid(categories: list[CategoryScore]) -> None:
    cards = []
    for c in categories:
        rows = []
        for f in c.factors:
            tone = "pos" if f.delta > 0 else ("neg" if f.delta < 0 else "zero")
            sign = f"{f.delta:+d}" if f.delta else "—"
            rows.append(f'<div class="rm-factor-row"><span class="rm-delta {tone}">{sign}</span><span>{esc(f.label)}</span></div>')
        if not rows:
            rows.append('<div class="rm-factor-row"><span class="rm-delta zero">—</span><span>Değerlendirilecek veri yok</span></div>')
        cards.append(
            f'<div class="rm-factor-card">'
            f'<div class="rm-factor-head"><b>{esc(c.label)}</b><span>{c.score}/100 · %{c.weight * 100:.0f}</span></div>'
            f'{"".join(rows)}</div>'
        )
    st.html(f'<div class="rm-factor-grid">{"".join(cards)}</div>')


def strengths_card(items: list[str]) -> None:
    if not items:
        st.caption("Öne çıkan bir tespit yok.")
        return
    rows = "".join(
        f'<div class="rm-strength-item"><span class="rm-strength-icon" aria-hidden="true">✔</span><span>{esc(s)}</span></div>'
        for s in items
    )
    st.html(f'<div class="rm-strength-list">{rows}</div>')


def code_composition_card(q: QualityReport) -> None:
    total = max(q.total_lines, 1)
    sloc_pct = round(q.sloc / total * 100, 1)
    comm_pct = round(q.comment_lines / total * 100, 1)
    blank_pct = max(0.0, round(100.0 - sloc_pct - comm_pct, 1))
    st.html(f"""<div class="rm-comp-card">
  <div>
    <div class="rm-label">Satır dağılımı (Toplam {esc(tr_number(q.total_lines))} satır)</div>
    <div class="rm-comp-bar">
      <span style="width:{sloc_pct}%;background:var(--rm-accent)"></span>
      <span style="width:{comm_pct}%;background:var(--rm-good)"></span>
      <span style="width:{blank_pct}%;background:var(--rm-neutral)"></span>
    </div>
    <div class="rm-comp-legend">
      <span><i class="rm-dot" style="background:var(--rm-accent)"></i>Kod (SLOC): <b>{esc(tr_number(q.sloc))}</b> (%{sloc_pct:g})</span>
      <span><i class="rm-dot" style="background:var(--rm-good)"></i>Yorum: <b>{esc(tr_number(q.comment_lines))}</b> (%{comm_pct:g})</span>
      <span><i class="rm-dot" style="background:var(--rm-neutral)"></i>Boş: <b>{esc(tr_number(q.blank_lines))}</b> (%{blank_pct:g})</span>
    </div>
  </div>
  <div class="rm-hygiene-grid">
    <div class="rm-hygiene-pill"><span>Uzun fonksiyon (50+)</span><b>{q.long_functions}</b></div>
    <div class="rm-hygiene-pill"><span>Çıplak except</span><b>{q.bare_excepts}</b></div>
    <div class="rm-hygiene-pill"><span>TODO / FIXME</span><b>{q.todo_count}</b></div>
    <div class="rm-hygiene-pill"><span>Sözdizimi hatası</span><b>{len(q.syntax_errors)}</b></div>
  </div>
</div>""")


def tile(label: str, value: object, note: str = "") -> None:
    st.html(f"""<div class="rm-card">
  <div class="rm-label">{esc(label)}</div>
  <div class="rm-tile-value">{esc(value)}</div>
  <div class="rm-tile-note">{esc(note)}</div>
</div>""")


def severity_badge(severity: str) -> str:
    color = STATUS[SEVERITY_STATUS[severity]]
    return (
        f'<span class="rm-badge" style="border-color:color-mix(in srgb, {color} 38%, transparent);'
        f'background:color-mix(in srgb, {color} 12%, transparent)">'
        f'<span class="rm-dot" style="background:{color}"></span>'
        f'<span class="rm-icon" aria-hidden="true">{SEVERITY_ICON[severity]}</span>{SEVERITY_LABELS[severity]}</span>'
    )


def severity_summary(issues: list[Issue]) -> None:
    cells = []
    for severity, label in SEVERITY_LABELS.items():
        count = sum(1 for i in issues if i.severity == severity)
        color = STATUS[SEVERITY_STATUS[severity]]
        cells.append(
            f'<div class="rm-sev-tile" style="border-top-color:{color}"><b>{count}</b>'
            f'<span><span class="rm-dot" style="background:{color};margin-right:6px"></span>{label}</span></div>'
        )
    st.html(f'<div class="rm-sev-grid">{"".join(cells)}</div>')


def issue_card(issue: Issue, key: str) -> None:
    color = STATUS[SEVERITY_STATUS[issue.severity]]
    with st.container(border=False, key=f"issue-{key}"):
        chips = [
            severity_badge(issue.severity),
            f'<span class="rm-chip">{esc(issue.rule_id)}</span>',
            f'<span class="rm-chip">⏱ {esc(issue.effort_label)}</span>',
            f'<span class="rm-chip">{esc(CATEGORY_NAMES.get(issue.category, issue.category))}</span>',
        ]
        loc_html = ""
        if issue.locations:
            extra = f" (+{len(issue.locations) - 1} konum)" if len(issue.locations) > 1 else ""
            loc_html = f'<div class="rm-issue-loc">📍 {esc(issue.locations[0])}{esc(extra)}</div>'
        st.html(
            f'<div class="rm-issue-header" style="border-left-color:{color}">'
            f'<div class="rm-badges">{"".join(chips)}</div>'
            f'<div class="rm-issue-title">{esc(issue.title)}</div>'
            f'{loc_html}'
            f'<p class="rm-issue-desc">{esc(issue.explanation)}</p>'
            f'</div>'
        )
        with st.expander("Çözüm ve teknik ayrıntılar"):
            confidence = {"high": "yüksek", "medium": "orta", "low": "düşük"}[issue.confidence]
            st.caption(f"{CATEGORY_NAMES.get(issue.category, issue.category)} · Kaynak: {SOURCE_NAMES.get(issue.source, issue.source)} · Güven: {confidence}")
            st.markdown(f"**Öneri:** {safe_md(issue.recommendation)}")
            if issue.snippet:
                st.code(issue.snippet, language="python")
            if len(issue.locations) > 1:
                st.caption(f"Konumlar ({issue.count if issue.count > len(issue.locations) else len(issue.locations)})")
                st.code("\n".join(str(loc) for loc in issue.locations), language=None)


def issue_list(issues: list[Issue], key: str, empty: str = "Bu kategoride bulgu yok.") -> None:
    if not issues:
        st.success(empty)
        return
    for index, issue in enumerate(issues):
        issue_card(issue, f"{key}-{index}")


def checklist(items: list[tuple[str, bool]]) -> None:
    rows = "".join(
        f'<div class="rm-check"><span class="{"ok" if ok else "no"}" aria-hidden="true">{"✔" if ok else "✖"}</span>'
        f'<span>{esc(label)}<span class="rm-disclaimer"> — {"mevcut" if ok else "eksik"}</span></span></div>'
        for label, ok in items
    )
    st.html(f'<div class="rm-card">{rows}</div>')


def facts(rows: list[tuple[str, str]]) -> None:
    body = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in rows)
    st.html(f'<div class="rm-card rm-facts-card"><dl class="rm-facts">{body}</dl></div>')
