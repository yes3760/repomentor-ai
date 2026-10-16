"""Typed containers for every section of an analysis report."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from repomentor.models.issue import Issue


@dataclass
class FileInfo:
    path: str                     # POSIX path relative to project root
    size: int
    language: str | None = None
    lines: int = 0
    skipped_reason: str | None = None


@dataclass
class ProjectInfo:
    name: str
    source: str                   # "zip" | "github" | "local" | "demo"
    source_url: str | None = None
    project_type: str = "Bilinmeyen proje türü"
    primary_language: str | None = None
    languages: dict[str, int] = field(default_factory=dict)   # language -> lines
    frameworks: list[str] = field(default_factory=list)
    ml_libraries: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    test_tools: list[str] = field(default_factory=list)
    has_docker: bool = False
    has_ci: bool = False
    entry_points: list[str] = field(default_factory=list)
    dependency_files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    python_version: str | None = None
    github: dict | None = None

    @property
    def technologies(self) -> list[str]:
        techs: list[str] = []
        if self.primary_language:
            techs.append(self.primary_language)
        for group in (self.frameworks, self.databases, self.ml_libraries, self.test_tools):
            techs.extend(t for t in group if t not in techs)
        if self.has_docker:
            techs.append("Docker")
        if self.has_ci:
            techs.append("GitHub Actions")
        return techs


@dataclass
class BrokenCommand:
    command: str
    problem: str
    line: int


@dataclass
class DocumentationReport:
    has_readme: bool = False
    readme_path: str | None = None
    readme_words: int = 0
    checks: dict[str, bool] = field(default_factory=dict)
    license_file: str | None = None
    has_env_example: bool = False
    has_contributing: bool = False
    has_changelog: bool = False
    documented_symbols: int = 0
    documentable_symbols: int = 0
    commands_checked: int = 0
    broken_commands: list[BrokenCommand] = field(default_factory=list)

    @property
    def docstring_coverage(self) -> float | None:
        if not self.documentable_symbols:
            return None
        return self.documented_symbols / self.documentable_symbols


@dataclass
class TestReport:
    __test__ = False  # not a pytest test class

    test_files: list[str] = field(default_factory=list)
    test_functions: int = 0
    source_functions: int = 0
    frameworks: list[str] = field(default_factory=list)
    ci_files: list[str] = field(default_factory=list)
    ci_runs_tests: bool = False
    has_conftest: bool = False
    has_coverage_config: bool = False

    @property
    def ratio(self) -> float:
        return self.test_functions / self.source_functions if self.source_functions else 0.0

    @property
    def status(self) -> str:
        if not self.test_files:
            return "Yok"
        if self.test_functions >= 10 and self.ratio >= 0.3:
            return "İyi"
        if self.test_functions >= 3:
            return "Orta"
        return "Zayıf"


@dataclass
class TaintFlow:
    """User input that reaches a dangerous call, with the path it took."""

    kind: str            # code | command | sql | path | deserialize | template | ssrf | redirect | xss
    file: str
    line: int
    sink: str            # the dangerous call as written
    source: str          # where the input came from
    source_line: int
    path: list[str] = field(default_factory=list)   # variables the value passed through
    function: str = ""
    remote: bool = True  # web input (False: console input such as input())
    via: str | None = None   # helper function that contains the sink


@dataclass
class ImportEdge:
    source: str
    target: str
    lazy: bool = False      # imported inside a function: cannot cause an import-time cycle


@dataclass
class ModuleCoupling:
    name: str
    file: str
    fan_in: int             # Ca: modules that import this one
    fan_out: int            # Ce: project modules this one imports
    instability: float      # Ce / (Ca + Ce): 0 = stable foundation, 1 = depends on everything


@dataclass
class ImportGraphReport:
    modules: list[ModuleCoupling] = field(default_factory=list)
    edges: list[ImportEdge] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)   # each: a → b → … → a


@dataclass
class SecurityReport:
    secrets_found: int = 0
    dangerous_calls: int = 0
    bandit_ran: bool = False
    bandit_issues: int = 0
    bandit_error: str | None = None
    env_committed: list[str] = field(default_factory=list)
    has_gitignore: bool = False
    gitignore_covers_env: bool = False
    taint_flows: list[TaintFlow] = field(default_factory=list)
    taint_functions: int = 0


@dataclass
class Vulnerability:
    id: str
    summary: str
    severity: str                  # critical | high | medium | low
    fixed: str | None = None       # first version that fixes it for the installed range
    cve: str | None = None
    url: str = ""


@dataclass
class VulnerablePackage:
    name: str
    version: str
    file: str
    severity: str
    vulnerabilities: list[Vulnerability]
    fixed_version: str | None = None   # smallest version that fixes every advisory with a fix
    line: int | None = None


@dataclass
class DependencyReport:
    """Known-vulnerability lookup for dependencies with an exact version (OSV.dev)."""

    enabled: bool = False
    ran: bool = False
    error: str | None = None
    total: int = 0                 # dependencies declared (exact + loose)
    checked: int = 0               # exact versions sent to OSV.dev
    skipped: int = 0               # exact versions beyond the per-analysis cap
    unpinned: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    vulnerable: list[VulnerablePackage] = field(default_factory=list)

    @property
    def vulnerability_count(self) -> int:
        return sum(len(p.vulnerabilities) for p in self.vulnerable)


@dataclass
class FunctionMetric:
    file: str
    name: str
    line: int
    length: int
    complexity: int = 1      # cyclomatic: independent paths (testing effort)
    params: int = 0
    cognitive: int = 0       # cognitive: how hard the code is to read

    @property
    def difficulty(self) -> float:
        """Distance from the limits; >= 1 means at least one metric is over its threshold."""
        return max(self.complexity / 11, self.cognitive / 15)


@dataclass
class DuplicateBlock:
    lines: int
    occurrences: list[str]            # "path:line"
    preview: str


@dataclass
class CloneGroup:
    """Functions with the same structure that differ only in names or literal values."""

    members: list[str]       # "path:line name()"
    lines: int


@dataclass
class QualityReport:
    python_files: int = 0
    total_lines: int = 0
    sloc: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    functions: int = 0
    classes: int = 0
    avg_function_length: float = 0.0
    long_functions: int = 0
    avg_complexity: float = 0.0
    avg_maintainability: float | None = None
    complexity_distribution: dict[str, int] = field(default_factory=dict)
    longest_functions: list[FunctionMetric] = field(default_factory=list)
    most_complex: list[FunctionMetric] = field(default_factory=list)
    maintainability: list[dict] = field(default_factory=list)      # {file, mi, rank}
    ruff_ran: bool = False
    ruff_error: str | None = None
    ruff_total: int = 0
    ruff_by_code: dict[str, dict] = field(default_factory=dict)    # code -> {count, message, sample}
    duplicates: list[DuplicateBlock] = field(default_factory=list)
    clones: list[CloneGroup] = field(default_factory=list)
    avg_cognitive: float = 0.0
    hard_functions: int = 0          # over a limit (cyclomatic >= 11 or cognitive >= 15)
    very_hard_functions: int = 0     # far over (cyclomatic >= 21 or cognitive >= 30)
    annotated: int = 0               # type-hinted parameters + return values
    annotatable: int = 0
    syntax_errors: list[str] = field(default_factory=list)
    per_file: dict[str, dict] = field(default_factory=dict)     # path -> {cognitive, functions, lines}
    bare_excepts: int = 0
    todo_count: int = 0
    flow: list[FlowFinding] = field(default_factory=list)   # control-flow graph findings

    @property
    def type_hint_coverage(self) -> float | None:
        return self.annotated / self.annotatable if self.annotatable else None


@dataclass
class UnusedSymbol:
    name: str          # qualified, e.g. "Report.render"
    kind: str          # function | method | class
    file: str
    line: int


@dataclass
class UsageReport:
    """Call-graph answers: what nothing uses, and what the tests can reach."""

    symbols: int = 0
    references: int = 0
    unused: list[UnusedSymbol] = field(default_factory=list)
    test_reached: int = 0
    test_total: int = 0
    untested: list[UnusedSymbol] = field(default_factory=list)   # public functions no test reaches

    @property
    def test_reach(self) -> float | None:
        return self.test_reached / self.test_total if self.test_total else None


@dataclass
class FileFix:
    """One file of the downloadable fix patch."""

    path: str
    diff: str                                             # unified diff (`git apply` / `patch -p1`)
    changes: list[str] = field(default_factory=list)      # what was changed, in plain words
    rules: list[str] = field(default_factory=list)        # issue rule ids this fix resolves
    new_file: bool = False


@dataclass
class FixReport:
    files: list[FileFix] = field(default_factory=list)

    @property
    def patch(self) -> str:
        return "".join(f.diff for f in self.files)

    @property
    def change_count(self) -> int:
        return sum(len(f.changes) for f in self.files)

    @property
    def rules(self) -> set[str]:
        return {rule for f in self.files for rule in f.rules}


@dataclass
class FlowFinding:
    """A control-flow finding inside one function (unreachable code, unreleased resource)."""

    rule: str          # QLT014, QLT015
    file: str
    line: int
    function: str
    detail: str


@dataclass
class MLFinding:
    rule: str          # LEAK001, LEAK002, PD001…
    file: str
    line: int
    detail: str


@dataclass
class MLReport:
    applicable: bool = False   # the project uses pandas / scikit-learn
    findings: list[MLFinding] = field(default_factory=list)


@dataclass
class TechnicalDebt:
    """SQALE-style remediation cost (the model behind SonarQube's maintainability rating)."""

    minutes: int = 0
    ratio: float = 0.0                 # remediation cost / estimated cost to write the code
    rating: str = "A"                  # A ≤ 5 %, B ≤ 10 %, C ≤ 20 %, D ≤ 50 %, E > 50 %
    by_category: dict[str, int] = field(default_factory=dict)


@dataclass
class Hotspot:
    """A file ranked by how much attention it needs first."""

    file: str
    risk: int                          # 0-100
    cognitive: int
    issues: int
    severe: int                        # critical + high findings in the file
    lines: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class ScoreFactor:
    label: str
    delta: int


@dataclass
class CategoryScore:
    key: str
    label: str
    score: int
    weight: float
    factors: list[ScoreFactor] = field(default_factory=list)


@dataclass
class ScoreReport:
    overall: int
    band: str
    categories: list[CategoryScore]

    def category(self, key: str) -> CategoryScore:
        return next(c for c in self.categories if c.key == key)


@dataclass
class RoadmapStep:
    title: str
    effort_minutes: int
    severity: str
    rule_id: str | None = None
    file: str | None = None


@dataclass
class RoadmapPhase:
    key: str
    label: str
    budget_minutes: int
    steps: list[RoadmapStep] = field(default_factory=list)


@dataclass
class CareerTexts:
    project_title: str
    cv_bullets: list[str]
    linkedin_post: str
    linkedin_short: str
    source: str = "rule"              # "rule" | "ai"


@dataclass
class AIInsights:
    provider: str
    model: str
    summary: str = ""
    architecture_review: str = ""
    readability_review: str = ""
    strengths: list[str] = field(default_factory=list)
    readme_suggestions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    extra_issues: list[Issue] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class AnalysisResult:
    project: ProjectInfo
    files: list[FileInfo]
    documentation: DocumentationReport
    tests: TestReport
    security: SecurityReport
    quality: QualityReport
    issues: list[Issue]
    score: ScoreReport
    roadmap: list[RoadmapPhase]
    career: CareerTexts
    summary: str
    strengths: list[str] = field(default_factory=list)
    ai: AIInsights | None = None
    warnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    analyzed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    version: str = ""
    dependencies: DependencyReport = field(default_factory=DependencyReport)
    imports: ImportGraphReport = field(default_factory=ImportGraphReport)
    usage: UsageReport = field(default_factory=UsageReport)
    data_science: MLReport = field(default_factory=MLReport)
    fixes: FixReport = field(default_factory=FixReport)
    debt: TechnicalDebt = field(default_factory=TechnicalDebt)
    hotspots: list[Hotspot] = field(default_factory=list)

    def issues_by_category(self, category: str) -> list[Issue]:
        return [i for i in self.issues if i.category == category]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["issues"] = [i.to_dict() for i in self.issues]
        if self.ai:
            data["ai"]["extra_issues"] = [i.to_dict() for i in self.ai.extra_issues]
        data["documentation"]["docstring_coverage"] = self.documentation.docstring_coverage
        data["tests"]["status"] = self.tests.status
        data["project"]["technologies"] = self.project.technologies
        data["dependencies"]["vulnerability_count"] = self.dependencies.vulnerability_count
        # The patch is its own download; diff context lines would copy source code into a report meant for sharing.
        for fix in data["fixes"]["files"]:
            fix.pop("diff")
        data["fixes"]["change_count"] = self.fixes.change_count
        return data
