"""Test suite presence, size and CI wiring."""

from __future__ import annotations

import ast
import re

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.rules import make_issue
from repomentor.models.analysis_result import ProjectInfo, TestReport
from repomentor.models.issue import Issue, Location

CI_TEST_COMMAND = re.compile(r"\b(pytest|unittest|tox|nox|nose2|coverage run|make test|python -m pytest)\b")


def count_test_functions(project: ProjectFiles) -> int:
    """Number of `test*` functions inside test files."""
    total = 0
    for path in project.test_python_files:
        if (tree := project.tree(path)) is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                total += 1
    return total


def count_source_functions(project: ProjectFiles) -> int:
    """Number of public functions in non-test source files."""
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
        for _, tree in project.parsed_python(include_tests=False)
        for node in ast.walk(tree)
    )


def build_test_report(project: ProjectFiles, info: ProjectInfo) -> TestReport:
    """Count test files and functions and detect CI / coverage configuration."""
    report = TestReport(
        test_files=[p for p in project.test_python_files if not p.endswith(("conftest.py", "__init__.py"))],
        test_functions=count_test_functions(project),
        source_functions=count_source_functions(project),
        frameworks=list(info.test_tools),
        has_conftest=bool(project.by_name("conftest.py")),
    )
    config_text = "".join(project.text(p) or "" for p in project.at_root("pyproject.toml", "setup.cfg", "tox.ini", "pytest.ini"))
    report.has_coverage_config = bool(project.at_root(".coveragerc")) or "[tool.coverage" in config_text or "--cov" in config_text
    ci_names = {".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml", ".circleci/config.yml"}
    report.ci_files = [p for p in project.paths if (p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))) or p in ci_names]
    report.ci_runs_tests = any(CI_TEST_COMMAND.search(project.text(p) or "") for p in report.ci_files)
    return report


def _coverage_issue(report: TestReport) -> Issue | None:
    if not report.test_files:
        return make_issue("TST001", [Location("tests/")])
    if report.test_functions < 3:
        return make_issue("TST002", [Location(report.test_files[0])], {"count": report.test_functions})
    if report.ratio < 0.2 and report.source_functions >= 15:
        values = {"functions": report.source_functions, "tests": report.test_functions, "ratio": f"{report.ratio:.2f}".replace(".", ",")}
        return make_issue("TST003", values=values, confidence="medium")
    return None


def analyze_tests(project: ProjectFiles, info: ProjectInfo) -> tuple[TestReport, list[Issue]]:
    """Test suite presence, size and CI wiring."""
    report = build_test_report(project, info)
    if report.source_functions == 0:
        return report, []
    issues = [issue] if (issue := _coverage_issue(report)) else []
    if report.test_files and not report.ci_runs_tests:
        issues.append(make_issue("TST004", [Location(".github/workflows/tests.yml")]))
    return report, issues
