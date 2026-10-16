"""Safe, mechanical fixes delivered as a unified-diff patch.

RepoMentor never writes to the analysed project: it produces `repomentor-fixes.patch`
which the user reviews and applies with `git apply` (or `patch -p1`).

Only fixes that cannot break a working program are made:
* `yaml.load(x)` → `yaml.safe_load(x)` (SEC012; PyYAML ≥ 6 even raises without a Loader),
* bare `except:` → `except Exception:` (QLT007; Ctrl+C and `sys.exit()` are no longer swallowed),
* `.gitignore` created, or `.env` added to it (SEC005 / SEC006),
* `.env.example` listing the environment variables the code reads, values empty (DOC009),
* Ruff's *safe* fixes for a few rules (unused imports outside `__init__.py`, f-strings without
  placeholders, `is` against a literal, stray semicolons). Ruff's "unsafe" fixes, such as
  `== None` → `is None` (different on pandas objects), are left to the user.
* Confirmed SQL and shell-command injection flows rewritten as a parameterised query or an
  argument list (TNT003 / TNT002, see `security_fixes`). Each rewrite is applied on its own and
  the taint analysis runs again; it is kept only if the flow is gone.

Files are re-read as bytes so line endings survive, every fixed Python file must still parse,
and non-UTF-8 files are skipped rather than re-encoded.
"""

from __future__ import annotations

import ast
import difflib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.security_fixes import FORMAT_DRIVERS, QMARK_DRIVERS, CallFix, call_fixes, imported_modules
from repomentor.analyzer.taint import find_taint_flows
from repomentor.analyzer.taint.sources import call_name
from repomentor.models.analysis_result import FileFix, FixReport, TaintFlow
from repomentor.models.issue import Issue
from repomentor.utils.constants import TOOL_TIMEOUT_SECONDS

MAX_INJECTION_FIXES = 10                 # each one re-runs the taint analysis
LINE = re.compile(r"[^\r\n]*(?:\r\n|\n|\r)|[^\r\n]+\Z")
BARE_EXCEPT = re.compile(r"except\s*:")
RUFF_FIXES = {
    "F401": "kullanılmayan import silindi",
    "F541": "yer tutucusu olmayan f-string düz metne çevrildi",
    "F632": "sabitle `is` karşılaştırması `==` yapıldı",
    "E703": "gereksiz noktalı virgül silindi",
}
ENV_READERS = {"os.getenv", "getenv", "os.environ.get", "environ.get"}
ENV_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", re.M)
GITIGNORE = """# Python
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/

# Gizli ayarlar: yalnızca boş şablon depoya girer
.env
.env.*
!.env.example
"""


@dataclass
class _Edit:
    line: int        # 1-based
    start: int       # character columns within the line
    end: int         # character column on `end_line` (the same line unless the edit spans several)
    text: str
    rule: str
    change: str
    end_line: int | None = None


def _lines(text: str) -> list[str]:
    return LINE.findall(text)


def _char_col(line: str, byte_col: int) -> int:
    """AST columns count UTF-8 bytes; `ğ` is two bytes but one character."""
    return len(line.encode("utf-8")[:byte_col].decode("utf-8", errors="ignore"))


def _read(project: ProjectFiles, path: str) -> str | None:
    try:
        return (Path(project.root) / path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# --- Python source edits ------------------------------------------------------------------------------------

def _yaml_edits(tree: ast.Module, lines: list[str]) -> list[_Edit]:
    edits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and call_name(node.func) == "yaml.load" and len(node.args) == 1 and not node.keywords):
            continue
        line = lines[node.func.end_lineno - 1]
        end = _char_col(line, node.func.end_col_offset)
        if line[end - 4:end] == "load":
            edits.append(_Edit(node.func.end_lineno, end - 4, end, "safe_load", "SEC012",
                               f"satır {node.lineno}: `yaml.load()` → `yaml.safe_load()` (dosyadan nesne/kod oluşturulamaz)"))
    return edits


def _except_edits(tree: ast.Module, lines: list[str]) -> list[_Edit]:
    edits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            line = lines[node.lineno - 1]
            col = _char_col(line, node.col_offset)
            if match := BARE_EXCEPT.match(line, col):
                edits.append(_Edit(node.lineno, col, match.end(), "except Exception:", "QLT007",
                                   f"satır {node.lineno}: çıplak `except:` → `except Exception:` (Ctrl+C ve `sys.exit()` yutulmaz)"))
    return edits


