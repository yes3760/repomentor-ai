"""The single finding type every analyzer produces."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Severity = Literal["critical", "high", "medium", "low", "info"]
Category = Literal["security", "quality", "testing", "documentation", "organization", "runnable"]
Source = Literal["rule", "ast", "taint", "bandit", "ruff", "radon", "osv", "ai"]

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SEVERITY_LABELS = {
    "critical": "Kritik",
    "high": "Yüksek",
    "medium": "Orta",
    "low": "Düşük",
    "info": "Bilgi",
}


@dataclass
class Location:
    file: str
    line: int | None = None

    def __str__(self) -> str:
        return f"{self.file}:{self.line}" if self.line else self.file


@dataclass
class Issue:
    """A prioritised, actionable finding.

    `explanation` answers "why does this matter", `recommendation` answers
    "how do I fix it". Every issue carries an effort estimate so the roadmap
    can be built from issues alone.
    """

    rule_id: str
    title: str
    severity: Severity
    category: Category
    explanation: str
    recommendation: str
    effort_minutes: int
    locations: list[Location] = field(default_factory=list)
    source: Source = "rule"
    confidence: Literal["high", "medium", "low"] = "high"
    snippet: str | None = None
    count: int = 1

    @property
    def file(self) -> str | None:
        return self.locations[0].file if self.locations else None

    @property
    def line(self) -> int | None:
        return self.locations[0].line if self.locations else None

    @property
    def sort_key(self) -> tuple:
        return (SEVERITY_ORDER[self.severity], self.effort_minutes, self.title)

    @property
    def effort_label(self) -> str:
        return format_effort(self.effort_minutes)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["effort_label"] = self.effort_label
        data["severity_label"] = SEVERITY_LABELS[self.severity]
        return data


def format_effort(minutes: int) -> str:
    """Human effort label in Turkish: '10 dakika', '1,5 saat', '1,1 gün'."""
    if minutes < 60:
        return f"{minutes} dakika"
    hours = minutes / 60
    if hours < 8:
        value = round(hours * 2) / 2
        return f"{value:g} saat".replace(".", ",")
    return f"{round(hours / 8, 1):g} gün".replace(".", ",")
