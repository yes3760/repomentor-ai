"""Our own AST metrics: cognitive complexity, structural clones and type-hint coverage.

Cognitive complexity follows the SonarSource definition (G. Ann Campbell, 2017)
mapped to Python syntax. Unlike cyclomatic complexity it measures how hard
code is to *read*: every nesting level makes the next branch more expensive,
while `elif`/`else` and a run of the same boolean operator count once.
"""

from __future__ import annotations

import ast
import copy
import hashlib
from collections import defaultdict

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.models.analysis_result import CloneGroup

COGNITIVE_LIMIT = 15        # SonarSource's default threshold
COGNITIVE_VERY_HIGH = 30
MIN_CLONE_STATEMENTS = 5
MIN_CLONE_LINES = 8


# --- Cognitive complexity -------------------------------------------------------------------------

class _Cognitive:
    def __init__(self, name: str, lines: list[str]):
        self.name, self.lines, self.score = name, lines, 0

    def body(self, nodes: list[ast.AST], nesting: int) -> None:
        for node in nodes:
            self.visit(node, nesting)

    def visit(self, node: ast.AST, nesting: int) -> None:
        handler = getattr(self, f"_{type(node).__name__}", None)
        if handler is not None:
            handler(node, nesting)
        else:
            for child in ast.iter_child_nodes(node):
                self.visit(child, nesting)

    def _is_elif(self, node: ast.If) -> bool:
        line = self.lines[node.lineno - 1] if 0 < node.lineno <= len(self.lines) else ""
        return line.lstrip().startswith("elif")

    def _If(self, node: ast.If, nesting: int, is_elif: bool = False) -> None:
        self.score += 1 if is_elif else 1 + nesting      # `elif` is a hybrid increment: no nesting penalty
        self.visit(node.test, nesting)
        self.body(node.body, nesting + 1)
        if not node.orelse:
            return
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If) and self._is_elif(node.orelse[0]):
            self._If(node.orelse[0], nesting, is_elif=True)
        else:
            self.score += 1                               # `else`
            self.body(node.orelse, nesting + 1)

    def _loop(self, node: ast.For | ast.While, nesting: int) -> None:
        self.score += 1 + nesting
        self.visit(node.iter if isinstance(node, (ast.For, ast.AsyncFor)) else node.test, nesting)
        self.body(node.body, nesting + 1)
        if node.orelse:
            self.score += 1
            self.body(node.orelse, nesting + 1)

    _For = _AsyncFor = _While = _loop

    def _IfExp(self, node: ast.IfExp, nesting: int) -> None:
        self.score += 1 + nesting
        for part in (node.test, node.body, node.orelse):
            self.visit(part, nesting + 1)

    def _Try(self, node: ast.Try, nesting: int) -> None:
        self.body(node.body, nesting)
        for handler in node.handlers:
            self.score += 1 + nesting
            self.body(handler.body, nesting + 1)
        self.body(node.orelse, nesting)
        self.body(node.finalbody, nesting)

    _TryStar = _Try

    def _Match(self, node: ast.Match, nesting: int) -> None:
        self.score += 1 + nesting
        self.visit(node.subject, nesting)
        for case in node.cases:
            self.body(case.body, nesting + 1)

    def _BoolOp(self, node: ast.BoolOp, nesting: int, parent: type | None = None) -> None:
        if type(node.op) is not parent:                   # a run of the same operator counts once
            self.score += 1
        for value in node.values:
            if isinstance(value, ast.BoolOp):
                self._BoolOp(value, nesting, type(node.op))
            else:
                self.visit(value, nesting)

    def _FunctionDef(self, node: ast.FunctionDef, nesting: int) -> None:
        self.body(node.body, nesting + 1)                 # nested function: more nesting, no increment

    _AsyncFunctionDef = _FunctionDef

    def _Lambda(self, node: ast.Lambda, nesting: int) -> None:
        self.visit(node.body, nesting + 1)

    def _ClassDef(self, node: ast.ClassDef, nesting: int) -> None:
        return                                            # its methods are measured on their own

    def _Call(self, node: ast.Call, nesting: int) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == self.name:
            self.score += 1                               # recursion
        for child in ast.iter_child_nodes(node):
            self.visit(child, nesting)


