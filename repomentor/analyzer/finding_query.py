"""Search and export findings independently of the UI."""

from __future__ import annotations

import csv
import io

from repomentor.models.issue import SEVERITY_LABELS, Issue


def filter_findings(
    issues: list[Issue], query: str = "", severities: list[str] | None = None,
    categories: list[str] | None = None, sort: str = "priority",
) -> list[Issue]:
    terms = query.casefold().split()
    filtered = []
    for issue in issues:
        if severities is not None and issue.severity not in severities:
            continue
        if categories is not None and issue.category not in categories:
            continue
        text = " ".join([
            issue.rule_id, issue.title, issue.explanation, issue.recommendation,
            *(str(loc) for loc in issue.locations),
        ]).casefold()
        if all(term in text for term in terms):
            filtered.append(issue)
    if sort == "effort":
        return sorted(filtered, key=lambda i: (i.effort_minutes, i.sort_key))
    if sort == "file":
        return sorted(filtered, key=lambda i: (i.file or "", i.line or 0, i.sort_key))
    return sorted(filtered, key=lambda i: i.sort_key)


def safe_csv_cell(value: object) -> str:
    text = str(value)
    # Prevent spreadsheet formula injection when a repository controls a cell.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def findings_csv(issues: list[Issue]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["Kural", "Öncelik", "Kategori", "Başlık", "Konum", "Açıklama", "Öneri", "Dakika"])
    for issue in issues:
        writer.writerow([safe_csv_cell(value) for value in [
            issue.rule_id, SEVERITY_LABELS[issue.severity], issue.category, issue.title,
            "; ".join(str(loc) for loc in issue.locations), issue.explanation,
            issue.recommendation, issue.effort_minutes,
        ]])
    return "\ufeff" + stream.getvalue()
