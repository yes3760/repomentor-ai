"""Fixes for the two most common injection flows, rewritten so the user value never becomes code.

* SQL built with an f-string or `+` directly inside `execute()` becomes a parameterised query:
  `cur.execute(f"... WHERE ad = '{ad}'")` → `cur.execute("... WHERE ad = ?", (ad,))`.
  A quoted value with surrounding text keeps it in the parameter (`LIKE '%{q}%'` → `LIKE ?`,
  `f"%{q}%"`); the placeholder follows the driver the project imports (`?` for sqlite3, `%s`
  for psycopg / PyMySQL / MySQL Connector, where a literal `%` must then be written `%%`).
* A shell command built the same way for `os.system()` or `subprocess.*(shell=True)` becomes an
  argument list run without a shell: `os.system("cp a " + x)` → `subprocess.run(["cp", "a", x])`.

Only confirmed taint flows are touched, and only when the rewrite keeps the meaning for honest
input. Anything uncertain is left alone: an unknown driver, a value inside a double-quoted SQL
identifier, `{x!r}` / `{x:>5}` formatting, shell syntax such as pipes, redirects or `$VAR`, a
call that already has parameters. `autofix` re-runs the taint analysis on every rewrite and drops
the ones after which the flow is still there.
"""

from __future__ import annotations

import ast
import json
import re
import shlex
from dataclasses import dataclass

from repomentor.analyzer.taint.sinks import SQL_METHODS, SUBPROCESS_CALLS
from repomentor.analyzer.taint.sources import call_name

QMARK_DRIVERS = {"sqlite3", "aiosqlite"}
FORMAT_DRIVERS = {"psycopg2", "psycopg", "pymysql", "MySQLdb", "mysql.connector", "mysql"}
SHELL_SYNTAX = set("|&;<>()$`*?[]{}~!\n\\")
SENTINEL = re.compile("\x00(\\d+)\x00")


@dataclass
class CallFix:
    """Replace one call expression; `kind` is the taint kind the rewrite closes."""

    node: ast.Call
    text: str
    kind: str            # "sql" | "command"
    rule: str
    change: str
    needs_subprocess: bool = False


# --- Strings built from pieces ---------------------------------------------------------------------------------

