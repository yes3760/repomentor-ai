"""Code quality metrics: Radon (complexity, maintainability, raw), Ruff, AST rules, duplication."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from radon.complexity import cc_visit
from radon.metrics import mi_rank, mi_visit
from radon.raw import analyze as raw_analyze

from repomentor.analyzer.code_metrics import (
    COGNITIVE_VERY_HIGH,
    annotation_counts,
    cognitive_complexity,
    find_clones,
)
from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.rules import make_issue
from repomentor.models.analysis_result import DuplicateBlock, FunctionMetric, QualityReport
from repomentor.models.issue import Issue, Location
from repomentor.utils.constants import (
    DUPLICATE_WINDOW,
    HIGH_COMPLEXITY,
    LONG_FILE_LINES,
    LONG_FUNCTION_LINES,
    MAX_PARAMS,
    TOOL_TIMEOUT_SECONDS,
    VERY_HIGH_COMPLEXITY,
)

RUFF_SELECT = "F,E4,E7,B,W6"
RUFF_IGNORE = "E722"          # bare except is reported by our own AST rule
RUFF_SEVERITY = {
    "F821": "medium", "F822": "medium", "F823": "medium", "B006": "medium", "B023": "medium",
}
RUFF_HINTS = {
    "F401": "Kullanılmayan import'ları silin (`ruff check --fix` otomatik yapar).",
    "F841": "Atanıp hiç kullanılmayan değişkenleri kaldırın.",
    "F821": "Tanımsız isim kullanımı çalışma anında `NameError` verir; yazım hatası veya eksik import olabilir.",
    "F811": "Aynı isim iki kez tanımlanmış; biri diğerini ezer.",
    "F403": "`from x import *` yerine kullandığınız isimleri açıkça import edin.",
    "F541": "Yer tutucu içermeyen f-string'lerin başındaki `f`'yi kaldırın.",
    "E402": "Import'ları dosyanın en üstüne taşıyın.",
    "E711": "`== None` yerine `is None` kullanın.",
    "E712": "`== True` yerine doğrudan koşulu kullanın.",
    "E731": "Değişkene atanan `lambda` yerine `def` ile isimli fonksiyon yazın.",
    "E741": "`l`, `O`, `I` gibi okunması zor değişken isimlerinden kaçının.",
    "B006": "Değiştirilebilir varsayılan argüman (`def f(x=[])`) çağrılar arasında paylaşılır; `None` kullanıp fonksiyon içinde oluşturun.",
    "B007": "Kullanılmayan döngü değişkenini `_` olarak adlandırın.",
    "B008": "Varsayılan argümanda fonksiyon çağrısı tanımlanma anında bir kez çalışır.",
    "B023": "Döngü içinde tanımlanan fonksiyon döngü değişkenini yakalıyor; değer beklenmedik biçimde son turdaki değer olabilir. Değeri argüman olarak geçirin.",
    "B904": "`except` içinde yeni hata fırlatırken `raise ... from exc` kullanın; asıl hata kaybolmasın.",
    "B905": "`zip()` çağrısına `strict=True` ekleyin; listeler farklı uzunluktaysa hata sessizce gizlenmesin.",
}


# --- Metrics ------------------------------------------------------------------------

def complexity_band(value: int) -> str:
    if value <= 5:
        return "Düşük (1-5)"
    if value <= 10:
        return "Orta (6-10)"
    if value <= 20:
        return "Yüksek (11-20)"
    return "Çok yüksek (21+)"


def _function_params(tree: ast.Module) -> dict[int, int]:
    params: dict[int, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            names = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]
            params[node.lineno] = len([n for n in names if n not in {"self", "cls"}])
    return params


def _radon_blocks(source: str) -> list:
    """Functions and methods. Radon lists methods both inside their Class block and
    again as top-level Function entries, so Class blocks are skipped to avoid double counting."""
    try:
        blocks = cc_visit(source)
    except Exception:  # radon raises assorted errors on unusual syntax
        return []
    return [block for block in blocks if not hasattr(block, "methods")]


def _cognitive_by_line(tree: ast.Module, text: str) -> dict[int, int]:
    lines = text.splitlines()
    return {
        node.lineno: cognitive_complexity(node, lines)
        for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def collect_functions(project: ProjectFiles) -> list[FunctionMetric]:
    """Radon cyclomatic complexity + our cognitive complexity for every source function."""
    metrics: list[FunctionMetric] = []
    for path, tree in project.parsed_python(include_tests=False):
        params = _function_params(tree)
        cognitive = _cognitive_by_line(tree, project.texts[path])
        for fn in _radon_blocks(project.texts[path]):
            name = f"{fn.classname}.{fn.name}" if getattr(fn, "classname", None) else fn.name
            metrics.append(FunctionMetric(
                file=path, name=name, line=fn.lineno, length=fn.endline - fn.lineno + 1,
                complexity=fn.complexity, params=params.get(fn.lineno, 0), cognitive=cognitive.get(fn.lineno, 0),
            ))
    return metrics


def _raw_metrics(project: ProjectFiles, report: QualityReport) -> None:
    for path in project.python_files:
        try:
            raw = raw_analyze(project.texts[path])
        except Exception:
            continue
        report.total_lines += raw.loc
        report.sloc += raw.sloc
        report.comment_lines += raw.comments + raw.multi
        report.blank_lines += raw.blank


def _maintainability(project: ProjectFiles, report: QualityReport) -> None:
    rows = []
    for path in project.source_python_files:
        text = project.texts[path]
        if project.tree(path) is None or not text.strip():
            continue
        try:
            mi = mi_visit(text, multi=True)
        except Exception:
            continue
        rows.append({"file": path, "mi": round(mi, 1), "rank": mi_rank(mi), "lines": text.count("\n") + 1})
    rows.sort(key=lambda m: m["mi"])
    report.maintainability = rows
    if rows:
        total_lines = sum(m["lines"] for m in rows)
        report.avg_maintainability = round(sum(m["mi"] * m["lines"] for m in rows) / total_lines, 1)


def _per_file(project: ProjectFiles, functions: list[FunctionMetric]) -> dict[str, dict]:
    stats = {p: {"cognitive": 0, "functions": 0, "lines": len(project.texts[p].splitlines())} for p in project.source_python_files}
    for fn in functions:
        stats[fn.file]["cognitive"] += fn.cognitive
        stats[fn.file]["functions"] += 1
    return stats


def _difficulty_counts(report: QualityReport, functions: list[FunctionMetric]) -> None:
    very = [f for f in functions if f.complexity >= VERY_HIGH_COMPLEXITY or f.cognitive >= COGNITIVE_VERY_HIGH]
    report.very_hard_functions = len(very)
    report.hard_functions = sum(1 for f in functions if f.difficulty >= 1) - len(very)


def _function_summary(project: ProjectFiles, report: QualityReport) -> list[FunctionMetric]:
    functions = collect_functions(project)
    report.functions = len(functions)
    report.classes = sum(isinstance(n, ast.ClassDef) for _, t in project.parsed_python(include_tests=False) for n in ast.walk(t))
    if functions:
        report.avg_function_length = round(sum(f.length for f in functions) / len(functions), 1)
        report.avg_complexity = round(sum(f.complexity for f in functions) / len(functions), 2)
        report.avg_cognitive = round(sum(f.cognitive for f in functions) / len(functions), 2)
    report.complexity_distribution = dict(Counter(complexity_band(f.complexity) for f in functions))
    _difficulty_counts(report, functions)
    report.long_functions = sum(1 for f in functions if f.length > LONG_FUNCTION_LINES)
    report.longest_functions = sorted(functions, key=lambda f: -f.length)[:10]
    report.most_complex = sorted(functions, key=lambda f: (-f.difficulty, -f.cognitive))[:10]
    report.annotated, report.annotatable = annotation_counts(project)
    report.per_file = _per_file(project, functions)
    return functions


# --- Duplicate detection ------------------------------------------------------------

TRIVIAL_LINES = {"else:", "try:", "pass", "return", "break", "continue"}
SKIPPED_PREFIXES = ("#", "import ", "from ", '"""', "'''", "@")


