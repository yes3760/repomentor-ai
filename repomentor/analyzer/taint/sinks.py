"""Dangerous calls (sinks) and which argument carries the data into them."""

from __future__ import annotations

import ast
import re

from repomentor.analyzer.taint.sources import _is_true, _kwarg, _short, call_name

CODE_SINKS = {"eval", "exec", "compile", "builtins.eval", "builtins.exec"}
COMMAND_SINKS = {"os.system", "os.popen", "subprocess.getoutput", "subprocess.getstatusoutput", "commands.getoutput"}
SUBPROCESS_CALLS = {"run", "call", "Popen", "check_output", "check_call"}
SQL_METHODS = {"execute", "executemany", "executescript", "raw", "mogrify"}
PATH_SINKS = {"open", "io.open", "os.open", "os.remove", "os.unlink", "os.rmdir", "shutil.rmtree", "send_file", "flask.send_file"}
PATH_METHODS = {"open", "read_text", "read_bytes", "write_text", "write_bytes", "unlink", "rmdir"}
DESERIALIZE_SINKS = {"pickle.loads", "pickle.load", "cPickle.loads", "marshal.loads", "dill.loads", "jsonpickle.decode", "yaml.unsafe_load", "shelve.open"}
TEMPLATE_SINKS = {"render_template_string", "flask.render_template_string", "jinja2.Template", "Environment.from_string"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "request"}
HTTP_MODULES = ("requests.", "httpx.")
URL_OPENERS = {"urllib.request.urlopen", "urlopen", "urllib.urlopen"}
REDIRECT_SINKS = {"redirect", "flask.redirect", "HttpResponseRedirect", "RedirectResponse"}
MARKUP_SINKS = {"Markup", "markupsafe.Markup", "mark_safe", "format_html"}

FIXED_HOST = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//[^/?#{}]+[/?#]|^/(?!/)", re.I)


def _url_argument(node: ast.Call, short: str) -> ast.expr | None:
    if (url := _kwarg(node, "url")) is not None:
        return url
    index = 1 if short == "request" else 0
    return node.args[index] if len(node.args) > index else None


def _subprocess_shell(node: ast.Call, name: str) -> bool:
    return name.startswith("subprocess.") and _short(name) in SUBPROCESS_CALLS and _is_true(_kwarg(node, "shell"))


def _unsafe_yaml(node: ast.Call) -> bool:
    loader = _kwarg(node, "Loader") or (node.args[1] if len(node.args) > 1 else None)
    return "Safe" not in (ast.unparse(loader) if loader is not None else "")


def _first(node: ast.Call) -> ast.expr | None:
    return node.args[0] if node.args else None


def _is_http_call(name: str, short: str) -> bool:
    return short in HTTP_METHODS and name.startswith(HTTP_MODULES)


def _markdown_html(node: ast.Call, name: str) -> bool:
    return name in {"st.markdown", "streamlit.markdown", "st.write"} and _is_true(_kwarg(node, "unsafe_allow_html"))


# (kind, predicate(call, name, short) -> bool, which argument carries the data, needs host control)
SINK_RULES: tuple[tuple[str, object, object, bool], ...] = (
    ("code", lambda n, name, short: name in CODE_SINKS, _first, False),
    ("command", lambda n, name, short: name in COMMAND_SINKS or _subprocess_shell(n, name), _first, False),
    ("sql", lambda n, name, short: short in SQL_METHODS or name in {"sqlalchemy.text", "sa.text"}, _first, False),
    ("deserialize", lambda n, name, short: name in DESERIALIZE_SINKS or (name == "yaml.load" and _unsafe_yaml(n)), _first, False),
    ("template", lambda n, name, short: name in TEMPLATE_SINKS or short == "from_string", _first, False),
    ("path", lambda n, name, short: name in PATH_SINKS, _first, False),
    ("path", lambda n, name, short: isinstance(n.func, ast.Attribute) and short in PATH_METHODS, lambda n: n.func.value, False),
    ("ssrf", lambda n, name, short: _is_http_call(name, short), lambda n: _url_argument(n, _short(call_name(n.func))), True),
    ("ssrf", lambda n, name, short: name in URL_OPENERS, _first, True),
    ("redirect", lambda n, name, short: name in REDIRECT_SINKS, _first, True),
    ("xss", lambda n, name, short: name in MARKUP_SINKS or _markdown_html(n, name), _first, False),
)


def _constant_prefix(node: ast.expr) -> str | None:
    """The literal text a string expression starts with, if it starts with one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values and isinstance(node.values[0], ast.Constant):
        return str(node.values[0].value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return _constant_prefix(node.left)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        prefix = _constant_prefix(node.func.value)
        return prefix.split("{", 1)[0] if prefix is not None else None
    return None
