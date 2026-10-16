"""Dead code and static test reach, both answered by the call graph."""

from __future__ import annotations

from pathlib import PurePosixPath

from repomentor.analyzer.call_graph import TEST_CLIENT, CallGraph, Symbol, build_call_graph
from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.rules import make_issue
from repomentor.models.analysis_result import UnusedSymbol, UsageReport
from repomentor.models.issue import Issue, Location

MAX_LISTED = 40


def _dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _private(symbol: Symbol, graph: CallGraph) -> bool:
    owner = graph.symbols.get(symbol.owner) if symbol.owner else None
    return symbol.name.startswith("_") or bool(owner and owner.name.startswith("_"))


def _measurable(symbol: Symbol) -> bool:
    """Source code a person wrote and could delete or test (not tests, protocol methods or declarations)."""
    return not symbol.test and not symbol.pure_only and "<locals>" not in symbol.key and not _dunder(symbol.name)


def _qualified(symbol: Symbol) -> str:
    return symbol.key.split(":", 1)[1]


def _reportable(symbol: Symbol, graph: CallGraph, alive: set[str], library: bool) -> bool:
    if symbol.kind not in {"function", "method", "class"} or symbol.key in alive or not _measurable(symbol):
        return False
    return not library or _private(symbol, graph)   # a library's public names are its API, used by code we cannot see


def find_unused(graph: CallGraph, library: bool) -> list[UnusedSymbol]:
    roots = {k for k, s in graph.symbols.items() if s.root or s.kind in {"module", "variable"}} | graph.script_roots()
    alive = graph.reachable(roots)
    unused, dead_classes = [], set()
    for symbol in sorted(graph.symbols.values(), key=lambda s: (s.file, s.line)):
        if not _reportable(symbol, graph, alive, library) or symbol.owner in dead_classes:
            continue   # a dead class is reported once instead of every method
        if symbol.kind == "class":
            dead_classes.add(symbol.key)
        unused.append(UnusedSymbol(_qualified(symbol), symbol.kind, symbol.file, symbol.line))
    return unused


def _indirect_test_roots(graph: CallGraph, test_text: str) -> set[str]:
    """Source code tests exercise without calling it: scripts run by path, endpoints hit through a test client."""
    uses_client = bool(TEST_CLIENT.search(test_text))
    roots = set()
    for key, symbol in graph.symbols.items():
        if symbol.test:
            continue
        if symbol.kind == "module" and f'"{PurePosixPath(symbol.file).name}"' in test_text:
            roots.add(key)        # AppTest.from_file("app.py") / subprocess runs execute the module
        elif symbol.route and uses_client:
            roots.add(key)
    return roots


def _test_roots(graph: CallGraph, project: ProjectFiles) -> set[str]:
    roots = {k for k, s in graph.symbols.items() if s.test and (s.root or s.kind in {"module", "variable"})}
    test_text = "\n".join(project.texts[p] for p in project.python_files if project.is_test(p))
    return roots | _indirect_test_roots(graph, test_text)


def test_reach(graph: CallGraph, project: ProjectFiles) -> tuple[int, int, list[UnusedSymbol]]:
    reached = graph.reachable(_test_roots(graph, project))
    measured = [s for s in graph.symbols.values() if s.kind in {"function", "method"} and _measurable(s)]
    covered = sum(1 for s in measured if s.key in reached)
    untested = [
        UnusedSymbol(_qualified(s), s.kind, s.file, s.line)
        for s in sorted(measured, key=lambda s: (s.file, s.line))
        if s.key not in reached and not _private(s, graph)
    ]
    return covered, len(measured), untested


def _names(items: list[UnusedSymbol], limit: int = 5) -> str:
    shown = ", ".join(f"`{i.name}`" for i in items[:limit])
    return shown + (f" ve {len(items) - limit} tane daha" if len(items) > limit else "")


def usage_issues(report: UsageReport, has_tests: bool) -> list[Issue]:
    issues = []
    if report.unused:
        issues.append(make_issue(
            "DEAD001", [Location(u.file, u.line) for u in report.unused][:15],
            {"count": len(report.unused), "names": _names(report.unused)},
            source="ast", confidence="medium", count=len(report.unused),
            effort_minutes=min(10 + 5 * len(report.unused), 120),
        ))
    if has_tests and report.untested and report.test_reach is not None:
        issues.append(make_issue(
            "TST005", [Location(u.file, u.line) for u in report.untested][:15],
            {"count": len(report.untested), "percent": f"{report.test_reach * 100:.0f}", "names": _names(report.untested)},
            source="ast", confidence="medium", count=len(report.untested),
            effort_minutes=min(20 * len(report.untested), 480),
        ))
    return issues


def analyze_usage(project: ProjectFiles, library: bool = False) -> tuple[UsageReport, list[Issue]]:
    graph = build_call_graph(project)
    covered, total, untested = test_reach(graph, project)
    report = UsageReport(
        symbols=sum(1 for s in graph.symbols.values() if s.kind in {"function", "method", "class"}),
        references=sum(len(targets) for targets in graph.edges.values()),
        unused=find_unused(graph, library)[:MAX_LISTED],
        test_reached=covered, test_total=total, untested=untested[:MAX_LISTED],
    )
    has_tests = any(s.test and s.root == "test" for s in graph.symbols.values())
    return report, usage_issues(report, has_tests)