def string_parts(node: ast.expr) -> list[str | ast.expr] | None:
    """Literal text and inserted expressions of an f-string or a `+` chain; None for anything else."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return _joined_parts(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = string_parts(node.left), string_parts(node.right)
        return None if left is None or right is None else left + right
    return [node] if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)) else None


def _joined_parts(node: ast.JoinedStr) -> list[str | ast.expr] | None:
    parts: list[str | ast.expr] = []
    for value in node.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        elif value.conversion != -1 or value.format_spec is not None:
            return None            # {x!r} / {x:>5} would change the text the database receives
        else:
            parts.append(value.value)
    return parts


def _items(parts: list[str | ast.expr]) -> list[str | ast.expr]:
    """Characters and expressions, one item each."""
    return [char for part in parts for char in (part if isinstance(part, str) else [part])]


def _fstring(items: list[str | ast.expr]) -> ast.expr:
    """One expression for literal text mixed with values: `%` + q + `%` → f"%{q}%"."""
    values: list[ast.expr] = []
    for item in items:
        if isinstance(item, str):
            if values and isinstance(values[-1], ast.Constant):
                values[-1] = ast.Constant(values[-1].value + item)
            else:
                values.append(ast.Constant(item))
        else:
            values.append(ast.FormattedValue(value=item, conversion=-1, format_spec=None))
    if len(values) == 1 and not isinstance(values[0], ast.Constant):
        return values[0].value
    return ast.JoinedStr(values=values)


# --- SQL ------------------------------------------------------------------------------------------------------

def sql_placeholder(imported: set[str]) -> str | None:
    """`?` or `%s`, decided by the database driver; None when there is none or more than one style."""
    styles = {"?" for name in imported if name in QMARK_DRIVERS} | {"%s" for name in imported if name in FORMAT_DRIVERS}
    return styles.pop() if len(styles) == 1 else None


class _SqlTemplate:
    """Walk the query text: values outside quotes and quoted literals holding values become placeholders."""

    def __init__(self, placeholder: str):
        self.placeholder = placeholder
        self.sql: list[str] = []
        self.params: list[ast.expr] = []
        self.literal: list[str | ast.expr] | None = None     # inside '...'
        self.identifier = False                               # inside "..."

    def text(self, char: str) -> str:
        return "%%" if char == "%" and self.placeholder == "%s" else char

    def feed(self, item: str | ast.expr) -> bool:
        """False when the query cannot be parameterised safely."""
        if self.identifier:
            if not isinstance(item, str):
                return False                     # a table or column name cannot be a parameter
            self.identifier = item != '"'
            self.sql.append(item)
        elif self.literal is not None:
            self._in_literal(item)
        elif isinstance(item, str):
            self._outside(item)
        else:
            self.sql.append(self.placeholder)
            self.params.append(_unwrap_str(item))
        return True

    def _outside(self, char: str) -> None:
        if char == "'":
            self.literal = []
        elif char == '"':
            self.identifier = True
            self.sql.append(char)
        else:
            self.sql.append(self.text(char))

    def _in_literal(self, item: str | ast.expr) -> None:
        if item != "'":
            self.literal.append(item)            # "''" arrives as one item: an escaped quote inside the literal
            return
        literal, self.literal = self.literal, None
        if any(not isinstance(i, str) for i in literal):
            self.sql.append(self.placeholder)
            self.params.append(_fstring(["'" if i == "''" else i for i in literal]))   # '' is one quote in the value
        else:
            self.sql.append("'" + "".join(self.text(c) for c in literal) + "'")


def _unwrap_str(node: ast.expr) -> ast.expr:
    """`str(user_id)` in an unquoted position binds the value itself."""
    if isinstance(node, ast.Call) and call_name(node.func) == "str" and len(node.args) == 1 and not node.keywords:
        return node.args[0]
    return node


def parameterise(parts: list[str | ast.expr], placeholder: str) -> tuple[str, list[ast.expr]] | None:
    """(query text, parameter expressions), or None when the query is not a plain template."""
    template = _SqlTemplate(placeholder)
    items, index = _items(parts), 0
    while index < len(items):
        if template.literal is not None and items[index] == "'" and items[index + 1:index + 2] == ["'"]:
            template.literal.append("''")        # SQL writes a quote inside a literal as ''
            index += 2
            continue
        if not template.feed(items[index]):
            return None
        index += 1
    if template.literal is not None or template.identifier or not template.params:
        return None
    return "".join(template.sql), template.params


def _sql_fix(node: ast.Call, source: str, placeholder: str | None) -> CallFix | None:
    if placeholder is None or len(node.args) != 1 or node.keywords or call_name(node.func).rsplit(".", 1)[-1] not in SQL_METHODS:
        return None
    parts = string_parts(node.args[0])
    result = parameterise(parts, placeholder) if parts else None
    if result is None:
        return None
    sql, params = result
    func = ast.get_source_segment(source, node.func)
    text = f"{func}({json.dumps(sql, ensure_ascii=False)}, {ast.unparse(ast.Tuple(elts=params, ctx=ast.Load()))})"
    return CallFix(node, text, "sql", "TNT003",
                   f"satır {node.lineno}: SQL sorgusu parametreli hale getirildi (`{placeholder}` yer tutucusu); "
                   "kullanıcı değeri artık sorgunun parçası değil, SQL enjeksiyonu kapandı")


# --- Shell commands ---------------------------------------------------------------------------------------------

def _uses_shell_syntax(parts: list[str | ast.expr]) -> bool:
    return any(char in SHELL_SYNTAX for part in parts if isinstance(part, str) for char in part)


def _argument(token: str, parts: list[str | ast.expr]) -> ast.expr:
    """One argv entry: literal text, a value, or both glued together (`yedek/` + name)."""
    items: list[str | ast.expr] = []
    for position, piece in enumerate(SENTINEL.split(token)):       # text, index, text, index, …
        items += list(piece) if position % 2 == 0 else [parts[int(piece)]]
    return _fstring(items) if any(not isinstance(i, str) for i in items) else ast.Constant("".join(items))


def shell_arguments(parts: list[str | ast.expr]) -> list[ast.expr] | None:
    """The argv list a shell would build from the command, or None when it uses shell syntax."""
    if _uses_shell_syntax(parts):
        return None
    combined = "".join(part if isinstance(part, str) else f"\x00{index}\x00" for index, part in enumerate(parts))
    try:
        tokens = shlex.split(combined, posix=True)
    except ValueError:
        return None
    return [_argument(token, parts) for token in tokens] or None


def _shell_call(node: ast.Call) -> str | None:
    """"os.system" or "subprocess" when the call runs its single argument through a shell."""
    name = call_name(node.func)
    if len(node.args) != 1:
        return None
    if name == "os.system" and not node.keywords:
        return "os.system"
    shell = any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords)
    return "subprocess" if shell and name.startswith("subprocess.") and name.rsplit(".", 1)[-1] in SUBPROCESS_CALLS else None


def _command_text(node: ast.Call, source: str, kind: str, argv: str, value_used: bool) -> str:
    if kind == "subprocess":      # same call, list instead of string, no shell=True
        rest = [ast.get_source_segment(source, k) for k in node.keywords if k.arg != "shell"]
        return f"{ast.get_source_segment(source, node.func)}({', '.join([argv, *rest])})"
    return f"subprocess.run({argv})" + (".returncode" if value_used else "")   # os.system returns the exit status


def _command_fix(node: ast.Call, source: str, value_used: bool) -> CallFix | None:
    kind = _shell_call(node)
    parts = string_parts(node.args[0]) if kind else None
    arguments = shell_arguments(parts) if parts else None
    if arguments is None:
        return None
    argv = ast.unparse(ast.List(elts=arguments, ctx=ast.Load()))
    return CallFix(node, _command_text(node, source, kind, argv, value_used), "command", "TNT002",
                   f"satır {node.lineno}: kabuk komutu argüman listesine çevrildi (kabuk yok); "
                   "kullanıcı değeri tek bir argüman olarak kalıyor, komut enjeksiyonu kapandı", needs_subprocess=kind == "os.system")


# --- Entry point -------------------------------------------------------------------------------------------------

def _value_used(tree: ast.Module, node: ast.Call) -> bool:
    return not any(isinstance(n, ast.Expr) and n.value is node for n in ast.walk(tree))


def call_fixes(tree: ast.Module, source: str, sink_lines: dict[int, set[str]], imported: set[str]) -> list[CallFix]:
    """Rewrites for the sink calls on `sink_lines` ({line: {"sql", "command"}}) of one module."""
    placeholder = sql_placeholder(imported)
    fixes = []
    for node in ast.walk(tree):
        kinds = sink_lines.get(getattr(node, "lineno", 0), set()) if isinstance(node, ast.Call) else set()
        fix = (_sql_fix(node, source, placeholder) if "sql" in kinds else None) or \
              (_command_fix(node, source, _value_used(tree, node)) if "command" in kinds else None)
        if fix is not None:
            fixes.append(fix)
    return fixes


def imported_modules(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
    return names
