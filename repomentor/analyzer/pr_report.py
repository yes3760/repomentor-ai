"""A short Markdown summary for a pull request: score change, new and resolved findings, gates.

The full Markdown report is long; a PR comment should answer "did this change make the code
better or worse, and what exactly is new?" in one screen. A hidden marker lets the GitHub
Action update its own comment instead of adding one per push.
"""

from __future__ import annotations

from repomentor.analyzer.comparison import Comparison, compare_reports
from repomentor.models.analysis_result import AnalysisResult
from repomentor.models.issue import SEVERITY_LABELS, Issue
from repomentor.utils.constants import APP_NAME
from repomentor.utils.text_utils import mask_secrets

MARKER = "<!-- repomentor-ai:pr-comment -->"
SEVERITY_ICONS = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
LIST_LIMIT = 10
SCORING_URL = "https://github.com/yes3760/repomentor-ai#skor-nasıl-hesaplanır"


def _signed(value: int) -> str:
    return "±0" if value == 0 else f"{value:+d}"


def _issue_line(issue: Issue, fixable: set[str] = frozenset()) -> str:
    where = ", ".join(f"`{loc}`" for loc in issue.locations[:2]) + (" …" if len(issue.locations) > 2 else "")
    fix = " · 🔧 otomatik düzeltme var" if issue.rule_id in fixable else ""
    return f"- {SEVERITY_ICONS[issue.severity]} **{SEVERITY_LABELS[issue.severity]}** · {issue.title}" + (f" — {where}" if where else "") + fix


def _issue_list(title: str, issues: list[Issue], fixable: set[str] = frozenset()) -> list[str]:
    if not issues:
        return []
    more = [f"- … ve {len(issues) - LIST_LIMIT} bulgu daha"] if len(issues) > LIST_LIMIT else []
    return [f"### {title} ({len(issues)})", "", *(_issue_line(i, fixable) for i in issues[:LIST_LIMIT]), *more, ""]


def _category_table(comparison: Comparison) -> list[str]:
    rows = [f"| {c['Kategori']} | {c['Önceki']} | {c['Şimdiki']} | {_signed(c['Fark'])} |" for c in comparison.categories]
    return ["| Kategori | Önce | Sonra | Fark |", "|---|---:|---:|---:|", *rows, ""]


def _changes(comparison: Comparison, fixable: set[str]) -> list[str]:
    if not comparison.added and not comparison.resolved:
        return ["Bu değişiklik yeni bir bulgu eklemiyor ve mevcut bulgulardan birini gidermiyor.", ""]
    return _issue_list("Yeni bulgular", comparison.added, fixable) + _issue_list("Giderilen bulgular", comparison.resolved)


def _gate_lines(gates: list[tuple[str, bool]]) -> list[str]:
    return [f"{'✅' if passed else '❌'} {label}" for label, passed in gates] + ([""] if gates else [])


def _open_findings(current: AnalysisResult) -> list[str]:
    serious = [i for i in current.issues if i.severity in {"critical", "high"}]
    if not serious:
        return []
    return ["<details>", f"<summary>Projedeki kritik ve yüksek öncelikli bulgular ({len(serious)})</summary>", "",
            *(_issue_line(i, current.fixes.rules) for i in serious[:LIST_LIMIT]), "", "</details>", ""]


def build_pr_comment(current: AnalysisResult, previous: AnalysisResult | None = None,
                     gates: list[tuple[str, bool]] | None = None) -> str:
    """`previous` is the base branch; without it the comment summarises the current state only."""
    heading = f"## 🧭 {APP_NAME} · {current.score.overall}/100 · {current.score.band}"
    lines = [MARKER, heading, ""]
    if previous is not None:
        comparison = compare_reports(previous, current)
        lines += [f"Temel dala göre skor: **{previous.score.overall} → {current.score.overall}** ({_signed(comparison.score_delta)})", ""]
        lines += _gate_lines(gates or []) + _category_table(comparison) + _changes(comparison, current.fixes.rules)
    else:
        lines += _gate_lines(gates or []) + [f"{len(current.issues)} bulgu · teknik borç notu {current.debt.rating}", ""]
    lines += _open_findings(current)
    if current.fixes.files:
        lines += [f"🔧 {current.fixes.change_count} güvenli düzeltme hazır: `python -m repomentor . --fix-patch duzeltmeler.patch` "
                  "ile yamayı alıp `git apply duzeltmeler.patch` ile uygulayabilirsiniz.", ""]
    lines.append(f"<sub>{APP_NAME} v{current.version} · kod çalıştırılmadan statik analiz · [Skor nasıl hesaplanır?]({SCORING_URL})</sub>")
    return mask_secrets("\n".join(lines)) + "\n"
