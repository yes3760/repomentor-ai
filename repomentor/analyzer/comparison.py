"""Compare deterministic reports without treating shifted line numbers as new issues."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlsplit

from repomentor.models.analysis_result import AnalysisResult
from repomentor.models.issue import Issue


@dataclass
class Comparison:
    score_delta: int
    categories: list[dict]
    added: list[Issue]
    resolved: list[Issue]
    unchanged: int
    same_project: bool


def project_identity(result: AnalysisResult) -> str:
    """GitHub identities include the owner, branch and subdirectory when provided."""
    p = result.project
    if not p.source_url:
        return f"{p.source}:{p.name}"
    url = urlsplit(p.source_url)
    parts = url.path.strip("/").removesuffix(".git").split("/")
    repository = "/".join(parts[:2]).casefold()
    scope = "/".join(parts[2:])  # Branch and directory names are case-sensitive.
    return f"{url.netloc.casefold()}/{repository}" + (f"/{scope}" if scope else "")


def _fingerprint(issue: Issue) -> tuple:
    # Titles can include changing counts; source lines can move after unrelated edits.
    return issue.rule_id, tuple(sorted({loc.file for loc in issue.locations}))


def _difference(current: list[Issue], previous: list[Issue]) -> list[Issue]:
    remaining = Counter(_fingerprint(i) for i in previous)
    difference = []
    for issue in current:
        key = _fingerprint(issue)
        if remaining[key]:
            remaining[key] -= 1
        else:
            difference.append(issue)
    return difference


def compare_reports(previous: AnalysisResult, current: AnalysisResult) -> Comparison:
    """Match rule + file set as a multiset; AI opinions never affect this comparison."""
    before = {c.key: c for c in previous.score.categories}
    added = _difference(current.issues, previous.issues)
    resolved = _difference(previous.issues, current.issues)
    return Comparison(
        score_delta=current.score.overall - previous.score.overall,
        categories=[
            {"Kategori": c.label, "Önceki": before[c.key].score, "Şimdiki": c.score,
             "Fark": c.score - before[c.key].score}
            for c in current.score.categories if c.key in before
        ],
        added=added, resolved=resolved, unchanged=len(current.issues) - len(added),
        same_project=project_identity(previous) == project_identity(current),
    )