def _normalised_rows(text: str) -> list[tuple[int, str]]:
    rows = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if len(line) >= 4 and not line.startswith(SKIPPED_PREFIXES) and line not in TRIVIAL_LINES:
            rows.append((lineno, re.sub(r"\s+", " ", line)))
    return rows


def _window_hash(rows: list[tuple[int, str]]) -> str:
    return hashlib.md5("\n".join(t for _, t in rows).encode(), usedforsecurity=False).hexdigest()


def _distinct(occurrences: list[tuple[str, int]], window: int) -> list[tuple[str, int]]:
    """Drop overlapping occurrences inside the same file (repetitive lines)."""
    kept: list[tuple[str, int]] = []
    for path, idx in occurrences:
        if all(path != q or abs(idx - j) >= window for q, j in kept):
            kept.append((path, idx))
    return kept


def _block_length(keys: dict[str, list[str]], start: tuple[str, int], occurrences: list[tuple[str, int]]) -> int:
    """How many consecutive windows all occurrences share, starting at `start`."""
    path, i = start
    extend = 1
    while i + extend < len(keys[path]):
        target = keys[path][i + extend]
        if not all(idx + extend < len(keys[p]) and keys[p][idx + extend] == target for p, idx in occurrences):
            break
        extend += 1
    return extend