def cognitive_complexity(func: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str]) -> int:
    calculator = _Cognitive(func.name, lines)
    calculator.body(func.body, 0)
    return calculator.score


# --- Type hints -------------------------------------------------------------------------------------

def annotation_counts(project: ProjectFiles) -> tuple[int, int]:
    """(annotated, annotatable) parameters and return values of public source functions."""
    annotated = total = 0
    for _, tree in project.parsed_python(include_tests=False):
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name.startswith("_"):
                continue
            params = [a for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs if a.arg not in {"self", "cls"}]
            total += len(params) + 1
            annotated += sum(a.annotation is not None for a in params) + (node.returns is not None)
    return annotated, total


# --- Structural (Type-2) clones -------------------------------------------------------------------------

def _local_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names = {a.arg for a in ast.walk(func.args) if isinstance(a, ast.arg)}
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
    return names


class _Normaliser(ast.NodeTransformer):
    """Rename local variables to v0, v1… by first use and replace literals with their type."""

    def __init__(self, local: set[str]):
        self.local, self.mapping = local, {}

    def _rename(self, name: str) -> str:
        return self.mapping.setdefault(name, f"v{len(self.mapping)}") if name in self.local else name

    def visit_Name(self, node: ast.Name) -> ast.Name:
        return ast.copy_location(ast.Name(id=self._rename(node.id), ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.arg:
        return ast.copy_location(ast.arg(arg=self._rename(node.arg)), node)

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        return ast.copy_location(ast.Constant(value=type(node.value).__name__), node)


def structural_fingerprint(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Hash of the function shape, or None when it is too small to be an interesting clone."""
    body = list(func.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]  # docstring
    length = (func.end_lineno or func.lineno) - func.lineno + 1
    if len(body) < MIN_CLONE_STATEMENTS and length < MIN_CLONE_LINES:
        return None
    shape = ast.Module(body=[copy.deepcopy(s) for s in body], type_ignores=[])
    args = copy.deepcopy(func.args)
    normaliser = _Normaliser(_local_names(func))
    dumped = ast.dump(normaliser.visit(args), annotate_fields=False) + ast.dump(normaliser.visit(shape), annotate_fields=False)
    return hashlib.sha1(dumped.encode(), usedforsecurity=False).hexdigest()


def _overlaps(member: tuple[str, int, int], covered: dict[str, list[tuple[int, int]]]) -> bool:
    path, start, end = member
    return any(start <= c_end and c_start <= end for c_start, c_end in covered.get(path, []))


def _fingerprints(project: ProjectFiles) -> dict[str, list[tuple[str, ast.FunctionDef]]]:
    groups: dict[str, list[tuple[str, ast.FunctionDef]]] = defaultdict(list)
    for path, tree in project.parsed_python(include_tests=False):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (key := structural_fingerprint(node)):
                groups[key].append((path, node))
    return groups


def find_clones(project: ProjectFiles, covered: dict[str, list[tuple[int, int]]] | None = None) -> list[CloneGroup]:
    """Functions with the same structure but different names/literals.

    Groups whose every member is already inside a line-based duplicate block are
    skipped so the same copy is not reported twice.
    """
    covered = covered or {}
    clones = []
    for members in _fingerprints(project).values():
        spans = [(path, node.lineno, node.end_lineno or node.lineno) for path, node in members]
        if len(members) < 2 or all(_overlaps(span, covered) for span in spans):
            continue
        clones.append(CloneGroup(
            members=[f"{path}:{node.lineno} {node.name}()" for path, node in members],
            lines=max(end - start + 1 for _, start, end in spans),
        ))
    return sorted(clones, key=lambda c: (-len(c.members) * c.lines, c.members[0]))