def _apply(text: str, edits: list[_Edit]) -> str:
    """Apply edits back to front so earlier positions stay valid; edits may span lines."""
    offsets = [0]
    for line in _lines(text):
        offsets.append(offsets[-1] + len(line))
    for edit in sorted(edits, key=lambda e: (e.line, e.start), reverse=True):
        start = offsets[edit.line - 1] + edit.start
        end = offsets[(edit.end_line or edit.line) - 1] + edit.end
        text = text[:start] + edit.text + text[end:]
    return text


# --- Injection fixes ------------------------------------------------------------------------------------------

def _call_edit(fix: CallFix, lines: list[str]) -> _Edit:
    node = fix.node
    start = _char_col(lines[node.lineno - 1], node.col_offset)
    end = _char_col(lines[node.end_lineno - 1], node.end_col_offset)
    return _Edit(node.lineno, start, end, fix.text, fix.rule, fix.change + " (doğrulandı)", end_line=node.end_lineno)


def _import_anchor(tree: ast.Module) -> int:
    """The line after which a new import goes: the last top-level import, else the docstring, else the top."""
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    if imports:
        return imports[-1].end_lineno
    first = tree.body[0] if tree.body else None
    is_docstring = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)
    return first.end_lineno if is_docstring else 0


def _import_edit(tree: ast.Module, lines: list[str]) -> _Edit:
    """`import subprocess` on its own line, in the file's own line-ending style."""
    after = _import_anchor(tree)
    newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    if after < len(lines):
        return _Edit(after + 1, 0, 0, f"import subprocess{newline}", "TNT002", "")
    last = lines[-1]                       # the anchor is the last line: append after it
    ending = "" if last.endswith(("\n", "\r")) else newline
    return _Edit(len(lines), len(last), len(last), f"{ending}import subprocess{newline}", "TNT002", "")


def _flow_count(project: ProjectFiles, path: str, text: str, kind: str) -> int:
    """Confirmed flows of `kind` in `path` once its source is `text` (the rest of the project unchanged)."""
    variant = ProjectFiles(root=project.root, files=project.files, texts={**project.texts, path: text}, notebooks=project.notebooks)
    flows, _ = find_taint_flows(variant)
    return sum(flow.file == path and flow.kind == kind for flow in flows)


class _InjectionFixer:
    """Rewrites for one file's SQL / shell sinks, each kept only after the taint analysis confirms it."""

    def __init__(self, project: ProjectFiles, path: str, original: str, drivers: set[str]):
        self.project, self.path, self.original = project, path, original
        self.tree, self.lines = ast.parse(original), _lines(original)
        self.imported = imported_modules(self.tree)
        self.drivers = self.imported if self.imported & (QMARK_DRIVERS | FORMAT_DRIVERS) else drivers
        # only a module-level import makes `subprocess` visible in every function
        self.has_subprocess = any(isinstance(n, ast.Import) and any(a.name == "subprocess" and a.asname is None for a in n.names)
                                  for n in self.tree.body)

    def _sinks(self, flows: list[TaintFlow]) -> dict[int, set[str]]:
        """{line: kinds} of this file's direct sinks; flows through a helper in another file are not rewritten here."""
        sinks: dict[int, set[str]] = defaultdict(set)
        for flow in flows:
            if flow.file == self.path and flow.via is None:
                sinks[flow.line].add(flow.kind)
        return dict(sinks)

    def _with_import(self, fixes: list[CallFix]) -> list[_Edit]:
        edits = [_call_edit(fix, self.lines) for fix in fixes]
        if any(fix.needs_subprocess for fix in fixes) and not self.has_subprocess:
            edits.append(_import_edit(self.tree, self.lines))
        return edits

    def edits(self, flows: list[TaintFlow]) -> list[_Edit]:
        sinks = self._sinks(flows)
        fixes = call_fixes(self.tree, self.original, sinks, self.drivers) if sinks else []
        return self._with_import([fix for fix in fixes[:MAX_INJECTION_FIXES] if self._closes(fix)])

    def _closes(self, fix: CallFix) -> bool:
        fixed = _apply(self.original, self._with_import([fix]))
        before = _flow_count(self.project, self.path, self.original, fix.kind)
        return _parses(fixed) and _flow_count(self.project, self.path, fixed, fix.kind) < before


