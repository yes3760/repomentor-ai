"""Potential security risks: committed secrets, .env hygiene, dangerous calls, Bandit.

Every finding here is a *potential* risk. Pattern matching cannot know whether
`eval()` ever sees user input, so messages are worded accordingly.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from repomentor.analyzer.documentation_analyzer import uses_environment
from repomentor.analyzer.entropy import describe_hit, find_high_entropy
from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.rules import POTENTIAL_NOTE, make_issue
from repomentor.analyzer.taint import describe, find_taint_flows
from repomentor.models.analysis_result import SecurityReport, TaintFlow
from repomentor.models.issue import Issue, Location
from repomentor.utils.constants import TOOL_TIMEOUT_SECONDS
from repomentor.utils.text_utils import (
    KNOWN_TOKEN_PATTERNS,
    SECRET_ASSIGNMENT,
    is_placeholder,
    mask_secrets,
    mask_value,
)

SECRET_SCAN_SUFFIXES = {".py", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".env", ".txt", ".sh", ".js", ".ts"}
EXAMPLE_MARKERS = ("example", "sample", "template", "dist")
ENV_IGNORE_PATTERNS = {".env", ".env*", "*.env", ".env.*", ".env.local"}
MAX_LOCATIONS = 15

# Bandit checks that are either noise for this audience or duplicated by our own rules.
BANDIT_SKIP = {
    "B101",   # assert_used – normal in tests / scripts
    "B104",   # binding to 0.0.0.0 – standard for container apps
    "B105", "B106", "B107",  # hardcoded passwords – handled by our masked secret scan
    "B110", "B112",  # try/except/pass – a quality concern, reported by Ruff
    "B311",   # random – only matters for crypto use
    "B404", "B603", "B607",  # importing / calling subprocess without shell – low signal
    "B307", "B102", "B301", "B403", "B506", "B602", "B605", "B501", "B201",  # covered by our AST rules
}


def _grouped(rule_id: str, locations: list[Location], step: int = 5, **overrides) -> Issue:
    """One issue for many hits of the same rule; effort grows with the hit count."""
    issue = make_issue(rule_id, locations[:MAX_LOCATIONS], count=len(locations), **overrides)
    issue.effort_minutes += step * min(len(locations) - 1, 6)
    return issue


# --- Secrets ------------------------------------------------------------------

@dataclass
class _SecretHits:
    known: dict[str, list[Location]] = field(default_factory=lambda: defaultdict(list))
    assigned: list[Location] = field(default_factory=list)
    snippet: str | None = None


def _is_scan_target(path: str) -> bool:
    p = PurePosixPath(path)
    return p.suffix.lower() in SECRET_SCAN_SUFFIXES or p.name.startswith(".env")


def _skip_assignments(project: ProjectFiles, path: str) -> bool:
    """Example files, test fixtures and .env files (reported as a whole) are not scanned for assignments."""
    name = PurePosixPath(path).name.lower()
    return any(marker in name for marker in EXAMPLE_MARKERS) or name.startswith(".env") or project.is_test(path)


# Bare `key` is usually a dict or widget key (`st.button(..., key="save")`), not a credential.
GENERIC_KEY_NAMES = {"key", "keys"}


def _looks_random(value: str) -> bool:
    return len(value) >= 16 and any(c.isdigit() for c in value) and any(c.isalpha() for c in value)


def _is_real_value(name: str, value: str) -> bool:
    value = value.strip()
    if len(value) < 6 or " " in value or is_placeholder(value) or value.startswith(("http://", "https://", "/")):
        return False
    return _looks_random(value) if name.lower() in GENERIC_KEY_NAMES else True


def _scan_line(hits: _SecretHits, location: Location, line: str, check_assignments: bool) -> None:
    for label, pattern in KNOWN_TOKEN_PATTERNS.items():
        if pattern.search(line) and "EXAMPLE" not in line:
            hits.known[label].append(location)
    if not check_assignments:
        return
    for match in SECRET_ASSIGNMENT.finditer(line):
        if _is_real_value(match.group("name"), match.group("value")):
            hits.assigned.append(location)
            hits.snippet = hits.snippet or f'{match.group("name")} = "{mask_value(match.group("value"))}"'


def scan_secrets(project: ProjectFiles) -> list[Issue]:
    """Known token formats anywhere; KEY/TOKEN/PASSWORD assignments in source files."""
    hits = _SecretHits()
    for path, text in project.texts.items():
        if not _is_scan_target(path):
            continue
        check_assignments = not _skip_assignments(project, path)
        for lineno, line in enumerate(text.splitlines(), 1):
            if len(line) <= 1000:
                _scan_line(hits, Location(path, lineno), line, check_assignments)

    issues = [_grouped("SEC001", locations, step=0, values={"label": label}) for label, locations in hits.known.items()]
    if hits.assigned:
        issues.append(_grouped("SEC002", hits.assigned, values={"count": len(hits.assigned)}, confidence="medium", snippet=hits.snippet))
    return issues


def entropy_issues(project: ProjectFiles, already: set[tuple[str, int]]) -> list[Issue]:
    hits = find_high_entropy(project, already)
    if not hits:
        return []
    examples = "; ".join(f"{describe_hit(h)} {h.file}:{h.line}" for h in hits[:3])
    return [make_issue("SEC007", [Location(h.file, h.line) for h in hits][:MAX_LOCATIONS], {"count": len(hits), "examples": examples},
                       confidence="low", count=len(hits), snippet="\n".join(describe_hit(h) for h in hits[:5]))]


# --- .env and .gitignore ------------------------------------------------------------

def _env_has_values(text: str) -> bool:
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line and line.split("=", 1)[1].strip().strip("'\""):
            return True
    return False


def _is_env_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return name.startswith(".env") and not any(m in name.lower() for m in EXAMPLE_MARKERS) and not name.endswith((".py", ".md"))


def _env_file_issue(path: str, source: str, covered: bool) -> Issue:
    # A ZIP made from a local checkout can contain a .env that git never sees.
    rule_id = "SEC003" if source == "zip" and covered else "SEC004"
    return make_issue(rule_id, [Location(path)], {"name": PurePosixPath(path).name})


def _gitignore_issue(project: ProjectFiles, report: SecurityReport, gitignores: list[str]) -> Issue | None:
    if not gitignores:
        return make_issue("SEC005", [Location(".gitignore")])
    if not report.gitignore_covers_env and (uses_environment(project) or report.env_committed):
        return make_issue("SEC006", [Location(gitignores[0])])
    return None


def check_env_files(project: ProjectFiles, source: str, report: SecurityReport) -> list[Issue]:
    """Committed .env files with values, and whether .gitignore protects them."""
    gitignores = project.by_name(".gitignore")
    gitignore_lines = "\n".join(project.text(p) or "" for p in gitignores).splitlines()
    report.has_gitignore = bool(gitignores)
    report.gitignore_covers_env = any(line.strip().lstrip("/") in ENV_IGNORE_PATTERNS for line in gitignore_lines)
    report.env_committed = [p for p in project.paths if _is_env_file(p)]

    issues = [
        _env_file_issue(path, source, report.gitignore_covers_env)
        for path in report.env_committed
        if _env_has_values(project.text(path) or "")
    ]
    if gitignore_issue := _gitignore_issue(project, report, gitignores):
        issues.append(gitignore_issue)
    return issues


# --- Dangerous calls (AST) ------------------------------------------------------

def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    func = node.func
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


def _kwarg(node: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in node.keywords if kw.arg == name), None)


def _is_true(expr: ast.expr | None) -> bool:
    return isinstance(expr, ast.Constant) and expr.value is True


def _is_dynamic_string(expr: ast.expr) -> bool:
    if isinstance(expr, ast.JoinedStr):
        return True
    if isinstance(expr, ast.BinOp):
        return isinstance(expr.op, (ast.Add, ast.Mod))
    return isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "format"


def _unsafe_yaml(node: ast.Call) -> bool:
    loader = _kwarg(node, "Loader")
    if loader is None and len(node.args) > 1:
        loader = node.args[1]
    return "Safe" not in (ast.unparse(loader) if loader is not None else "")


def _verify_disabled(node: ast.Call) -> bool:
    verify = _kwarg(node, "verify")
    return isinstance(verify, ast.Constant) and verify.value is False


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "request", "head"}
SQL_METHODS = {"execute", "executemany", "executescript", "raw"}

# (rule id, predicate on (call node, dotted name, last name segment)); first match wins.
CALL_RULES = (
    ("SEC010", lambda n, name, short: name in {"eval", "exec", "builtins.eval", "builtins.exec"}),
    ("SEC011", lambda n, name, short: name in {"pickle.load", "pickle.loads", "cPickle.loads", "marshal.loads", "dill.loads"}),
    ("SEC012", lambda n, name, short: name == "yaml.load" and _unsafe_yaml(n)),
    ("SEC013", lambda n, name, short: name in {"os.system", "os.popen"} or (name.startswith("subprocess.") and _is_true(_kwarg(n, "shell")))),
    ("SEC014", lambda n, name, short: short in SQL_METHODS and bool(n.args) and _is_dynamic_string(n.args[0])),
    ("SEC015", lambda n, name, short: short in HTTP_METHODS and _verify_disabled(n)),
    ("SEC016", lambda n, name, short: short == "run" and _is_true(_kwarg(n, "debug"))),
    ("SEC017", lambda n, name, short: name in {"hashlib.md5", "hashlib.sha1"} and _kwarg(n, "usedforsecurity") is None),
)


def classify_call(node: ast.Call) -> str | None:
    """Rule id of the first dangerous-call rule this call matches, else None."""
    name = _call_name(node)
    short = name.rsplit(".", 1)[-1]
    return next((rule_id for rule_id, matches in CALL_RULES if matches(node, name, short)), None)


def _is_debug_setting(node: ast.AST) -> bool:
    return isinstance(node, ast.Assign) and _is_true(node.value) and any(isinstance(t, ast.Name) and t.id == "DEBUG" for t in node.targets)


def _rule_for_node(node: ast.AST, is_settings: bool) -> str | None:
    if isinstance(node, ast.Call):
        return classify_call(node)
    return "SEC016" if is_settings and _is_debug_setting(node) else None


def scan_dangerous_calls(project: ProjectFiles) -> list[Issue]:
    """eval/exec, shell commands, string-built SQL, unsafe deserialisation and friends."""
    hits: dict[str, list[Location]] = defaultdict(list)
    for path, tree in project.parsed_python(include_tests=False):
        is_settings = PurePosixPath(path).name == "settings.py"
        for node in ast.walk(tree):
            if rule_id := _rule_for_node(node, is_settings):
                hits[rule_id].append(Location(path, node.lineno))
    return [_grouped(rule_id, locations, source="ast", confidence="medium") for rule_id, locations in hits.items()]


# --- Bandit -------------------------------------------------------------------------

SEVERITY_MAP = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
CONFIDENCE_MAP = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}


def _bandit_title(test_id: str, text: str, count: int) -> str:
    short = text.split(". ")[0].strip().rstrip(".")
    if len(short) > 70:
        short = short[:67].rstrip() + "…"
    return f"Bandit {test_id}: {short}" + (f" ({count} yer)" if count > 1 else "")


def _call_bandit(project: ProjectFiles, report: SecurityReport, targets: list[str]) -> list[dict]:
    cmd = [sys.executable, "-m", "bandit", "-f", "json", "-q", "-s", ",".join(sorted(BANDIT_SKIP)), *targets]
    try:
        proc = subprocess.run(cmd, cwd=project.root, capture_output=True, text=True, timeout=TOOL_TIMEOUT_SECONDS)
        data = json.loads(proc.stdout or "{}")
    except subprocess.TimeoutExpired:
        report.bandit_error = "Bandit zaman aşımına uğradı."
        return []
    except (OSError, json.JSONDecodeError) as exc:
        report.bandit_error = f"Bandit çalıştırılamadı: {exc.__class__.__name__}"
        return []
    report.bandit_ran = True
    return data.get("results", [])


def _bandit_issue(test_id: str, results: list[dict]) -> Issue:
    first = results[0]
    severity = SEVERITY_MAP.get(first["issue_severity"], "low")
    if first["issue_confidence"] == "LOW":
        severity = "low"
    return Issue(
        rule_id=f"BANDIT-{test_id}", title=_bandit_title(test_id, first["issue_text"], len(results)),
        severity=severity, category="security",
        explanation=f"{first['issue_text']}{POTENTIAL_NOTE}",
        recommendation=f"Bulunan satırları inceleyin. Ayrıntı: {first.get('more_info', 'https://bandit.readthedocs.io')}",
        effort_minutes=10 + 5 * min(len(results) - 1, 6),
        locations=[Location(r["filename"].removeprefix("./"), r["line_number"]) for r in results][:MAX_LOCATIONS],
        source="bandit", confidence=CONFIDENCE_MAP.get(first["issue_confidence"], "low"),
        snippet=mask_secrets(first.get("code", "")).strip()[:400] or None, count=len(results),
    )


def run_bandit(project: ProjectFiles, report: SecurityReport, already_flagged: set[tuple[str, int]]) -> list[Issue]:
    """Bandit findings not already reported by our own rules, grouped by check id."""
    targets = [p for p in project.source_python_files if project.tree(p) is not None]
    if not targets:
        return []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for result in _call_bandit(project, report, targets):
        if (result["filename"].removeprefix("./"), result["line_number"]) not in already_flagged:
            grouped[result["test_id"]].append(result)
    report.bandit_issues = sum(len(results) for results in grouped.values())
    return [_bandit_issue(test_id, results) for test_id, results in grouped.items()]


# --- Confirmed data flows (taint analysis) ---------------------------------------------------------

TAINT_RULES = {
    "code": "TNT001", "command": "TNT002", "sql": "TNT003", "path": "TNT004", "deserialize": "TNT005",
    "template": "TNT006", "ssrf": "TNT007", "redirect": "TNT008", "xss": "TNT009",
}
# A confirmed flow replaces the "potential risk" pattern finding on the same line.
SUPERSEDED = {"code": {"SEC010"}, "command": {"SEC013"}, "sql": {"SEC014"}, "deserialize": {"SEC011", "SEC012"}}
DOWNGRADE = {"critical": "high", "high": "medium", "medium": "low", "low": "low", "info": "info"}
LOCAL_NOTE = (" Girdi konsoldan (`input()` / `sys.argv`) geliyor; yalnızca programı çalıştıran kişi kontrol eder. "
              "Uzak bir saldırı yolu değildir ama bu kod bir web uygulamasına taşınırsa doğrudan açığa dönüşür.")


def _taint_issue(kind: str, remote: bool, flows: list[TaintFlow]) -> Issue:
    more = f" (ve {len(flows) - 1} akış daha)" if len(flows) > 1 else ""
    issue = make_issue(
        TAINT_RULES[kind], [Location(f.file, f.line) for f in flows][:MAX_LOCATIONS], {"flow": describe(flows[0]) + more},
        source="taint", confidence="high", count=len(flows),
        snippet="\n".join(f"{f.file}:{f.line}  {f.sink}" for f in flows[:5]),
    )
    issue.effort_minutes += 10 * min(len(flows) - 1, 6)
    if not remote:
        issue.severity = DOWNGRADE[issue.severity]
        issue.title += " — yerel girdi"
        issue.explanation += LOCAL_NOTE
        issue.confidence = "medium"
    return issue


def taint_issues(flows: list[TaintFlow]) -> list[Issue]:
    groups: dict[tuple[str, bool], list[TaintFlow]] = defaultdict(list)
    for flow in flows:
        groups[(flow.kind, flow.remote)].append(flow)
    return [_taint_issue(kind, remote, group) for (kind, remote), group in groups.items()]


def drop_superseded(issues: list[Issue], flows: list[TaintFlow]) -> list[Issue]:
    """Remove pattern-rule locations that a confirmed flow already explains."""
    confirmed = {(f.file, f.line, rule) for f in flows for rule in SUPERSEDED.get(f.kind, ())}
    kept = []
    for issue in issues:
        remaining = [loc for loc in issue.locations if (loc.file, loc.line, issue.rule_id) not in confirmed]
        if not remaining and issue.locations:
            continue
        if len(remaining) < len(issue.locations):
            issue.count = max(issue.count - (len(issue.locations) - len(remaining)), len(remaining))
            issue.locations = remaining
        kept.append(issue)
    return kept


def analyze_security(project: ProjectFiles, source: str, run_tools: bool = True) -> tuple[SecurityReport, list[Issue]]:
    """All security checks; `run_tools=False` skips the Bandit subprocess (fast tests)."""
    report = SecurityReport()
    issues = scan_secrets(project)
    issues += entropy_issues(project, {(loc.file, loc.line) for i in issues for loc in i.locations})
    report.secrets_found = sum(i.count for i in issues)
    issues += check_env_files(project, source, report)
    dangerous = scan_dangerous_calls(project)
    report.dangerous_calls = sum(i.count for i in dangerous)
    report.taint_flows, report.taint_functions = find_taint_flows(project)
    issues = drop_superseded(issues + dangerous, report.taint_flows) + taint_issues(report.taint_flows)
    if run_tools:
        flagged = {(loc.file, loc.line) for i in issues for loc in i.locations if loc.line}
        issues += run_bandit(project, report, flagged)
    return report, issues
