"""Project-wide analysis: index functions, summarise them to a fixed point, collect flows."""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import PurePosixPath

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.taint.body import _BodyAnalysis
from repomentor.analyzer.taint.model import Summary, Taint, _Function
from repomentor.analyzer.taint.sources import NON_INPUT_PARAMS, ROUTE_DECORATORS, VALIDATED_TYPES, call_name
from repomentor.models.analysis_result import TaintFlow


def _is_route(node: ast.AST) -> bool:
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr in ROUTE_DECORATORS and isinstance(decorator, ast.Call):
            return True
        if isinstance(target, ast.Name) and target.id == "api_view":
            return True
    return False


def _params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    return node.args.posonlyargs + node.args.args + node.args.kwonlyargs


def _validated(arg: ast.arg, default: ast.expr | None) -> bool:
    """FastAPI converts and validates typed parameters; `Depends(...)` values are not user input."""
    annotation = ast.unparse(arg.annotation) if arg.annotation is not None else ""
    if annotation.split("[")[0].split("|")[0].strip() in VALIDATED_TYPES:
        return True
    return isinstance(default, ast.Call) and call_name(default.func) in {"Depends", "Security", "fastapi.Depends"}


def _defaults(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, ast.expr | None]:
    positional = node.args.posonlyargs + node.args.args
    padded = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    values = dict(zip((a.arg for a in positional), padded, strict=True))
    values.update(zip((a.arg for a in node.args.kwonlyargs), node.args.kw_defaults, strict=True))
    return values


class TaintEngine:
    MAX_ROUNDS = 4

    def __init__(self, project: ProjectFiles):
        self.project = project
        self.functions: dict[str, list[_Function]] = defaultdict(list)
        self.classes: set[str] = set()
        self.local_modules = {PurePosixPath(p).stem for p in project.python_files} | {
            part for p in project.python_files for part in PurePosixPath(p).parts[:-1]
        }
        self.modules: list[_Function] = []
        self.summaries: dict[str, Summary] = {}
        self._index()

    def _index(self) -> None:
        for path, tree in self.project.parsed_python(include_tests=False):
            self.modules.append(_Function(tree, path, "<modül>", []))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.classes.add(node.name)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    params = [p for p in _params(node) if p.arg not in {"self", "cls"}]
                    self.functions[node.name].append(_Function(node, path, node.name, params, _is_route(node)))

    def summary_for(self, func: ast.expr) -> Summary | None:
        """Summary of a call target that is certainly one of the project's functions.

        Plain names, `self.`/`cls.` methods and `module.function` for the project's own
        modules qualify; `request.args.get` must not borrow the summary of a local `get`.
        """
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and (
            func.value.id in {"self", "cls"} or func.value.id in self.local_modules
        ):
            name = func.attr
        else:
            return None
        return self.summaries.get(name) if name in self.functions else None

    @property
    def function_count(self) -> int:
        return sum(len(defs) for defs in self.functions.values())

    def _body(self, func: _Function) -> list[ast.stmt]:
        return list(func.node.body)

    def summarise(self) -> None:
        """Iterate function summaries to a fixed point (bounded)."""
        for _ in range(self.MAX_ROUNDS):
            changed = False
            for name, defs in self.functions.items():
                merged = self.summaries.setdefault(name, Summary())
                for func in defs:
                    env = {p.arg: Taint(f"parametre `{p.arg}`", func.node.lineno, param=i) for i, p in enumerate(func.params)}
                    analysis = _BodyAnalysis(self, func, env)
                    analysis.block(self._body(func), True)
                    changed |= merged.merge(analysis.summary)
            if not changed:
                return

    def _route_env(self, func: _Function) -> dict[str, Taint]:
        if not func.route:
            return {}
        defaults = _defaults(func.node)
        return {
            p.arg: Taint(f"istek parametresi `{p.arg}`", func.node.lineno, hops=(p.arg,))
            for p in func.params
            if p.arg not in NON_INPUT_PARAMS and not _validated(p, defaults.get(p.arg))
        }

    def flows(self) -> list[TaintFlow]:
        self.summarise()
        found: dict[tuple[str, int, str], TaintFlow] = {}
        units = [f for defs in self.functions.values() for f in defs] + self.modules
        for func in units:
            analysis = _BodyAnalysis(self, func, self._route_env(func))
            analysis.block(self._body(func), True)
            for flow in analysis.flows:
                found.setdefault((flow.file, flow.line, flow.kind), flow)
        return sorted(found.values(), key=lambda f: (f.file, f.line))


KIND_LABELS = {
    "code": "Kod enjeksiyonu", "command": "Komut enjeksiyonu", "sql": "SQL enjeksiyonu", "path": "Dizin aşımı",
    "deserialize": "Güvensiz nesne yükleme", "template": "Şablon enjeksiyonu (SSTI)", "ssrf": "SSRF",
    "redirect": "Açık yönlendirme", "xss": "XSS",
}


def describe(flow: TaintFlow) -> str:
    """`request.args.get('q')` (app.py:12) → `q` → `eval(q)` (app.py:13)"""
    hops = [f"`{hop}`" for hop in flow.path]
    steps = [f"`{flow.source}` ({flow.file}:{flow.source_line})", *hops, f"`{flow.sink}` ({flow.file}:{flow.line})"]
    return " → ".join(steps)


def find_taint_flows(project: ProjectFiles) -> tuple[list[TaintFlow], int]:
    """(confirmed flows, number of functions analysed)."""
    engine = TaintEngine(project)
    return engine.flows(), engine.function_count
