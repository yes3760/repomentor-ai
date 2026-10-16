"""Derived views over the findings: technical debt and the files to fix first.

Technical debt follows the SQALE method used by SonarQube: the remediation
effort of every finding, divided by the estimated cost of writing the code
(30 minutes per line of code), mapped to an A–E rating.

Hotspots are RepoMentor's own ranking. Each file is scored on three axes –
cognitive load, severity-weighted findings and size – and each axis is turned
into a percentile rank among the project's files before weighting, so a
single huge number cannot drown the others and projects of any size compare
on the same 0-100 scale.
"""

from __future__ import annotations

from collections import defaultdict

from repomentor.models.analysis_result import Hotspot, QualityReport, TechnicalDebt
from repomentor.models.issue import Issue

MINUTES_PER_LINE = 30
RATING_LIMITS = (("A", 0.05), ("B", 0.10), ("C", 0.20), ("D", 0.50))
SEVERITY_WEIGHT = {"critical": 10, "high": 5, "medium": 2, "low": 1, "info": 0}
AXIS_WEIGHTS = {"issues": 0.45, "cognitive": 0.35, "lines": 0.20}
MAX_HOTSPOTS = 10


def technical_debt(issues: list[Issue], sloc: int) -> TechnicalDebt:
    """Remediation minutes of every non-AI finding versus the cost of writing the code."""
    by_category: dict[str, int] = defaultdict(int)
    for issue in issues:
        if issue.source != "ai":
            by_category[issue.category] += issue.effort_minutes
    minutes = sum(by_category.values())
    ratio = minutes / (max(sloc, 1) * MINUTES_PER_LINE)
    rating = next((grade for grade, limit in RATING_LIMITS if ratio <= limit), "E")
    return TechnicalDebt(minutes=minutes, ratio=round(ratio, 4), rating=rating, by_category=dict(by_category))


def _percentile_ranks(values: dict[str, float]) -> dict[str, float]:
    """Zero stays 0; non-zero values rank from 1/n (smallest) to 1 (largest), ties sharing a rank.

    A file with any finding must never rank 0, however small its share.
    """
    ordered = sorted({v for v in values.values() if v > 0})
    position = {value: (index + 1) / len(ordered) for index, value in enumerate(ordered)}
    return {key: position.get(value, 0.0) for key, value in values.items()}


def base_path(location_file: str) -> str:
    """Notebook findings point at `nb.ipynb › hücre 3`; files are keyed by the notebook itself."""
    return location_file.split(" › ", 1)[0]


def _file_findings(issues: list[Issue]) -> tuple[dict[str, float], dict[str, int], dict[str, int]]:
    weight: dict[str, float] = defaultdict(float)
    count: dict[str, int] = defaultdict(int)
    severe: dict[str, int] = defaultdict(int)
    for issue in issues:
        if issue.source == "ai":
            continue
        for path in {base_path(loc.file) for loc in issue.locations}:
            weight[path] += SEVERITY_WEIGHT[issue.severity]
            count[path] += 1
            severe[path] += issue.severity in {"critical", "high"}
    return weight, count, severe


def _reasons(stats: dict, count: int, severe: int) -> list[str]:
    reasons = []
    if severe:
        reasons.append(f"{severe} kritik/yüksek bulgu")
    elif count:
        reasons.append(f"{count} bulgu")
    if stats["cognitive"] >= 15:
        reasons.append(f"bilişsel yük {stats['cognitive']}")
    if stats["lines"] >= 300:
        reasons.append(f"{stats['lines']} satır")
    return reasons


def file_risks(quality: QualityReport, issues: list[Issue]) -> dict[str, dict]:
    """Every source file: its 0-100 risk, the percentile rank on each axis and the raw numbers."""
    files = quality.per_file
    weight, count, severe = _file_findings(issues)
    axes = {
        "issues": _percentile_ranks({f: weight.get(f, 0.0) for f in files}),
        "cognitive": _percentile_ranks({f: float(stats["cognitive"]) for f, stats in files.items()}),
        "lines": _percentile_ranks({f: float(stats["lines"]) for f, stats in files.items()}),
    }
    return {
        path: {
            **stats, "weight": weight.get(path, 0.0), "count": count.get(path, 0), "severe": severe.get(path, 0),
            "ranks": {axis: axes[axis][path] for axis in AXIS_WEIGHTS},
            "risk": round(100 * sum(AXIS_WEIGHTS[axis] * axes[axis][path] for axis in AXIS_WEIGHTS)),
        }
        for path, stats in files.items()
    }


def hotspots(quality: QualityReport, issues: list[Issue]) -> list[Hotspot]:
    ranked = [
        Hotspot(file=path, risk=row["risk"], cognitive=row["cognitive"], issues=row["count"], severe=row["severe"],
                lines=row["lines"], reasons=_reasons(row, row["count"], row["severe"]))
        for path, row in file_risks(quality, issues).items()
        if row["weight"] or row["cognitive"] >= 15     # size alone is not a reason to look first
    ]
    return sorted(ranked, key=lambda h: (-h.risk, -h.severe, h.file))[:MAX_HOTSPOTS]
