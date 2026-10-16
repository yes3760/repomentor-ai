"""Module dependency graph: who imports whom, circular imports and coupling.

* Edges come from `import` / `from … import` statements resolved against the
  project's own modules (relative imports and `src/` layouts included).
* Imports inside functions are *lazy*: they run after every module has loaded,
  so they cannot cause an import-time cycle and are kept out of cycle
  detection. `if TYPE_CHECKING:` imports never run and are ignored.
* Cycles are the strongly connected components of the eager graph (Tarjan,
  iterative). For each component one concrete loop is reported, because
  "a → b → c → a" is actionable and "{a, b, c}" is not.
* Coupling follows Robert C. Martin: Ca (afferent, fan-in), Ce (efferent,
  fan-out) and instability I = Ce / (Ca + Ce).
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from pathlib import PurePosixPath

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.rules import make_issue
from repomentor.models.analysis_result import ImportEdge, ImportGraphReport, ModuleCoupling
from repomentor.models.issue import Issue, Location

MAX_GRAPH_NODES = 40


def module_name(path: str, strip_src: bool = True) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if strip_src and parts and parts[0] == "src" and len(parts) > 1:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _imports(tree: ast.Module) -> list[tuple[ast.Import | ast.ImportFrom, bool]]:
    """(import node, lazy) pairs, skipping `if TYPE_CHECKING:` blocks."""
    found: list[tuple[ast.Import | ast.ImportFrom, bool]] = []

    def walk(nodes: list[ast.AST], lazy: bool) -> None:
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                found.append((node, lazy))
            elif isinstance(node, ast.If) and _is_type_checking(node.test):
                walk(node.orelse, lazy)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                walk(list(ast.iter_child_nodes(node)), True)
            else:
                walk(list(ast.iter_child_nodes(node)), lazy)

    walk(tree.body, False)
    return found


def _resolve(candidates: list[str], known: dict[str, str]) -> str | None:
    """Canonical name of the longest known module among the candidates' dotted prefixes."""
    for candidate in candidates:
        parts = candidate.split(".")
        for size in range(len(parts), 0, -1):
            prefix = ".".join(parts[:size])
            if prefix in known:
                return known[prefix]
    return None


def from_base(node: ast.ImportFrom, current: str, is_package: bool) -> str:
    """Absolute module a `from … import` refers to, resolving leading dots."""
    if not node.level:
        return node.module or ""
    package = current.split(".") if is_package else current.split(".")[:-1]
    if node.level > 1:
        package = package[: len(package) - (node.level - 1)]
    return ".".join(part for part in [*package, node.module or ""] if part)


def _targets(node: ast.Import | ast.ImportFrom, current: str, is_package: bool, known: dict[str, str]) -> set[str]:
    if isinstance(node, ast.Import):
        candidates = [alias.name for alias in node.names]
    else:
        # `from pkg import sub` depends on pkg.sub when it is a module, otherwise on pkg itself (longest known prefix).
        base = from_base(node, current, is_package)
        candidates = [f"{base}.{alias.name}" if base else alias.name for alias in node.names]
    return {target for target in (_resolve([c], known) for c in candidates) if target}


def _module_index(project: ProjectFiles) -> tuple[dict[str, str], dict[str, str]]:
    """(canonical name -> file, import name -> canonical name).

    `src/data.py` is known as both `data` (installed src layout) and `src.data`
    (beginner projects that run from the repository root and import `src.data`).
    """
    files: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for path in project.source_python_files:
        full = module_name(path, strip_src=False)
        canonical = module_name(path) or full
        if not canonical:
            continue
        files[canonical] = path
        for alias in {canonical, full} - {""}:
            aliases.setdefault(alias, canonical)
    return files, aliases


def build_edges(project: ProjectFiles) -> tuple[dict[str, str], list[ImportEdge]]:
    files, known = _module_index(project)
    edges: dict[tuple[str, str], bool] = {}
    for name, path in files.items():
        tree = project.tree(path)
        if tree is None:
            continue
        is_package = PurePosixPath(path).name == "__init__.py"
        for node, lazy in _imports(tree):
            for target in _targets(node, name, is_package, known) - {name}:
                edges[(name, target)] = edges.get((name, target), True) and lazy   # eager wins
    return files, [ImportEdge(source, target, lazy) for (source, target), lazy in sorted(edges.items())]