def _window_index(rows: dict[str, list[tuple[int, str]]], window: int) -> tuple[dict[str, list[str]], dict[str, list[tuple[str, int]]]]:
    """Hash every `window`-line slice; return per-file hashes and hash -> occurrences."""
    keys = {p: [_window_hash(r[i:i + window]) for i in range(len(r) - window + 1)] for p, r in rows.items()}
    occurrences: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for path, file_keys in keys.items():
        for i, key in enumerate(file_keys):
            occurrences[key].append((path, i))
    return keys, occurrences


def find_duplicates(project: ProjectFiles, window: int = DUPLICATE_WINDOW, limit: int = 15) -> list[DuplicateBlock]:
    """Detect copy-pasted blocks of >= `window` normalised lines."""
    rows = {p: r for p in project.source_python_files if len(r := _normalised_rows(project.texts[p])) >= window}
    keys, occurrences = _window_index(rows, window)
    covered: set[tuple[str, int]] = set()
    blocks: list[DuplicateBlock] = []
    for path, i in ((p, i) for p, file_keys in keys.items() for i in range(len(file_keys))):
        distinct = _distinct(occurrences[keys[path][i]], window)
        if (path, i) in covered or len(distinct) < 2:
            continue
        extend = _block_length(keys, (path, i), distinct)
        covered.update((p, idx + k) for p, idx in distinct for k in range(extend + window - 1))
        blocks.append(DuplicateBlock(
            lines=extend + window - 1,
            occurrences=[f"{p}:{rows[p][idx][0]}" for p, idx in distinct],
            preview="\n".join(t for _, t in rows[path][i:i + min(window, 8)]),
        ))
        if len(blocks) >= limit:
            break
    return blocks


# --- Ruff ---------------------------------------------------------------------------------

def run_ruff(project: ProjectFiles, report: QualityReport) -> list[dict]:
    targets = [p for p in project.python_modules if project.tree(p) is not None]   # Ruff reads files from disk
    if not targets:
        return []
    cmd = [
        sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache", "--exit-zero",
        "--output-format", "json", "--select", RUFF_SELECT, "--ignore", RUFF_IGNORE, *targets,
    ]
    try:
        proc = subprocess.run(cmd, cwd=project.root, capture_output=True, text=True, timeout=TOOL_TIMEOUT_SECONDS)
        results = json.loads(proc.stdout or "[]")
    except subprocess.TimeoutExpired:
        report.ruff_error = "Ruff zaman aşımına uğradı."
        return []
    except (OSError, json.JSONDecodeError) as exc:
        report.ruff_error = f"Ruff çalıştırılamadı: {exc.__class__.__name__}"
        return []
    report.ruff_ran = True
    root = Path(project.root).resolve()
    for r in results:
        try:
            r["relpath"] = Path(r["filename"]).resolve().relative_to(root).as_posix()
        except ValueError:
            r["relpath"] = r["filename"]
    return results


def _ruff_title(code: str, message: str, count: int) -> str:
    short = message.replace("`", "").split(". ")[0].strip()
    if len(short) > 70:
        short = short[:67].rstrip() + "…"
    return f"Ruff {code}: {short} ({count} yer)"


def _ruff_summary(by_code: dict[str, list[dict]]) -> dict[str, dict]:
    ranked = sorted(by_code.items(), key=lambda kv: -len(kv[1]))
    return {
        code: {"count": len(rs), "message": rs[0]["message"], "url": rs[0].get("url"), "sample": f"{rs[0]['relpath']}:{rs[0]['location']['row']}"}
        for code, rs in ranked
    }


