"""Project layout and "can someone else run this?" checks."""

from __future__ import annotations

import re

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.rules import make_issue
from repomentor.models.analysis_result import ProjectInfo
from repomentor.models.issue import Issue, Location
from repomentor.utils.constants import LOCK_FILES

PINNED = re.compile(r"(==|~=|>=|<=|<|>|===|@)")


def unpinned_requirements(project: ProjectFiles) -> list[str]:
    """Requirement lines in the root requirements.txt without any version specifier."""
    names = []
    for path in project.at_root("requirements.txt"):
        for line in (project.text(path) or "").splitlines():
            line = line.split("#", 1)[0].strip()
            if line and not line.startswith(("-", "git+", "http://", "https://")) and not PINNED.search(line):
                names.append(line)
    return names


def is_flat_layout(project: ProjectFiles) -> bool:
    """Eight or more source files and no sub-packages."""
    sources = project.source_python_files
    return len(sources) >= 8 and all("/" not in p for p in sources)


def _dependency_issue(project: ProjectFiles, info: ProjectInfo) -> Issue | None:
    if not info.dependency_files:
        return make_issue("ORG001", [Location("requirements.txt")])
    loose = unpinned_requirements(project)
    if len(loose) >= 3 and not project.at_root(*LOCK_FILES):
        return make_issue("ORG002", [Location("requirements.txt")], {"count": len(loose)}, snippet=", ".join(loose[:8]), count=len(loose))
    return None


def _needs_entry_point(project: ProjectFiles, info: ProjectInfo) -> bool:
    """A notebook is its own entry point; only `.py` projects need a main.py / app.py."""
    has_modules = any(p.endswith(".py") for p in project.source_python_files)
    return not info.entry_points and has_modules and info.project_type != "Python kütüphanesi / paketi"


def _wants_docker(info: ProjectInfo) -> bool:
    return not info.has_docker and bool(info.frameworks) and info.project_type.startswith(("Python web", "Python veri"))


def analyze_organization(project: ProjectFiles, info: ProjectInfo) -> list[Issue]:
    """Layout and "can someone else run this?" checks for Python projects."""
    if info.primary_language not in {"Python", "Jupyter Notebook"}:
        return []
    notebooks = [p for p in project.paths if p.endswith(".ipynb")]
    candidates = [
        _dependency_issue(project, info),
        make_issue("ORG003") if _needs_entry_point(project, info) else None,
        make_issue("ORG004", values={"count": len(project.source_python_files)}) if is_flat_layout(project) else None,
        make_issue("ORG005", [Location("Dockerfile")]) if _wants_docker(info) else None,
        make_issue("ORG006") if not info.python_version and info.dependency_files else None,
        make_issue("ORG007", [Location(notebooks[0])]) if notebooks and not any(p.endswith(".py") for p in project.source_python_files) else None,
    ]
    return [issue for issue in candidates if issue is not None]
