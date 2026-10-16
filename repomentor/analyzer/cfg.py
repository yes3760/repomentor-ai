"""Statement-level control-flow graphs, and two analyses on top of them.

* Unreachable code: statements no path from the function entry reaches
  (after `return`/`raise`/`break`/`continue`/`sys.exit()`, under `if False:`,
  after `while True:` without `break`). Only the first statement of each dead
  region is reported.
* Resource leaks: a file / connection opened outside `with` for which at
  least one path to the function exit (early returns and `except` paths
  included) neither closes it nor hands it over. Returning it, yielding it,
  storing it on an object or passing it to another call transfers ownership
  and is not reported; well-known readers such as `json.load(f)` only borrow.

Exceptions are modelled where the code names them: every statement inside a
`try` may jump to its handlers, and `finally` runs on every way out.
Project functions that just `return sqlite3.connect(...)` are recognised as
resource factories, so `conn = db()` is tracked like the call it wraps.
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from dataclasses import dataclass, field

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.rules import make_issue
from repomentor.analyzer.taint.sources import PROCESS_EXITS, call_name, ends_flow
from repomentor.models.analysis_result import FlowFinding
from repomentor.models.issue import Issue, Location

RESOURCES = {
    "open": "dosya", "io.open": "dosya", "codecs.open": "dosya", "gzip.open": "dosya", "bz2.open": "dosya",
    "sqlite3.connect": "SQLite bağlantısı", "psycopg2.connect": "veritabanı bağlantısı",
    "pymysql.connect": "veritabanı bağlantısı", "mysql.connector.connect": "veritabanı bağlantısı",
    "socket.socket": "soket", "socket.create_connection": "soket", "urllib.request.urlopen": "ağ bağlantısı",
    "urlopen": "ağ bağlantısı", "zipfile.ZipFile": "arşiv", "tarfile.open": "arşiv",
    "tempfile.TemporaryFile": "geçici dosya", "tempfile.NamedTemporaryFile": "geçici dosya",
}
# `with conn:` only wraps a transaction for these; the connection stays open.
NOT_CLOSED_BY_WITH = {"sqlite3.connect", "psycopg2.connect"}
CLOSERS = {"close", "aclose", "__exit__"}
# Calls that use a file without taking responsibility for closing it.
BORROWERS = {
    "json.load", "json.dump", "pickle.load", "pickle.dump", "yaml.load", "yaml.safe_load", "yaml.dump", "yaml.safe_dump",
    "csv.reader", "csv.writer", "csv.DictReader", "csv.DictWriter", "tomllib.load", "toml.load", "print",
    "shutil.copyfileobj", "pd.read_csv", "pandas.read_csv", "len", "iter", "next", "list", "enumerate", "sorted",
}


@dataclass
class CFG:
    nodes: list[ast.AST | None] = field(default_factory=list)   # None for the entry and exit nodes
    succ: dict[int, set[int]] = field(default_factory=dict)
    raise_edges: set[tuple[int, int]] = field(default_factory=set)   # statement -> first statement of an except handler
    entry: int = -1
    exit: int = -1

    def add(self, node: ast.AST | None) -> int:
        self.nodes.append(node)
        self.succ[len(self.nodes) - 1] = set()
        return len(self.nodes) - 1

    def link(self, sources: set[int], target: int) -> None:
        for source in sources:
            self.succ[source].add(target)

    def reachable(self, starts: set[int], blocked: set[int] | frozenset = frozenset()) -> set[int]:
        """Nodes reachable from `starts`; blocked nodes are reached but not passed through."""
        seen, queue = set(starts), deque(s for s in starts if s not in blocked)
        while queue:
            for nxt in self.succ[queue.popleft()] - seen:
                seen.add(nxt)
                if nxt not in blocked:
                    queue.append(nxt)
        return seen

    def predecessors(self) -> dict[int, set[int]]:
        preds: dict[int, set[int]] = defaultdict(set)
        for source, targets in self.succ.items():
            for target in targets:
                preds[target].add(source)
        return preds


def _constant_test(test: ast.expr) -> bool | None:
    return bool(test.value) if isinstance(test, ast.Constant) else None


class _Builder:
    def __init__(self) -> None:
        self.cfg = CFG()
        self.loops: list[tuple[int, set[int]]] = []    # (continue target, break sources)
        self.created: list[int] = []
        self.finally_exits: list[set[int]] = []         # nodes leaving the function through a pending `finally`

    def build(self, body: list[ast.stmt]) -> CFG:
        self.cfg.entry = self.cfg.add(None)
        self.cfg.exit = self.cfg.add(None)
        self.cfg.link(self.block(body, {self.cfg.entry}), self.cfg.exit)
        return self.cfg

    def block(self, statements: list[ast.stmt], preds: set[int]) -> set[int]:
        for statement in statements:
            preds = self.statement(statement, preds)
        return preds

    def node(self, statement: ast.AST, preds: set[int]) -> int:
        index = self.cfg.add(statement)
        self.created.append(index)
        self.cfg.link(preds, index)
        return index

    def leave(self, sources: set[int]) -> None:
        """Leave the function, through the innermost pending `finally` when there is one."""
        if self.finally_exits:
            self.finally_exits[-1].update(sources)
        else:
            self.cfg.link(sources, self.cfg.exit)

    def statement(self, statement: ast.stmt, preds: set[int]) -> set[int]:
        handler = getattr(self, f"_{type(statement).__name__}", None)
        if handler is not None:
            return handler(statement, preds)
        index = self.node(statement, preds)
        if ends_flow(statement):
            self.leave({index})
            return set()
        return {index}

    def _Break(self, statement: ast.Break, preds: set[int]) -> set[int]:
        index = self.node(statement, preds)
        if self.loops:
            self.loops[-1][1].add(index)
        return set()

    def _Continue(self, statement: ast.Continue, preds: set[int]) -> set[int]:
        index = self.node(statement, preds)
        if self.loops:
            self.cfg.link({index}, self.loops[-1][0])
        return set()

    def _If(self, statement: ast.If, preds: set[int]) -> set[int]:
        header = self.node(statement, preds)
        constant = _constant_test(statement.test)
        body = self.block(statement.body, set() if constant is False else {header})
        orelse_preds = set() if constant is True else {header}
        return body | (self.block(statement.orelse, orelse_preds) if statement.orelse else orelse_preds)

    def _loop(self, statement: ast.For | ast.AsyncFor | ast.While, preds: set[int]) -> set[int]:
        header = self.node(statement, preds)
        constant = _constant_test(statement.test) if isinstance(statement, ast.While) else None
        breaks: set[int] = set()
        self.loops.append((header, breaks))
        self.cfg.link(self.block(statement.body, set() if constant is False else {header}), header)
        self.loops.pop()
        normal_end = set() if constant is True else {header}
        return (self.block(statement.orelse, normal_end) if statement.orelse else normal_end) | breaks

    _For = _AsyncFor = _While = _loop

    def _With(self, statement: ast.With | ast.AsyncWith, preds: set[int]) -> set[int]:
        header = self.node(statement, preds)
        ends = self.block(statement.body, {header})
        # the context manager may swallow what ended the block (`contextlib.suppress`, `pytest.raises`)
        return ends or {header}

    _AsyncWith = _With

    def _handler(self, handler: ast.ExceptHandler, may_raise: set[int]) -> set[int]:
        first = len(self.cfg.nodes)
        ends = self.block(handler.body, may_raise)
        self.cfg.raise_edges.update((source, first) for source in may_raise)
        return ends

    def _Try(self, statement: ast.Try, preds: set[int]) -> set[int]:
        header = self.node(statement, preds)
        start = len(self.created)
        if statement.finalbody:
            self.finally_exits.append(set())
        body_end = self.block(statement.body, {header})
        may_raise = set(self.created[start:])   # the statements that run inside `try` (the header itself does nothing)
        handlers = set().union(*(self._handler(h, may_raise) for h in statement.handlers))
        normal = self.block(statement.orelse, body_end) if statement.orelse else body_end
        if not statement.finalbody:
            return normal | handlers
        leaving = self.finally_exits.pop()
        # `finally` runs on every way out: normally, after a handler, on `return` and on an uncaught exception.
        ends = self.block(statement.finalbody, normal | handlers | {header, *self.created[start:]})
        if leaving:
            self.leave(ends)
        return ends

    _TryStar = _Try

    def _Match(self, statement: ast.Match, preds: set[int]) -> set[int]:
        header = self.node(statement, preds)
        ends = set().union(*(self.block(case.body, {header}) for case in statement.cases))
        irrefutable = any(isinstance(c.pattern, ast.MatchAs) and c.pattern.pattern is None and c.guard is None for c in statement.cases)
        return ends if irrefutable else ends | {header}


def build_cfg(body: list[ast.stmt]) -> CFG:
    return _Builder().build(body)


# --- Unreachable code ---------------------------------------------------------------------------------------

def _placeholder(statement: ast.AST) -> bool:
    """`pass`, `...` and the bare `yield` that turns a function into a generator are dead on purpose."""
    return isinstance(statement, ast.Pass) or (
        isinstance(statement, ast.Expr) and isinstance(statement.value, (ast.Constant, ast.Yield)))


def unreachable_statements(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    """The first statement of every dead region.

    A dead statement starts a region when nothing earlier in the code leads to it; loop back edges
    come from later statements, so a dead loop still counts as one region.
    """
    cfg = build_cfg(func.body)
    alive = cfg.reachable({cfg.entry})
    preds = cfg.predecessors()
    starts = [cfg.nodes[i] for i in range(len(cfg.nodes))
              if cfg.nodes[i] is not None and i not in alive and all(p > i for p in preds[i])]
    return [s for s in starts if not _placeholder(s)]


# --- Resource leaks --------------------------------------------------------------------------------------------

def _opened_resource(statement: ast.AST | None, factories: dict[str, str]) -> tuple[str, str] | None:
    """(variable, opening call) for `name = open(...)`; factory calls resolve to the call they wrap."""
    if not isinstance(statement, ast.Assign) or len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
        return None
    call = statement.value
    if not isinstance(call, ast.Call) or any(k.arg == "fileno" for k in call.keywords):   # wraps a caller's descriptor
        return None
    name = call_name(call.func)
    opener = name if name in RESOURCES else factories.get(name)
    return (statement.targets[0].id, opener) if opener else None


def _header_parts(statement: ast.AST) -> list[ast.AST]:
    """The part of a statement that runs at its own CFG node (not its nested block)."""
    if isinstance(statement, (ast.If, ast.While)):
        return [statement.test]
    if isinstance(statement, (ast.For, ast.AsyncFor)):
        return [statement.iter]
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return [item.context_expr for item in statement.items]
    if isinstance(statement, ast.Match):
        return [statement.subject]
    if isinstance(statement, (ast.Try, ast.TryStar)):
        return []
    return [statement]


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _escapes(expr: ast.expr, name: str) -> bool:
    """The resource itself is part of the value (`f`, `(f, path)`), not merely used (`f.read()`)."""
    receivers = {id(n.value) for n in ast.walk(expr) if isinstance(n, ast.Attribute)}
    return any(_is_name(n, name) and id(n) not in receivers for n in ast.walk(expr))


def _hands_over(node: ast.AST, name: str) -> bool:
    """Ownership moves elsewhere: returned, yielded, stored on an object, or passed to a call that keeps it."""
    if isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom)) and node.value is not None:
        return _escapes(node.value, name)
    if isinstance(node, ast.Assign) and _is_name(node.value, name):
        return any(isinstance(t, (ast.Attribute, ast.Subscript)) for t in node.targets)
    if isinstance(node, ast.Call) and call_name(node.func) not in BORROWERS:
        return any(_is_name(a, name) for a in [*node.args, *(k.value for k in node.keywords)])
    return False


class _Ownership:
    """Which statements end the responsibility for one opened resource."""

    def __init__(self, name: str, opener: str):
        self.name = name
        self.with_closes = opener not in NOT_CLOSED_BY_WITH

    def releases(self, statement: ast.AST | None) -> bool:
        if statement is None:
            return False
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call) \
                and call_name(statement.value.func) in PROCESS_EXITS:
            return True        # the operating system reclaims everything
        if isinstance(statement, ast.If) and self._cleanup(statement):
            return True
        return any(self._part_releases(statement, part) for part in _header_parts(statement))

    def _cleanup(self, statement: ast.If) -> bool:
        """`if f is not None: f.close()` / `if opened: f.close()`: a close that falls through is trusted,
        because its condition mirrors the one under which the resource was opened."""
        body = [s for s in ast.walk(ast.Module(statement.body, [])) if isinstance(s, ast.stmt)]
        falls_through = not any(ends_flow(s) or isinstance(s, (ast.Break, ast.Continue)) for s in body)
        return falls_through and any(self.releases(s) for s in body)

    def _part_releases(self, statement: ast.AST, part: ast.AST) -> bool:
        if self.with_closes and isinstance(statement, (ast.With, ast.AsyncWith)) and _is_name(part, self.name):
            return True
        return any((isinstance(n, ast.Attribute) and n.attr in CLOSERS and _is_name(n.value, self.name))
                   or _hands_over(n, self.name) for n in ast.walk(part))


def leaked_resources(func: ast.FunctionDef | ast.AsyncFunctionDef, factories: dict[str, str] | None = None) -> list[tuple[ast.stmt, str, str]]:
    """(opening statement, variable, opening call) for resources some path never releases."""
    cfg = build_cfg(func.body)
    leaks = []
    for index in sorted(cfg.reachable({cfg.entry})):
        opened = _opened_resource(cfg.nodes[index], factories or {})
        if opened is None:
            continue
        ownership = _Ownership(*opened)
        release = {i for i, s in enumerate(cfg.nodes) if i != index and ownership.releases(s)}
        # if the opening call itself raises, nothing was opened: skip its own edges into `except`
        starts = {n for n in cfg.succ[index] if (index, n) not in cfg.raise_edges}
        if cfg.exit in cfg.reachable(starts, release) - release:
            leaks.append((cfg.nodes[index], *opened))
    return leaks


def _functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _factory_opener(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    returned = (n.value for n in ast.walk(func) if isinstance(n, ast.Return) and isinstance(n.value, ast.Call))
    return next((name for value in returned if (name := call_name(value.func)) in RESOURCES), None)


def resource_factories(trees: list[tuple[str, ast.Module]]) -> dict[str, str]:
    """Module-level functions that only hand out a resource: `def db(): return sqlite3.connect(DB)`.
    Decorated ones (`@contextmanager`) manage the resource themselves."""
    factories: dict[str, str] = {}
    for _, tree in trees:
        for func in tree.body:
            if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)) and not func.decorator_list \
                    and (opener := _factory_opener(func)):
                factories[func.name] = opener
    return factories


def _detail(finding: FlowFinding) -> str:
    return f"{finding.file}:{finding.line} `{finding.function}()` içinde {finding.detail}"


def flow_issues(findings: list[FlowFinding]) -> list[Issue]:
    groups: dict[str, list[FlowFinding]] = defaultdict(list)
    for finding in findings:
        groups[finding.rule].append(finding)
    issues = []
    for rule, group in groups.items():
        detail = "; ".join(_detail(f) for f in group[:3]) + (f" (+{len(group) - 3})" if len(group) > 3 else "")
        issues.append(make_issue(rule, [Location(f.file, f.line) for f in group][:15], {"count": len(group), "detail": detail},
                                 source="ast", count=len(group)))
    return issues


def analyze_flow(project: ProjectFiles) -> tuple[list[FlowFinding], list[Issue]]:
    trees = project.parsed_python(include_tests=False)
    factories = resource_factories(trees)
    findings: list[FlowFinding] = []
    for path, tree in trees:
        for func in _functions(tree):
            findings += [FlowFinding("QLT014", path, s.lineno, func.name, f"`{ast.unparse(s).splitlines()[0][:60]}`")
                         for s in unreachable_statements(func)]
            findings += [FlowFinding("QLT015", path, s.lineno, func.name, f"`{name}` ({RESOURCES[opener]})")
                         for s, name, opener in leaked_resources(func, factories)]
    return findings, flow_issues(findings)