def _ruff_issue(code: str, results: list[dict]) -> Issue:
    first = results[0]
    fixable = bool(first.get("fix"))
    hint = RUFF_HINTS.get(code, f"Kural açıklaması: {first.get('url') or 'https://docs.astral.sh/ruff/rules/'}")
    many = len(results) > 1
    return Issue(
        rule_id=f"RUFF-{code}", title=_ruff_title(code, first["message"], len(results)),
        severity=RUFF_SEVERITY.get(code, "low"), category="quality",
        explanation=f"{len(results)} yerde aynı lint uyarısı. Örnek: {first['message']}" if many else first["message"],
        recommendation=hint + (" `ruff check --fix` ile otomatik düzeltilebilir." if fixable else ""),
        effort_minutes=5 if fixable else min(5 + 2 * len(results), 60),
        locations=[Location(r["relpath"], r["location"]["row"]) for r in results][:10], source="ruff", count=len(results),
    )


def _ruff_issues(project: ProjectFiles, report: QualityReport) -> list[Issue]:
    results = run_ruff(project, report)
    report.ruff_total = len(results)
    by_code: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_code[r["code"] or "SYNTAX"].append(r)
    report.ruff_by_code = _ruff_summary(by_code)
    in_source = {code: [r for r in rs if not project.is_test(r["relpath"])] for code, rs in by_code.items() if code != "SYNTAX"}
    ranked = sorted(((c, rs) for c, rs in in_source.items() if rs), key=lambda kv: (kv[0] not in RUFF_SEVERITY, -len(kv[1])))
    return [_ruff_issue(code, rs) for code, rs in ranked[:8]]


# --- Issue builders -----------------------------------------------------------------------

def _complexity_issues(report: QualityReport) -> list[Issue]:
    complex_fns = [f for f in report.most_complex if f.difficulty >= 1]
    issues = []
    for fn in complex_fns[:5]:
        very = fn.complexity >= VERY_HIGH_COMPLEXITY or fn.cognitive >= COGNITIVE_VERY_HIGH
        values = {"name": fn.name, "complexity": fn.complexity, "cognitive": fn.cognitive}
        issues.append(make_issue(
            "QLT001", [Location(fn.file, fn.line)], values, source="radon",
            severity="high" if very else "medium", effort_minutes=90 if very else 45,
        ))
    if extra := complex_fns[5:]:
        issues.append(make_issue("QLT011", [Location(f.file, f.line) for f in extra], {"count": len(extra)}, source="radon", count=len(extra)))
    return issues


def _long_function_issues(report: QualityReport) -> list[Issue]:
    flagged = {(f.file, f.line) for f in report.most_complex[:5] if f.complexity >= HIGH_COMPLEXITY}
    long_fns = [f for f in report.longest_functions if f.length > LONG_FUNCTION_LINES and (f.file, f.line) not in flagged]
    issues = []
    for fn in long_fns[:4]:
        big = fn.length > 100
        values = {"name": fn.name, "length": fn.length, "limit": LONG_FUNCTION_LINES}
        issues.append(make_issue("QLT002", [Location(fn.file, fn.line)], values, source="ast",
                                 severity="medium" if big else "low", effort_minutes=60 if big else 30))
    return issues


def _size_issues(project: ProjectFiles, report: QualityReport, functions: list[FunctionMetric]) -> list[Issue]:
    issues = _long_function_issues(report)
    if many_params := [f for f in functions if f.params > MAX_PARAMS]:
        locations = [Location(f.file, f.line) for f in many_params][:10]
        issues.append(make_issue("QLT003", locations, {"count": len(many_params), "limit": MAX_PARAMS}, source="ast", count=len(many_params)))
    sizes = {p: project.texts[p].count("\n") + 1 for p in project.source_python_files}
    big_files = sorted(((p, n) for p, n in sizes.items() if n > LONG_FILE_LINES), key=lambda x: -x[1])[:3]
    issues += [make_issue("QLT004", [Location(path)], {"path": path, "lines": lines}, source="ast") for path, lines in big_files]
    return issues


