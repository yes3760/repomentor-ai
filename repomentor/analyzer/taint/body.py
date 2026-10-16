"""Walk one function (or module) body, tracking which names hold user input."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import TYPE_CHECKING

from repomentor.analyzer.taint.model import Summary, Taint, _Function
from repomentor.analyzer.taint.sinks import FIXED_HOST, SINK_RULES, _constant_prefix
from repomentor.analyzer.taint.sources import SANITIZERS, _short, _snippet, call_name, ends_flow, source_of
from repomentor.models.analysis_result import TaintFlow

if TYPE_CHECKING:
    from repomentor.analyzer.taint.engine import TaintEngine

# Checks that, when they pass, leave no room for injection characters. `startswith` is deliberately
# missing: a prefix check does not stop `/base/../etc` or `//evil.com`.
VALIDATORS = {"isdigit", "isdecimal", "isnumeric", "isalnum", "isalpha", "isidentifier", "is_relative_to", "fullmatch"}


class _BodyAnalysis:
    """Walk one function (or module) body, tracking which names hold user input."""

    def __init__(self, engine: TaintEngine, func: _Function, env: dict[str, Taint]):
        self.engine, self.func, self.env = engine, func, env
        self.flows: list[TaintFlow] = []
        self.summary = Summary()

    # expressions
    def taint(self, node: ast.AST | None) -> Taint | None:
        if node is None:
            return None
        if (source := source_of(node)) is not None:
            return source
        handler = getattr(self, f"_t_{type(node).__name__}", None)
        return handler(node) if handler else None

    def _any(self, nodes) -> Taint | None:
        return next((t for n in nodes if (t := self.taint(n)) is not None), None)

    def _t_Name(self, node: ast.Name) -> Taint | None:
        return self.env.get(node.id)

    def _t_JoinedStr(self, node: ast.JoinedStr) -> Taint | None:
        return self._any(node.values)

    def _t_FormattedValue(self, node: ast.FormattedValue) -> Taint | None:
        return self.taint(node.value)

    def _t_BinOp(self, node: ast.BinOp) -> Taint | None:
        return self.taint(node.left) or self.taint(node.right)

    def _t_BoolOp(self, node: ast.BoolOp) -> Taint | None:
        return self._any(node.values)

    def _t_IfExp(self, node: ast.IfExp) -> Taint | None:
        return self.taint(node.body) or self.taint(node.orelse)

    def _t_UnaryOp(self, node: ast.UnaryOp) -> Taint | None:
        return None if isinstance(node.op, ast.Not) else self.taint(node.operand)

    def _t_Attribute(self, node: ast.Attribute) -> Taint | None:
        return self.taint(node.value)

    def _t_Subscript(self, node: ast.Subscript) -> Taint | None:
        if (source := source_of(node.value)) is not None:   # request.args["q"]: name the exact read
            return replace(source, origin=_snippet(node, 50))
        return self.taint(node.value)

    def _t_Starred(self, node: ast.Starred) -> Taint | None:
        return self.taint(node.value)

    def _t_Await(self, node: ast.Await) -> Taint | None:
        return self.taint(node.value)

    def _t_NamedExpr(self, node: ast.NamedExpr) -> Taint | None:
        taint = self.taint(node.value)
        self.assign(node.target, taint, strong=False)
        return taint

    def _t_List(self, node: ast.List) -> Taint | None:
        return self._any(node.elts)

    _t_Tuple = _t_Set = _t_List

    def _t_Dict(self, node: ast.Dict) -> Taint | None:
        return self._any([k for k in node.keys if k is not None] + node.values)

    def _t_ListComp(self, node: ast.ListComp) -> Taint | None:
        return self._any([g.iter for g in node.generators])

    _t_SetComp = _t_GeneratorExp = _t_DictComp = _t_ListComp

    def _clears_taint(self, node: ast.Call, name: str, short: str) -> bool:
        """Sanitisers, `is…()` predicates and the project's own constructors return untracked values."""
        if name in SANITIZERS or short in SANITIZERS or short in self.engine.classes:
            return True  # project objects are not tracked field by field (precision over recall)
        return isinstance(node.func, ast.Attribute) and short.startswith("is")

    def _t_Call(self, node: ast.Call) -> Taint | None:
        name = call_name(node.func)
        short = _short(name)
        if self._clears_taint(node, name, short):
            return None
        if isinstance(node.func, ast.Attribute) and (source := source_of(node.func) or source_of(node.func.value)) is not None:
            return replace(source, origin=_snippet(node, 50))   # request.args.get("q") / request.get_json()
        args = [self.taint(a) for a in node.args]
        kwargs = [self.taint(kw.value) for kw in node.keywords]
        summary = self.engine.summary_for(node.func)
        if summary is not None:
            return self._through_summary(summary, args, short)
        receiver = self.taint(node.func.value) if isinstance(node.func, ast.Attribute) else None
        return receiver or next((a for a in args + kwargs if a is not None), None)

    @staticmethod
    def _through_summary(summary: Summary, args: list[Taint | None], short: str) -> Taint | None:
        """Result of calling a project function whose behaviour is summarised."""
        if summary.returns_source is not None:
            return summary.returns_source
        return next((arg.via(f"{short}()") for i, arg in enumerate(args) if arg is not None and i in summary.param_returns), None)

    # sinks
    def _controls_host(self, node: ast.expr) -> Taint | None:
        prefix = _constant_prefix(node)
        if prefix is not None and FIXED_HOST.match(prefix):
            return None  # the host is fixed by the code; only the path varies
        return self.taint(node)

    def check_sinks(self, root: ast.AST) -> None:
        for node in _calls_in(root):
            name = call_name(node.func)
            short = _short(name)
            self._check_call_sink(node, name, short)
            self._check_summary_sinks(node, short)

    def _check_call_sink(self, node: ast.Call, name: str, short: str) -> None:
        for kind, matches, argument, host in SINK_RULES:
            if not matches(node, name, short):
                continue
            arg = argument(node)
            taint = (self._controls_host(arg) if host else self.taint(arg)) if arg is not None else None
            if taint is not None:
                self.record(kind, taint, node, _snippet(node))
            return

    def _check_summary_sinks(self, node: ast.Call, short: str) -> None:
        summary = self.engine.summary_for(node.func)
        if summary is None or not summary.param_sinks:
            return
        for index, arg in enumerate(node.args):
            if index in summary.param_sinks and (taint := self.taint(arg)) is not None:
                kind, sink, file, line = summary.param_sinks[index]
                self.record(kind, taint.via(f"{short}()"), node, f"{_snippet(node, 40)} → {sink} ({file}:{line})", via=short)

    def record(self, kind: str, taint: Taint, node: ast.Call, sink: str, via: str | None = None) -> None:
        if taint.param is not None:
            self.summary.param_sinks.setdefault(taint.param, (kind, sink, self.func.file, node.lineno))
            return
        self.flows.append(TaintFlow(
            kind=kind, file=self.func.file, line=node.lineno, sink=sink, source=taint.origin, source_line=taint.line,
            path=list(taint.hops), function=self.func.name, remote=taint.remote, via=via,
        ))

    # statements
    def assign(self, target: ast.AST, taint: Taint | None, strong: bool) -> None:
        if isinstance(target, ast.Name):
            self._assign_name(target.id, taint, strong)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self.assign(element, taint, strong)
        elif isinstance(target, ast.Starred):
            self.assign(target.value, taint, strong)
        elif isinstance(target, (ast.Attribute, ast.Subscript)) and taint is not None:
            self._taint_container(target, taint)

    def _assign_name(self, name: str, taint: Taint | None, strong: bool) -> None:
        if taint is not None:
            self.env[name] = taint.via(name)
        elif strong:
            self.env.pop(name, None)      # re-assigned with a clean value: the mark is gone

    def _taint_container(self, target: ast.Attribute | ast.Subscript, taint: Taint) -> None:
        """`data["x"] = user_input` taints `data`; `self.x = …` is not tracked (field-insensitive)."""
        base = target.value
        while isinstance(base, (ast.Attribute, ast.Subscript)):
            base = base.value
        if isinstance(base, ast.Name) and base.id not in {"self", "cls"}:
            self.env[base.id] = taint.via(base.id)

    def block(self, statements: list[ast.stmt], strong: bool) -> None:
        for statement in statements:
            self.statement(statement, strong)

    def statement(self, node: ast.stmt, strong: bool) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return  # analysed on their own
        handler = getattr(self, f"_s_{type(node).__name__}", None)
        if handler is not None:
            handler(node, strong)
        else:
            self.check_sinks(node)

    def _s_Assign(self, node: ast.Assign, strong: bool) -> None:
        self.check_sinks(node.value)
        taint = self.taint(node.value)
        for target in node.targets:
            self.assign(target, taint, strong)

    def _s_AnnAssign(self, node: ast.AnnAssign, strong: bool) -> None:
        if node.value is not None:
            self.check_sinks(node.value)
            self.assign(node.target, self.taint(node.value), strong)

    def _s_AugAssign(self, node: ast.AugAssign, strong: bool) -> None:
        self.check_sinks(node.value)
        self.assign(node.target, self.taint(node.value), strong=False)

    def _s_Return(self, node: ast.Return, strong: bool) -> None:
        self.check_sinks(node)
        taint = self.taint(node.value)
        if taint is None:
            return
        if taint.param is not None:
            self.summary.param_returns.add(taint.param)
        else:
            self.summary.returns_source = self.summary.returns_source or taint

    def _s_If(self, node: ast.If, strong: bool) -> None:
        self.check_sinks(node.test)
        with self._validated(self.proven(node.test, True)):
            self.block(node.body, False)
        with self._validated(self.proven(node.test, False)):
            self.block(node.orelse, False)
        if strong and node.body and ends_flow(node.body[-1]):
            # `if not code.isdigit(): abort(400)`: everything below runs only when the check passed
            for name in self.proven(node.test, False):
                self.env.pop(name, None)

    # guards
    def proven(self, test: ast.expr, outcome: bool) -> set[str]:
        """Tainted names that are validated whenever `test` evaluates to `outcome`."""
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            return self.proven(test.operand, not outcome)
        if isinstance(test, ast.BoolOp):
            # `a and b` is true only if both hold; `a or b` is false only if neither holds
            parts = [self.proven(v, outcome) for v in test.values] if isinstance(test.op, ast.And) == outcome else []
            return set().union(*parts)
        if isinstance(test, ast.Compare):
            return self._allow_listed(test, outcome)
        return self._checked_by_call(test) if outcome else set()

    def _allow_listed(self, test: ast.Compare, outcome: bool) -> set[str]:
        """`x in ALLOWED` is true / `x not in ALLOWED` is false — but not `x in request.args`."""
        if len(test.ops) != 1 or not isinstance(test.left, ast.Name) or test.left.id not in self.env:
            return set()
        member = isinstance(test.ops[0], ast.In if outcome else ast.NotIn)
        return {test.left.id} if member and self.taint(test.comparators[0]) is None else set()

    def _checked_by_call(self, test: ast.expr) -> set[str]:
        """`x.isdigit()`, `re.fullmatch(P, x)`, `PATTERN.fullmatch(x)`, `Path(x).resolve().is_relative_to(BASE)`."""
        if not isinstance(test, ast.Call) or call_name(test.func).rsplit(".", 1)[-1] not in VALIDATORS:
            return set()
        subject = test.args if call_name(test.func).endswith("fullmatch") else [getattr(test.func, "value", test.func)]
        return {n.id for part in subject for n in ast.walk(part) if isinstance(n, ast.Name) and n.id in self.env}

    @contextmanager
    def _validated(self, names: set[str]) -> Iterator[None]:
        """Inside a branch that only runs when `names` passed a check, they carry no mark."""
        saved = {name: self.env.pop(name) for name in names if name in self.env}
        yield
        for name, taint in saved.items():
            self.env.setdefault(name, taint)

    def _s_While(self, node: ast.While, strong: bool) -> None:
        self.check_sinks(node.test)
        self.block(node.body, False)
        self.block(node.orelse, False)

    def _s_For(self, node: ast.For, strong: bool) -> None:
        self.check_sinks(node.iter)
        self.assign(node.target, self.taint(node.iter), strong=False)
        self.block(node.body, False)
        self.block(node.orelse, False)

    _s_AsyncFor = _s_For

    def _s_With(self, node: ast.With, strong: bool) -> None:
        for item in node.items:
            self.check_sinks(item.context_expr)
            if item.optional_vars is not None:
                self.assign(item.optional_vars, self.taint(item.context_expr), strong)
        self.block(node.body, strong)

    _s_AsyncWith = _s_With

    def _s_Try(self, node: ast.Try, strong: bool) -> None:
        self.block(node.body, strong)
        for handler in node.handlers:
            self.block(handler.body, False)
        self.block(node.orelse, False)
        self.block(node.finalbody, False)

    _s_TryStar = _s_Try

    def _s_Match(self, node: ast.Match, strong: bool) -> None:
        self.check_sinks(node.subject)
        for case in node.cases:
            self.block(case.body, False)


def _calls_in(root: ast.AST):
    """Calls inside `root`, not descending into nested functions, classes or lambdas."""
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Call):
            yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                stack.append(child)
