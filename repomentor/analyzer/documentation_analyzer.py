"""README completeness, licence, env documentation and docstring coverage."""

from __future__ import annotations

import ast
import re

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.readme_commands import check_readme_commands
from repomentor.analyzer.rules import make_issue
from repomentor.models.analysis_result import DocumentationReport, ProjectInfo
from repomentor.models.issue import Issue, Location
from repomentor.utils.text_utils import contains_any

README_NAMES = ("README.md", "README.rst", "README.txt", "README", "readme.md", "Readme.md")
ENV_USAGE = re.compile(r"os\.getenv|os\.environ|load_dotenv|dotenv_values|decouple|st\.secrets|BaseSettings")

README_CHECKS: dict[str, tuple[str, tuple[str, ...]]] = {
    "has_installation": ("Kurulum adımları", ("installation", "kurulum", "install", "getting started", "setup", "pip install", "başlarken")),
    "has_usage": ("Kullanım / çalıştırma", ("usage", "kullanım", "how to run", "çalıştır", "run the", "streamlit run", "python -m", "python main", "python app", "uvicorn ", "flask run", "örnek kullanım")),
    "has_features": ("Özellikler", ("features", "özellikler", "what it does", "neler yapar")),
    "has_tech_stack": ("Kullanılan teknolojiler", ("tech stack", "technologies", "teknolojiler", "built with", "kullanılan", "gereksinimler")),
    "has_screenshot": ("Ekran görüntüsü / demo", ("![", "<img", ".gif", "screenshot", "ekran görüntüsü")),
    "has_code_blocks": ("Kod / komut örnekleri", ("```", "    $ ", ".. code")),
    "has_license": ("Lisans bilgisi", ("license", "lisans")),
}
CHECK_LABELS = {key: label for key, (label, _) in README_CHECKS.items()}


# README section check -> rule fired when the section is missing.
SECTION_RULES = {
    "has_installation": "DOC003",
    "has_usage": "DOC004",
    "has_features": "DOC005",
    "has_screenshot": "DOC006",
    "has_tech_stack": "DOC007",
}
ENV_EXAMPLE_NAMES = (".env.example", ".env.sample", ".env.template", "env.example", "example.env", "secrets.toml.example")
LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING")


def find_readme(project: ProjectFiles) -> str | None:
    """Prefer a README at the root; fall back to the shallowest one."""
    root_hits = project.at_root(*README_NAMES)
    if root_hits:
        return root_hits[0]
    hits = project.by_name(*README_NAMES)
    return hits[0] if hits else None


def uses_environment(project: ProjectFiles) -> bool:
    """True when source code reads environment variables or secrets."""
    return any(ENV_USAGE.search(project.text(p) or "") for p in project.source_python_files)


def analyze_readme(text: str) -> dict[str, bool]:
    """Keyword-based presence check for the usual README sections (TR + EN)."""
    return {key: contains_any(text, words) for key, (_, words) in README_CHECKS.items()}


def docstring_counts(project: ProjectFiles) -> tuple[int, int]:
    """(documented, documentable) public functions and classes in source files."""
    documented = documentable = 0
    for _, tree in project.parsed_python(include_tests=False):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                documentable += 1
                documented += ast.get_docstring(node) is not None
    return documented, documentable


def build_documentation_report(project: ProjectFiles) -> DocumentationReport:
    """Collect README, licence, env template and docstring facts."""
    licence = project.at_root(*LICENSE_NAMES)
    report = DocumentationReport(
        license_file=licence[0] if licence else None,
        has_env_example=bool(project.by_name(*ENV_EXAMPLE_NAMES)),
        has_contributing=bool(project.at_root("CONTRIBUTING.md")),
        has_changelog=bool(project.at_root("CHANGELOG.md", "CHANGES.md", "HISTORY.md")),
    )
    report.documented_symbols, report.documentable_symbols = docstring_counts(project)
    readme = find_readme(project)
    report.checks = {key: False for key in README_CHECKS}
    if readme:
        text = project.text(readme) or ""
        report.has_readme, report.readme_path = True, readme
        report.readme_words = len(re.findall(r"\w+", text))
        report.checks = analyze_readme(text)
    report.checks["has_license"] = report.checks["has_license"] or bool(report.license_file)
    return report


def _readme_issues(report: DocumentationReport) -> list[Issue]:
    if not report.has_readme:
        return [make_issue("DOC001", [Location("README.md")])]
    loc = [Location(report.readme_path)]
    issues = [make_issue("DOC002", loc, {"words": report.readme_words})] if report.readme_words < 120 else []
    issues += [make_issue(rule_id, loc) for key, rule_id in SECTION_RULES.items() if not report.checks.get(key)]
    return issues


def _docstring_issue(report: DocumentationReport) -> Issue | None:
    coverage = report.docstring_coverage
    if coverage is None or report.documentable_symbols < 6 or coverage >= 0.3:
        return None
    values = {"percent": f"{coverage * 100:.0f}", "total": report.documentable_symbols, "documented": report.documented_symbols}
    return make_issue("DOC010", values=values, confidence="medium")


def analyze_documentation(project: ProjectFiles, info: ProjectInfo) -> tuple[DocumentationReport, list[Issue]]:
    """README completeness, licence, env documentation and docstring coverage."""
    report = build_documentation_report(project)
    issues = _readme_issues(report)
    if not report.license_file:
        issues.append(make_issue("DOC008", [Location("LICENSE")]))
    if uses_environment(project) and not report.has_env_example:
        issues.append(make_issue("DOC009", [Location(".env.example")]))
    if docstring_issue := _docstring_issue(report):
        issues.append(docstring_issue)
    report.commands_checked, report.broken_commands = check_readme_commands(project, report.readme_path, info.dependencies)
    if broken := report.broken_commands:
        shown = "; ".join(f"`{b.command}` ({b.problem})" for b in broken[:4]) + (f" ve {len(broken) - 4} komut daha" if len(broken) > 4 else "")
        issues.append(make_issue("DOC011", [Location(report.readme_path, b.line) for b in broken][:10],
                                 {"count": len(broken), "commands": shown}, count=len(broken),
                                 effort_minutes=min(10 + 5 * len(broken), 60)))
    return report, issues
