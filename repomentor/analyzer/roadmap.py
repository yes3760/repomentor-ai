"""Turn prioritised issues into a time-boxed action plan."""

from __future__ import annotations

import re

from repomentor.models.analysis_result import RoadmapPhase, RoadmapStep
from repomentor.models.issue import Issue

PHASES = [
    ("first_30m", "İlk 30 dakikada", 30),
    ("first_2h", "İlk 2 saatte", 90),
    ("first_day", "İlk 1 günde", 360),
]


ABBREVIATIONS = ("örn.", "vb.", "vs.", "ör.", "e.g.", "i.e.")


def first_sentence(text: str) -> str:
    protected = text
    for abbr in ABBREVIATIONS:
        protected = protected.replace(abbr, abbr.replace(".", "§"))
    sentence = re.split(r"(?<=[.!?])\s", protected, maxsplit=1)[0]
    return sentence.replace("§", ".").rstrip(".")


def _step_title(issue: Issue) -> str:
    fix = first_sentence(issue.recommendation)
    if len(fix) > 140:
        fix = fix[:137].rstrip() + "…"
    return f"{issue.title} → {fix}"


def build_roadmap(issues: list[Issue]) -> list[RoadmapPhase]:
    phases = [RoadmapPhase(key, label, budget) for key, label, budget in PHASES]
    later = RoadmapPhase("later", "Daha sonra", 0)
    used = [0] * len(phases)

    for issue in sorted(issues, key=lambda i: i.sort_key):
        step = RoadmapStep(_step_title(issue), issue.effort_minutes, issue.severity, issue.rule_id, issue.file)
        # Critical findings always go first, even if they blow the 30-minute box.
        if issue.severity == "critical":
            phases[0].steps.append(step)
            used[0] += issue.effort_minutes
            continue
        start = 2 if issue.severity == "info" else 0
        for index in range(start, len(phases)):
            if used[index] + issue.effort_minutes <= phases[index].budget_minutes:
                phases[index].steps.append(step)
                used[index] += issue.effort_minutes
                break
        else:
            later.steps.append(step)

    for phase in phases:
        phase.steps.sort(key=lambda s: ({"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}[s.severity], s.effort_minutes))
    return [p for p in phases + [later] if p.steps]
