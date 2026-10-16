"""The rule-based stage's output, handed to scoring and to the LLM stage."""

from __future__ import annotations

from dataclasses import dataclass, field

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.models.analysis_result import (
    DependencyReport,
    DocumentationReport,
    ImportGraphReport,
    MLReport,
    ProjectInfo,
    QualityReport,
    SecurityReport,
    TestReport,
    UsageReport,
)
from repomentor.models.issue import Issue


@dataclass
class AnalysisContext:
    project: ProjectFiles
    info: ProjectInfo
    docs: DocumentationReport
    tests: TestReport
    security: SecurityReport
    quality: QualityReport
    issues: list[Issue]
    warnings: list[str] = field(default_factory=list)
    dependencies: DependencyReport = field(default_factory=DependencyReport)
    imports: ImportGraphReport = field(default_factory=ImportGraphReport)
    usage: UsageReport = field(default_factory=UsageReport)
    data_science: MLReport = field(default_factory=MLReport)