def _health_issues(project: ProjectFiles, report: QualityReport) -> list[Issue]:
    low_mi = [m for m in report.maintainability if m["rank"] == "C"][:3]
    issues = [make_issue("QLT005", [Location(m["file"])], {"path": m["file"], "mi": m["mi"]}, source="radon") for m in low_mi]
    if report.syntax_errors:
        count = len(report.syntax_errors)
        issues.append(make_issue(
            "QLT006", [Location(p) for p in project.syntax_errors][:10], {"count": count},
            effort_minutes=15 * min(count, 6), snippet="\n".join(report.syntax_errors[:5]), count=count,
        ))
    return issues


def _hygiene_issues(project: ProjectFiles, report: QualityReport) -> list[Issue]:
    bare: list[Location] = []
    globals_: list[Location] = []
    for path, tree in project.parsed_python(include_tests=False):
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                bare.append(Location(path, node.lineno))
            elif isinstance(node, ast.Global):
                globals_.append(Location(path, node.lineno))
        report.todo_count += len(re.findall(r"#\s*(TODO|FIXME|XXX|HACK)\b", project.texts[path]))
    report.bare_excepts = len(bare)

    issues = []
    if bare:
        issues.append(make_issue(
            "QLT007", bare[:10], {"count": len(bare)}, source="ast", count=len(bare),
            severity="medium" if len(bare) >= 3 else "low", effort_minutes=5 * min(len(bare), 10),
        ))
    if len(globals_) >= 3:
        issues.append(make_issue("QLT008", globals_[:10], {"count": len(globals_)}, source="ast", count=len(globals_)))
    if report.todo_count >= 10:
        issues.append(make_issue("QLT010", values={"count": report.todo_count}, count=report.todo_count))
    return issues


def _parse_location(occurrence: str) -> Location:
    path, line = occurrence.rsplit(":", 1)
    return Location(path, int(line))


def _duplicate_issues(report: QualityReport) -> list[Issue]:
    if not report.duplicates:
        return []
    total = sum(b.lines for b in report.duplicates)
    locations = [_parse_location(occ) for b in report.duplicates[:5] for occ in b.occurrences[:2]]
    return [make_issue(
        "QLT009", locations, {"count": len(report.duplicates), "lines": total}, source="ast", confidence="medium",
        severity="medium" if total > 60 else "low", effort_minutes=min(20 * len(report.duplicates), 180),
        snippet=report.duplicates[0].preview, count=len(report.duplicates),
    )]


def _clone_issues(report: QualityReport) -> list[Issue]:
    if not report.clones:
        return []
    members = [m for clone in report.clones for m in clone.members]
    shown = "; ".join(" ↔ ".join(f"`{m.split(' ', 1)[1]}`" for m in clone.members) for clone in report.clones[:3])
    locations = [_parse_location(m.split(" ", 1)[0]) for m in members][:10]
    return [make_issue(
        "QLT013", locations, {"count": len(members), "members": shown}, source="ast", confidence="medium",
        severity="medium" if len(members) >= 4 else "low", effort_minutes=min(25 * len(report.clones), 180), count=len(members),
    )]


def _covered_lines(report: QualityReport) -> dict[str, list[tuple[int, int]]]:
    covered: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for block in report.duplicates:
        for occurrence in block.occurrences:
            location = _parse_location(occurrence)
            covered[location.file].append((location.line, location.line + block.lines))
    return covered


def analyze_quality(project: ProjectFiles, run_tools: bool = True) -> tuple[QualityReport, list[Issue]]:
    """Metrics plus issues; `run_tools=False` skips the Ruff subprocess (fast tests)."""
    report = QualityReport(python_files=len(project.python_files))
    for path in project.python_files:
        project.tree(path)  # parse once; fills project.syntax_errors
    report.syntax_errors = [f"{p} – {msg}" for p, msg in project.syntax_errors.items()]

    _raw_metrics(project, report)
    _maintainability(project, report)
    functions = _function_summary(project, report)
    report.duplicates = find_duplicates(project)
    report.clones = find_clones(project, _covered_lines(report))

    issues = _complexity_issues(report)
    issues += _size_issues(project, report, functions)
    issues += _health_issues(project, report)
    issues += _hygiene_issues(project, report)
    issues += _duplicate_issues(report)
    issues += _clone_issues(report)
    if run_tools:
        issues += _ruff_issues(project, report)
    return report, issues