class _Tarjan:
    """Tarjan's strongly connected components, iterative so deep graphs cannot hit the recursion limit."""

    def __init__(self, adjacency: dict[str, list[str]]):
        self.adjacency = adjacency
        self.index: dict[str, int] = {}
        self.low: dict[str, int] = {}
        self.stack: list[str] = []
        self.on_stack: set[str] = set()
        self.components: list[list[str]] = []

    def _enter(self, node: str, work: list) -> None:
        self.index[node] = self.low[node] = len(self.index)
        self.stack.append(node)
        self.on_stack.add(node)
        work.append((node, iter(self.adjacency.get(node, []))))

    def _close(self, node: str) -> None:
        """`node` is finished; if it is a component root, pop the component."""
        if self.low[node] != self.index[node]:
            return
        component = []
        while (member := self.stack.pop()) != node:
            self.on_stack.discard(member)
            component.append(member)
        self.on_stack.discard(node)
        self.components.append([*component, node])

    def _step(self, work: list) -> None:
        node, children = work[-1]
        child = next(children, None)
        if child is None:
            work.pop()
            if work:
                parent = work[-1][0]
                self.low[parent] = min(self.low[parent], self.low[node])
            self._close(node)
        elif child not in self.index:
            self._enter(child, work)
        elif child in self.on_stack:
            self.low[node] = min(self.low[node], self.index[child])

    def run(self, nodes: list[str]) -> list[list[str]]:
        for root in nodes:
            if root not in self.index:
                work: list = []
                self._enter(root, work)
                while work:
                    self._step(work)
        return self.components


def strongly_connected(nodes: list[str], adjacency: dict[str, list[str]]) -> list[list[str]]:
    return _Tarjan(adjacency).run(nodes)


def shortest_cycle(component: list[str], adjacency: dict[str, list[str]]) -> list[str]:
    """A concrete loop through the component's first module (BFS, so the shortest one)."""
    members = set(component)
    start = min(component)
    previous: dict[str, str] = {}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for child in adjacency.get(node, []):
            if child == start:
                path = [node]                       # walk back: node → … → start
                while path[-1] != start:
                    path.append(previous[path[-1]])
                return [*reversed(path), start]
            if child in members and child not in previous and child != start:
                previous[child] = node
                queue.append(child)
    return [*sorted(component), component[0]]


def _coupling(files: dict[str, str], edges: list[ImportEdge]) -> list[ModuleCoupling]:
    fan_in: dict[str, set[str]] = defaultdict(set)
    fan_out: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        fan_out[edge.source].add(edge.target)
        fan_in[edge.target].add(edge.source)
    rows = []
    for name, path in files.items():
        ca, ce = len(fan_in[name]), len(fan_out[name])
        rows.append(ModuleCoupling(name, path, ca, ce, round(ce / (ca + ce), 2) if ca + ce else 0.0))
    return sorted(rows, key=lambda m: (-(m.fan_in + m.fan_out), m.name))


def analyze_imports(project: ProjectFiles) -> ImportGraphReport:
    files, edges = build_edges(project)
    eager: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if not edge.lazy:
            eager[edge.source].append(edge.target)
    components = [c for c in strongly_connected(sorted(files), eager) if len(c) > 1]
    cycles = sorted((shortest_cycle(c, eager) for c in components), key=lambda c: (len(c), c))
    return ImportGraphReport(modules=_coupling(files, edges), edges=edges, cycles=cycles)


def cycle_issues(report: ImportGraphReport) -> list[Issue]:
    files = {m.name: m.file for m in report.modules}
    return [
        make_issue("ORG008", [Location(files[name]) for name in cycle[:-1] if name in files], {"cycle": " → ".join(cycle)},
                   source="ast", effort_minutes=30 + 15 * (len(cycle) - 2))
        for cycle in report.cycles[:5]
    ]


DOT_HEADER = [
    "digraph imports {",
    '  graph [rankdir=LR, bgcolor="transparent", pad=0.2, nodesep=0.25, ranksep=0.6];',
    '  node [shape=box, style="rounded,filled", fillcolor="#f5f4ef", color="#c9c7bd", fontcolor="#1f1e1b", '
    'fontname="Helvetica", fontsize=10];',
    '  edge [color="#9a998f", arrowsize=0.6];',
]
CYCLE_NODE = ', fillcolor="#fde3e3", color="#d03b3b", penwidth=1.6'


def _edge_line(edge: ImportEdge, in_cycle: set[tuple[str, str]]) -> str:
    attrs = ['color="#d03b3b"', "penwidth=2"] if (edge.source, edge.target) in in_cycle else []
    attrs += ["style=dashed"] if edge.lazy else []
    return f'  "{edge.source}" -> "{edge.target}"' + (f" [{', '.join(attrs)}]" if attrs else "") + ";"


def to_dot(report: ImportGraphReport, max_nodes: int = MAX_GRAPH_NODES) -> str:
    """Graphviz source: cycle edges in red, lazy imports dashed, busiest modules only."""
    shown = {m.name for m in report.modules[:max_nodes]}
    in_cycle = {(a, b) for cycle in report.cycles for a, b in zip(cycle, cycle[1:], strict=False)}
    cycle_nodes = {name for cycle in report.cycles for name in cycle}
    nodes = [f'  "{name}" [label="{name}"{CYCLE_NODE if name in cycle_nodes else ""}];' for name in sorted(shown)]
    edges = [_edge_line(e, in_cycle) for e in report.edges if e.source in shown and e.target in shown]
    return "\n".join([*DOT_HEADER, *nodes, *edges, "}"])
