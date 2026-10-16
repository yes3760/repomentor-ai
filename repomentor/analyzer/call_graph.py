"""Reference graph of the project's functions, classes and module-level tables.

One graph, two questions:
* Dead code – what can no entry point reach? Entry points are module-level
  code, framework-registered functions (decorators), protocol methods,
  subclasses of external classes, `__all__` and `[project.scripts]`.
* Static test reach – what can the tests reach? Starting from the test
  functions instead, the reachable source functions approximate coverage
  without running anything.

An edge is any *reference*, not only a call: callbacks (`on_click=f`),
functions stored in tables (`TABS = (("x", render_x),)`), `getattr(self,
f"_t_{…}")` dispatch, `super()` and the class hierarchy all count. When a
reference cannot be resolved precisely, every candidate with that name is
kept alive: telling someone to delete used code is worse than missing an
unused function.
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.import_graph import from_base, module_name
from repomentor.analyzer.taint.sources import call_name

# Decorators that do not register the function anywhere, so they do not make it an entry point.
PURE_DECORATORS = {
    "property", "staticmethod", "classmethod", "cached_property", "lru_cache", "cache", "wraps", "abstractmethod",
    "override", "setter", "getter", "deleter", "overload", "dataclass", "total_ordering", "contextmanager",
}
TEST_CLIENT = re.compile(r"\bTestClient\b|\.test_client\(|\bAsyncClient\(")
ROUTE_DECORATORS = {"route", "get", "post", "put", "patch", "delete", "api_route", "websocket"}


@dataclass
class Symbol:
    key: str                 # "module:Class.method", "module:func", "module:<module>", "module:TABLE"
    name: str
    kind: str                # function | method | class | variable | module
    file: str
    line: int
    owner: str | None = None # class key for methods
    root: str | None = None  # why this is an entry point for dead-code purposes
    test: bool = False
    route: bool = False
    pure_only: bool = False  # overload / abstract declarations: never reported


@dataclass
class _Module:
    name: str
    file: str
    scope: dict[str, str] = field(default_factory=dict)       # name -> symbol key
    modules: dict[str, str] = field(default_factory=dict)     # alias -> local module name
    imported: dict[str, tuple[str, str]] = field(default_factory=dict)  # alias -> (module, name)


def _decorator_names(node: ast.AST) -> list[str]:
    names = []
    for decorator in getattr(node, "decorator_list", []):
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        names.append(call_name(target))
    return names


def _registering(names: list[str]) -> list[str]:
    return [n for n in names if n.rsplit(".", 1)[-1] not in PURE_DECORATORS]


DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
NEUTRAL_BASES = {"object", "Generic", "Protocol", "ABC"}


class CallGraph:
    def __init__(self, project: ProjectFiles):
        self.project = project
        self.symbols: dict[str, Symbol] = {}
        self.edges: dict[str, set[str]] = defaultdict(set)
        self.modules: dict[str, _Module] = {}
        self.methods_by_name: dict[str, set[str]] = defaultdict(set)
        self.class_methods: dict[str, dict[str, str]] = defaultdict(dict)
        self.class_bases: dict[str, list[str]] = {}
        self.external_base: set[str] = set()
        self.parents: dict[str, set[str]] = defaultdict(set)
        self.children: dict[str, set[str]] = defaultdict(set)
        self._bodies: list[tuple[str, list[ast.AST], str, str | None]] = []   # (key, nodes, module, class key)
        self._aliases: list[tuple[str, str, str]] = []                           # (class key, alias, method name)
        self._index()
        self._link_classes()
        for key, nodes, module, owner in self._bodies:
            for node in nodes:
                self._refs(key, node, module, owner)

    # --- indexing: modules and imports -------------------------------------------------------------
    def _add(self, symbol: Symbol) -> None:
        self.symbols[symbol.key] = symbol

    @staticmethod
    def _name_of(path: str) -> str:
        return module_name(path) or module_name(path, strip_src=False) or PurePosixPath(path).stem

    def _index(self) -> None:
        trees = [(path, tree) for path in sorted(self.project.python_files) if (tree := self.project.tree(path)) is not None]
        for path, _ in trees:
            name = self._name_of(path)
            self.modules[name] = _Module(name, path)
            if (full := module_name(path, strip_src=False)) and full != name:
                self.modules.setdefault(full, self.modules[name])   # `src.data` and `data` are the same module
        for path, tree in trees:
            module = self.modules[self._name_of(path)]
            self._index_imports(module, tree)
            self._index_module(module, tree)

    def _local_module(self, dotted: str) -> str | None:
        parts = dotted.split(".")
        return next((".".join(parts[:n]) for n in range(len(parts), 0, -1) if ".".join(parts[:n]) in self.modules), None)

    def _bind_import(self, module: _Module, alias: ast.alias) -> None:
        # `import a.b.c` binds `a`; `import a.b.c as x` binds `x` to a.b.c itself.
        bound, dotted = (alias.asname, alias.name) if alias.asname else (alias.name.split(".")[0],) * 2
        if local := self._local_module(dotted):
            module.modules[bound] = local

    def _bind_from(self, module: _Module, base: str, alias: ast.alias) -> None:
        target = alias.asname or alias.name
        submodule = f"{base}.{alias.name}".lstrip(".")
        if submodule in self.modules:
            module.modules[target] = submodule
        elif base in self.modules:
            module.imported[target] = (base, alias.name)

    def _index_imports(self, module: _Module, tree: ast.Module) -> None:
        is_package = PurePosixPath(module.file).name == "__init__.py"
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._bind_import(module, alias)
            elif isinstance(node, ast.ImportFrom):
                base = from_base(node, module.name, is_package)
                for alias in node.names:
                    self._bind_from(module, base, alias)

    # --- indexing: definitions ------------------------------------------------------------------------
    def _index_module(self, module: _Module, tree: ast.Module) -> None:
        test = self.project.is_test(module.file)
        module_key = f"{module.name}:<module>"
        self._add(Symbol(module_key, "<module>", "module", module.file, 1, root="modül kodu", test=test))
        loose: list[ast.AST] = []
        for node in tree.body:
            if isinstance(node, DEF_NODES):
                self._index_def(node, module, None, module_key, test)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and self._simple_targets(node):
                self._index_variables(node, module, module_key, test)
            else:
                loose.append(node)
        self._bodies.append((module_key, loose, module.name, None))

    def _index_variables(self, node: ast.Assign | ast.AnnAssign, module: _Module, module_key: str, test: bool) -> None:
        """Module-level tables are nodes: `TABS = ((…, render_x),)` keeps render_x alive only if TABS is used."""
        for target in self._simple_targets(node):
            key = f"{module.name}:{target}"
            module.scope[target] = key
            self._add(Symbol(key, target, "variable", module.file, node.lineno, root="modül değişkeni", test=test))
            self._bodies.append((key, [node.value] if node.value is not None else [], module.name, None))
            if target == "__all__":
                self._bodies.append((module_key, self._all_names(node), module.name, None))

    @staticmethod
    def _simple_targets(node: ast.Assign | ast.AnnAssign) -> list[str]:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return [t.id for t in targets if isinstance(t, ast.Name)]

    @staticmethod
    def _all_names(node: ast.Assign | ast.AnnAssign) -> list[ast.AST]:
        values = getattr(node.value, "elts", [])
        return [ast.Name(id=v.value, ctx=ast.Load()) for v in values if isinstance(v, ast.Constant) and isinstance(v.value, str)]

    def _index_def(self, node: ast.AST, module: _Module, owner: str | None, parent: str, test: bool, prefix: str = "") -> None:
        qual = f"{prefix}{node.name}"
        key = f"{module.name}:{qual}"
        if owner is None and not prefix:
            module.scope[node.name] = key
        self._bodies.append((parent, list(getattr(node, "decorator_list", [])), module.name, owner))
        if isinstance(node, ast.ClassDef):
            self._index_class(node, module, key, qual, test)
        else:
            self._index_function(node, module, key, qual, owner, parent, test)

    def _index_class(self, node: ast.ClassDef, module: _Module, key: str, qual: str, test: bool) -> None:
        registered = _registering(_decorator_names(node))
        self._add(Symbol(key, node.name, "class", module.file, node.lineno, root="dekoratörle kayıtlı" if registered else None, test=test))
        self.class_bases[key] = [call_name(b) for b in node.bases]
        self._bodies.append((key, [*node.bases, *[k.value for k in node.keywords]], module.name, None))
        for child in node.body:
            if isinstance(child, DEF_NODES):
                owner = None if isinstance(child, ast.ClassDef) else key
                self._index_def(child, module, owner, key, test, f"{qual}.")
            else:
                self._class_statement(child, key, module)

    def _index_function(self, node: ast.FunctionDef, module: _Module, key: str, qual: str,
                        owner: str | None, parent: str, test: bool) -> None:
        decorators = _decorator_names(node)
        registered = _registering(decorators)
        self._add(Symbol(
            key, node.name, "method" if owner else "function", module.file, node.lineno, owner=owner, test=test,
            root=self._root_reason(node, registered, test and node.name.startswith("test")),
            route=any(d.rsplit(".", 1)[-1] in ROUTE_DECORATORS for d in registered),
            pure_only=any(d.rsplit(".", 1)[-1] in {"overload", "abstractmethod"} for d in decorators),
        ))
        if owner:
            self.class_methods[owner][node.name] = key
            self.methods_by_name[node.name].add(key)
        elif self.symbols[parent].kind in {"function", "method"}:
            self.edges[parent].add(key)   # a nested function lives as long as its enclosing function
        self._bodies.append((key, [*node.args.defaults, *[d for d in node.args.kw_defaults if d]], module.name, owner))
        body = [child for child in node.body if not isinstance(child, DEF_NODES)]
        for child in node.body:
            if isinstance(child, DEF_NODES):
                self._index_def(child, module, None, key, test, f"{qual}.<locals>.")
        self._bodies.append((key, body, module.name, owner))

    @staticmethod
    def _root_reason(node: ast.AST, registered: list[str], is_test_fn: bool) -> str | None:
        if is_test_fn:
            return "test"
        if registered:
            return "dekoratörle kayıtlı"
        if node.name.startswith("__") and node.name.endswith("__"):
            return "özel metot"
        return None

    def _class_statement(self, node: ast.AST, class_key: str, module: _Module) -> None:
        """`_t_Tuple = _t_Set = _t_List` inside a class makes method aliases."""
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            self._aliases += [(class_key, t.id, node.value.id) for t in node.targets if isinstance(t, ast.Name)]
        self._bodies.append((class_key, [node], module.name, class_key))

    # --- class hierarchy ---------------------------------------------------------------------------------
    def _link_classes(self) -> None:
        self._resolve_bases()
        self._apply_aliases()
        self._class_callbacks()

    def _resolve_bases(self) -> None:
        keys_by_name: dict[str, set[str]] = defaultdict(set)
        for key, symbol in self.symbols.items():
            if symbol.kind == "class":
                keys_by_name[symbol.name].add(key)
        for key, bases in self.class_bases.items():
            for base in bases:
                local = keys_by_name.get(base.rsplit(".", 1)[-1], set())
                self.parents[key] |= local
                for parent in local:
                    self.children[parent].add(key)
                if not local and base not in NEUTRAL_BASES and not base.startswith(("typing.", "Generic[")):
                    self.external_base.add(key)

    def _apply_aliases(self) -> None:
        for owner, alias, target in self._aliases:
            if target in self.class_methods[owner]:
                self.class_methods[owner][alias] = self.class_methods[owner][target]
                self.methods_by_name[alias].add(self.class_methods[owner][target])

    def _class_callbacks(self) -> None:
        """Protocol methods, and every method of a framework subclass, live as long as their class."""
        for owner, methods in self.class_methods.items():
            for key in methods.values():
                if key in self.symbols and (owner in self.external_base or self.symbols[key].root):
                    self.edges[owner].add(key)

    def family(self, class_key: str) -> set[str]:
        """The class, its project ancestors and descendants (overrides may be called through either)."""
        seen, queue = {class_key}, deque([class_key])
        while queue:
            current = queue.popleft()
            for other in (self.parents[current] | self.children[current]) - seen:
                seen.add(other)
                queue.append(other)
        return seen

    # --- reference resolution ---------------------------------------------------------------------------
    def _methods_named(self, name: str, classes: set[str] | None = None) -> set[str]:
        if classes is None:
            return set(self.methods_by_name.get(name, ()))
        return {self.class_methods[c][name] for c in classes if name in self.class_methods[c]}

    def _lookup(self, module_key: str, name: str, depth: int = 0) -> set[str]:
        """`name` as seen from a module, following re-exports (`from .engine import x` in `__init__.py`)."""
        module = self.modules.get(module_key)
        if module is None or depth > 6:
            return set()
        if name in module.scope:
            return {module.scope[name]}
        if name in module.imported:
            return self._lookup(*module.imported[name], depth + 1)
        if name in module.modules and module.modules[name] in self.modules:
            return {f"{self.modules[module.modules[name]].name}:<module>"}
        return set()

    def _class_of(self, value: ast.expr, module: _Module) -> str | None:
        if not isinstance(value, ast.Name):
            return None
        return next((k for k in self._lookup(module.name, value.id) if self.symbols.get(k) and self.symbols[k].kind == "class"), None)

    def _resolve_attribute(self, node: ast.Attribute, module: _Module, owner: str | None) -> set[str]:
        value, attr = node.value, node.attr
        if owner and (isinstance(value, ast.Name) and value.id in {"self", "cls"}):
            return self._methods_named(attr, self.family(owner)) or self._methods_named(attr)
        if owner and isinstance(value, ast.Call) and call_name(value.func) == "super":
            return self._methods_named(attr, self.family(owner))
        if isinstance(value, ast.Name) and module.modules.get(value.id) in self.modules:
            return self._lookup(module.modules[value.id], attr)
        if class_key := self._class_of(value, module):
            return self._methods_named(attr, self.family(class_key)) or self._methods_named(attr)
        # Unknown receiver: keep every same-named method alive rather than guess.
        return self._methods_named(attr) | ({module.scope[attr]} if attr in module.scope else set())

    def _methods_with_prefix(self, prefix: str, classes: set[str] | None) -> set[str]:
        pool = [self.class_methods[c] for c in classes] if classes else list(self.class_methods.values())
        return {key for methods in pool for method, key in methods.items() if method.startswith(prefix)}

    def _getattr_targets(self, node: ast.Call, owner: str | None) -> set[str]:
        """getattr(obj, "name") and getattr(self, f"prefix_{…}") dispatch."""
        if call_name(node.func) != "getattr" or len(node.args) < 2:
            return set()
        name = node.args[1]
        on_self = owner and isinstance(node.args[0], ast.Name) and node.args[0].id == "self"
        classes = self.family(owner) if on_self else None
        if isinstance(name, ast.Constant) and isinstance(name.value, str):
            return self._methods_named(name.value, classes)
        if isinstance(name, ast.JoinedStr) and name.values and isinstance(name.values[0], ast.Constant):
            return self._methods_with_prefix(str(name.values[0].value), classes)
        return set()

    def _targets(self, node: ast.AST, module: _Module, owner: str | None) -> set[str]:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            return self._lookup(module.name, node.id)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            return self._resolve_attribute(node, module, owner)
        if isinstance(node, ast.Call):
            return self._getattr_targets(node, owner)
        return set()

    def _refs(self, source: str, root: ast.AST, module_key: str, owner: str | None) -> None:
        module = self.modules[module_key]
        for node in ast.walk(root):
            for target in self._targets(node, module, owner) - {source}:
                if target not in self.symbols:
                    continue
                self.edges[source].add(target)
                if self.symbols[target].owner:
                    self.edges[source].add(self.symbols[target].owner)   # calling a method implies the class exists

    # --- queries ------------------------------------------------------------------------------------------
    def reachable(self, roots: set[str]) -> set[str]:
        seen, queue = set(roots), deque(roots)
        while queue:
            for target in self.edges.get(queue.popleft(), set()) - seen:
                seen.add(target)
                queue.append(target)
        return seen

    def script_roots(self) -> set[str]:
        """`[project.scripts] name = "pkg.module:function"` entries."""
        roots = set()
        for path in self.project.at_root("pyproject.toml"):
            try:
                scripts = tomllib.loads(self.project.text(path) or "").get("project", {}).get("scripts", {})
            except tomllib.TOMLDecodeError:
                continue
            for target in scripts.values():
                module, _, func = str(target).partition(":")
                roots |= self._lookup(module, func) if module in self.modules else set()
        return roots


def build_call_graph(project: ProjectFiles) -> CallGraph:
    return CallGraph(project)