def _ruff_command(*extra: str) -> list[str]:
    return [sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache", "--exit-zero", "--select", ",".join(RUFF_FIXES), *extra]


def _ruff_fixable(project: ProjectFiles, paths: list[str]) -> dict[str, Counter]:
    """Safe Ruff fixes per file (one Ruff run over the whole project)."""
    try:
        proc = subprocess.run(_ruff_command("--output-format", "json", *paths), cwd=project.root,
                              capture_output=True, text=True, timeout=TOOL_TIMEOUT_SECONDS)
        results = json.loads(proc.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}
    root = Path(project.root).resolve()
    fixable: dict[str, Counter] = {}
    for result in results:
        if (result.get("fix") or {}).get("applicability") != "safe":
            continue
        path = Path(result["filename"]).resolve().relative_to(root).as_posix()
        fixable.setdefault(path, Counter())[result["code"]] += 1
    return fixable


def _ruff_fix(project: ProjectFiles, path: str, text: str) -> str | None:
    try:
        proc = subprocess.run(_ruff_command("--quiet", "--fix", "--stdin-filename", path, "-"), cwd=project.root,
                              input=text.encode("utf-8"), capture_output=True, timeout=TOOL_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.decode("utf-8") if proc.returncode == 0 and proc.stdout else None


def _ruff_changes(codes: Counter) -> list[str]:
    return [f"Ruff: {count} × {RUFF_FIXES[code]} ({code})" for code, count in sorted(codes.items())]


def _parses(text: str) -> bool:
    try:
        ast.parse(text)
    except (SyntaxError, ValueError):
        return False
    return True


def _source_edits(original: str, wanted: set[str]) -> list[_Edit]:
    tree, lines = ast.parse(original), _lines(original)
    return (_yaml_edits(tree, lines) if "SEC012" in wanted else []) + (_except_edits(tree, lines) if "QLT007" in wanted else [])


@dataclass
class _Context:
    """What every file's fix needs to know about the whole analysis."""

    wanted: set[str]
    ruff: dict[str, Counter]
    flows: list[TaintFlow]
    drivers: set[str]


def _patchable_source(project: ProjectFiles, path: str) -> str | None:
    """The file as on disk, if it parses and is what was analysed (a patch must match both)."""
    original = _read(project, path)
    same = original is not None and original == project.texts.get(path, original)
    return original if same and original and _parses(original) else None


def _python_fix(project: ProjectFiles, path: str, context: _Context) -> FileFix | None:
    original = _patchable_source(project, path)
    if original is None:
        return None
    edits = _source_edits(original, context.wanted) + _InjectionFixer(project, path, original, context.drivers).edits(context.flows)
    fixed = _apply(original, edits)
    changes, rules = [e.change for e in edits if e.change], {e.rule for e in edits}
    ruff_codes = context.ruff.get(path)
    if ruff_codes and (after_ruff := _ruff_fix(project, path, fixed)) not in (None, fixed):
        fixed = after_ruff
        changes += _ruff_changes(ruff_codes)
        rules |= {f"RUFF-{code}" for code in ruff_codes}
    if fixed == original or not _parses(fixed):
        return None
    return FileFix(path=path, diff=unified_diff(path, original, fixed), changes=changes, rules=sorted(rules))


# --- Project files ---------------------------------------------------------------------------------------------

def _gitignore_fix(project: ProjectFiles, wanted: set[str]) -> FileFix | None:
    if not {"SEC005", "SEC006"} & wanted:
        return None
    rules = sorted({"SEC005", "SEC006"} & wanted)
    if ".gitignore" not in project.paths:
        return FileFix(path=".gitignore", diff=unified_diff(".gitignore", None, GITIGNORE), new_file=True, rules=rules,
                       changes=["Python çıktılarını, sanal ortamı ve `.env` dosyalarını dışarıda bırakan .gitignore oluşturuldu"])
    original = _read(project, ".gitignore")
    if original is None:
        return None
    separator = "" if not original or original.endswith("\n") else "\n"
    fixed = original + separator + "\n# Gizli ayarlar (RepoMentor AI)\n.env\n.env.*\n!.env.example\n"
    return FileFix(path=".gitignore", diff=unified_diff(".gitignore", original, fixed), rules=rules,
                   changes=["`.env` dosyaları .gitignore'a eklendi (yalnızca `.env.example` depoya girer)"])


def _env_key(node: ast.AST) -> str | None:
    """`os.getenv("X")`, `os.environ.get("X")`, `os.environ["X"]` → "X"."""
    key = None
    if isinstance(node, ast.Call) and call_name(node.func) in ENV_READERS and node.args:
        key = node.args[0]
    elif isinstance(node, ast.Subscript) and call_name(node.value) in {"os.environ", "environ"}:
        key = node.slice
    is_name = isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value.isidentifier()
    return key.value if is_name else None


def environment_names(project: ProjectFiles) -> list[str]:
    """Variables the code reads and the keys (never the values) of committed .env files."""
    names = {key for _, tree in project.parsed_python(include_tests=False) for node in ast.walk(tree) if (key := _env_key(node))}
    for path in project.paths:
        if PurePosixPath(path).name in {".env", ".env.local", ".env.dev", ".env.prod"}:
            names.update(ENV_KEY.findall(project.text(path) or ""))
    return sorted(names)


def _env_example_fix(project: ProjectFiles, wanted: set[str]) -> FileFix | None:
    names = environment_names(project) if "DOC009" in wanted and ".env.example" not in project.paths else []
    if not names:
        return None
    content = "# Gerçek değerleri .env dosyasına yazın; bu şablon depoya girer, .env girmez.\n" + "".join(f"{n}=\n" for n in names)
    return FileFix(path=".env.example", diff=unified_diff(".env.example", None, content), new_file=True, rules=["DOC009"],
                   changes=[f"{len(names)} ortam değişkeni için boş şablon: " + ", ".join(f"`{n}`" for n in names[:8])
                            + (f" (+{len(names) - 8})" if len(names) > 8 else "")])


# --- Patch ----------------------------------------------------------------------------------------------------

def unified_diff(path: str, before: str | None, after: str) -> str:
    """`git apply` / `patch -p1` compatible diff; `before=None` creates the file."""
    lines = difflib.unified_diff(_lines(before or ""), _lines(after), "/dev/null" if before is None else f"a/{path}", f"b/{path}")
    out = []
    for line in lines:
        out.append(line if line.endswith(("\n", "\r")) else line + "\n\\ No newline at end of file\n")
    return "".join(out)


def _fixable_sources(project: ProjectFiles) -> list[str]:
    """Ruff only touches source files: test helpers imported for pytest look unused, `__init__` re-exports too."""
    return [p for p in project.source_python_files if p.endswith(".py") and PurePosixPath(p).name not in {"__init__.py", "conftest.py"}]


def _drivers(project: ProjectFiles) -> set[str]:
    """Database drivers imported anywhere: a query in `views.py` may use a connection made in `db.py`."""
    names = set().union(*(imported_modules(tree) for _, tree in project.parsed_python(include_tests=False)))
    return names & (QMARK_DRIVERS | FORMAT_DRIVERS)


def _context(project: ProjectFiles, issues: list[Issue], run_tools: bool, flows: list[TaintFlow]) -> _Context:
    modules = set(project.python_modules)
    injections = [f for f in flows if f.kind in {"sql", "command"} and f.file in modules]
    ruff = _ruff_fixable(project, _fixable_sources(project)) if run_tools else {}
    return _Context({issue.rule_id for issue in issues}, ruff, injections, _drivers(project) if injections else set())


def _candidates(project: ProjectFiles, context: _Context) -> list[str]:
    """Python files worth reading again; notebooks are never patched."""
    paths = set(project.python_modules) if {"SEC012", "QLT007"} & context.wanted else set(context.ruff)
    return sorted(paths | {flow.file for flow in context.flows})


def build_fixes(project: ProjectFiles, issues: list[Issue], run_tools: bool = True, flows: list[TaintFlow] | None = None) -> FixReport:
    context = _context(project, issues, run_tools, flows or [])
    files = [fix for path in _candidates(project, context) if (fix := _python_fix(project, path, context))]
    files += [fix for fix in (_gitignore_fix(project, context.wanted), _env_example_fix(project, context.wanted)) if fix]
    return FixReport(files=files)
