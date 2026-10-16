"""Where user input enters (sources), what clears it (sanitisers), and small AST helpers."""

from __future__ import annotations

import ast

from repomentor.analyzer.taint.model import Taint

REQUEST_NAMES = {"request", "req"}
REQUEST_ATTRS = {
    "args", "form", "values", "json", "data", "files", "cookies", "headers", "GET", "POST", "FILES", "COOKIES",
    "body", "query_params", "path_params", "get_json", "get_data", "query_string", "stream",
}
STREAMLIT_TEXT_INPUTS = {"text_input", "text_area", "chat_input"}
ROUTE_DECORATORS = {"route", "get", "post", "put", "patch", "delete", "api_route", "websocket", "head", "options"}
NON_INPUT_PARAMS = {"self", "cls", "request", "req", "response", "db", "session", "background_tasks"}
VALIDATED_TYPES = {"int", "float", "bool", "UUID", "uuid.UUID", "date", "datetime", "Decimal", "PositiveInt"}

# --- Sanitisers (return a value that is safe for every sink we check) ----------------------------

SANITIZERS = {
    "int", "float", "bool", "len", "abs", "round", "hash", "id", "ord", "isinstance", "callable",
    "shlex.quote", "quote", "html.escape", "escape", "markupsafe.escape", "bleach.clean", "secure_filename",
    "os.path.basename", "uuid.UUID", "UUID", "re.escape", "int.from_bytes", "hashlib.sha256",
}

def call_name(node: ast.AST) -> str:
    """Dotted name of a call target: `os.path.join`, `cur.execute`, `eval`."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append(call_name(node.func) + "()")
    return ".".join(reversed(parts))


PROCESS_EXITS = {"sys.exit", "exit", "quit", "os._exit", "os.abort"}
EXIT_CALLS = PROCESS_EXITS | {"abort", "flask.abort"}   # flask's abort() raises an HTTP error


def ends_flow(statement: ast.AST) -> bool:
    """`return`, `raise`, `sys.exit()`, `abort()`: nothing after this statement runs."""
    if isinstance(statement, (ast.Return, ast.Raise)):
        return True
    return isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call) and call_name(statement.value.func) in EXIT_CALLS


def _short(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _snippet(node: ast.AST, limit: int = 70) -> str:
    text = ast.unparse(node)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _kwarg(node: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in node.keywords if kw.arg == name), None)


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _attribute_source(node: ast.Attribute) -> Taint | None:
    if not isinstance(node.value, ast.Name):
        return None
    owner, line = node.value.id, node.lineno
    if owner in REQUEST_NAMES and node.attr in REQUEST_ATTRS:
        return Taint(f"{owner}.{node.attr}", line)
    if (owner, node.attr) == ("sys", "argv"):
        return Taint("sys.argv", line, remote=False)
    if owner in {"st", "streamlit"} and node.attr == "query_params":
        return Taint("st.query_params", line)
    return None


def _call_source(node: ast.Call) -> Taint | None:
    name = call_name(node.func)
    if name == "input" or name in {"sys.stdin.read", "sys.stdin.readline"}:
        return Taint(f"{name}()", node.lineno, remote=False)
    if name.split(".")[0] in {"st", "streamlit"} and _short(name) in STREAMLIT_TEXT_INPUTS:
        return Taint(f"st.{_short(name)}()", node.lineno)
    return None


def source_of(node: ast.AST) -> Taint | None:
    """A Taint if `node` itself reads user input."""
    if isinstance(node, ast.Attribute):
        return _attribute_source(node)
    if isinstance(node, ast.Call):
        return _call_source(node)
    return None
