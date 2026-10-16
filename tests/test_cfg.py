"""Control-flow graph: unreachable code, resource leaks and guard-aware taint."""

import ast
import textwrap

import pytest

from repomentor.analyzer.cfg import analyze_flow, build_cfg, leaked_resources, resource_factories, unreachable_statements
from repomentor.analyzer.file_tree import scan_project
from repomentor.analyzer.taint import find_taint_flows
from tests.conftest import ROOT


def function(code: str) -> ast.FunctionDef:
    return ast.parse(textwrap.dedent(code)).body[0]


def dead_lines(code: str) -> list[int]:
    return [s.lineno for s in unreachable_statements(function(code))]


def leaks(code: str, factories: dict[str, str] | None = None) -> list[str]:
    return [name for _, name, _ in leaked_resources(function(code), factories)]


def test_graph_shape():
    cfg = build_cfg(function("def f(x):\n    if x:\n        return 1\n    return 2\n").body)
    assert len(cfg.nodes) == 5 and cfg.exit in cfg.reachable({cfg.entry})


# --- Unreachable code ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(("code", "lines"), [
    ("def f(x):\n    return x\n    print(1)\n    print(2)\n", [3]),                       # one region, reported once
    ("def f(xs):\n    for x in xs:\n        continue\n        print(x)\n", [4]),
    ("def f():\n    while True:\n        work()\n    cleanup()\n", [4]),                   # infinite loop without break
    ("def f():\n    if False:\n        debug()\n    sys.exit(1)\n    print('bye')\n", [3, 5]),
    ("def f(x):\n    if x:\n        raise ValueError\n    else:\n        return 1\n    "
     "for i in x:\n        print(i)\n", [6]),                                                # dead loop counted once
    ("def f(x):\n    match x:\n        case 1:\n            return 'a'\n        case _:\n            return 'b'\n    "
     "print(x)\n", [7]),
])
def test_unreachable_code_is_found(code, lines):
    assert dead_lines(code) == lines


@pytest.mark.parametrize("code", [
    "def f():\n    while True:\n        if done():\n            break\n    cleanup()\n",
    "def f():\n    try:\n        return compute()\n    except ValueError:\n        log()\n    return None\n",
    "def f():\n    try:\n        return compute()\n    finally:\n        cleanup()\n",          # finally always runs
    "def f():\n    with contextlib.suppress(KeyError):\n        return d['k']\n    return None\n",  # suppressed
    "def f():\n    raise NotImplementedError\n    yield\n",                                    # generator marker
    "def f(x):\n    match x:\n        case 1:\n            return 'a'\n    return 'b'\n",
    "def f(xs):\n    for x in xs:\n        if x:\n            break\n    else:\n        return None\n    return x\n",
])
def test_reachable_code_is_not_flagged(code):
    assert dead_lines(code) == []


# --- Resource leaks -----------------------------------------------------------------------------------------

@pytest.mark.parametrize(("code", "names"), [
    ("def f(p):\n    f = open(p)\n    return f.read()\n", ["f"]),
    ("def f(p):\n    f = open(p)\n    if not p:\n        return None\n    data = f.read()\n    f.close()\n    return data\n", ["f"]),
    ("def f(p):\n    f = open(p)\n    data = json.load(f)\n    return data\n", ["f"]),         # json.load only borrows
    ("def f(db):\n    conn = sqlite3.connect(db)\n    with conn:\n        conn.execute('x')\n", ["conn"]),   # commits, never closes
    ("def f(p):\n    f = open(p)\n    try:\n        data = f.read()\n        f.close()\n    except OSError:\n"
     "        return None\n    return data\n", ["f"]),                                         # not closed on the error path
])
def test_leaks_are_found(code, names):
    assert leaks(code) == names


@pytest.mark.parametrize("code", [
    "def f(p):\n    with open(p) as f:\n        return f.read()\n",
    "def f(p):\n    f = open(p)\n    try:\n        if not p:\n            return None\n        return f.read()\n    finally:\n        f.close()\n",
    "def f(p):\n    try:\n        f = open(p)\n    except OSError:\n        return None\n    with f:\n        return f.read()\n",
    "def f(p):\n    f = open(p)\n    return f\n",                                               # handed to the caller
    "def f(self, p):\n    f = open(p)\n    self.handle = f\n",                                    # stored on the object
    "def f(p):\n    f = open(p)\n    yield f\n    f.close()\n",
    "def f(p):\n    f = open(p)\n    atexit.register(f.close)\n",
    "def f(p, own):\n    if own:\n        f = open(p)\n    else:\n        f = None\n    work(p)\n    if f is not None:\n        f.close()\n",
    "def f(p):\n    f = open(p)\n    if not p:\n        sys.exit(1)\n    f.close()\n",                # the process ends
    "def f(fd):\n    s = socket.socket(fileno=fd)\n    return s.getpeername()\n",                  # wraps the caller's descriptor
    "def f(db):\n    conn = sqlite3.connect(db)\n    with contextlib.closing(conn):\n        conn.execute('x')\n",
])
def test_released_resources_are_not_flagged(code):
    assert leaks(code) == []


def test_factories_are_followed_across_functions():
    module = ast.parse("import sqlite3\ndef db():\n    return sqlite3.connect('x.db')\n"
                       "@contextmanager\ndef session():\n    return sqlite3.connect('x.db')\n")
    factories = resource_factories([("app.py", module)])
    assert factories == {"db": "sqlite3.connect"}, "decorated helpers manage their own resource"
    assert leaks("def view():\n    conn = db()\n    return conn.execute('x').fetchall()\n", factories) == ["conn"]


def test_problematic_example(problematic_result):
    found = {(f.rule, f.line, f.function) for f in problematic_result.quality.flow}
    assert found == {("QLT015", 26, "ogrenci_bul"), ("QLT014", 126, "hava_durumu")}
    issue = next(i for i in problematic_result.issues if i.rule_id == "QLT015")
    assert "SQLite bağlantısı" in issue.explanation
    assert any(f.label == "Erişilemeyen kod (1)" for f in problematic_result.score.category("quality").factors)


def test_repomentor_and_clean_example_have_no_flow_findings(clean_result):
    assert clean_result.quality.flow == []
    findings, _ = analyze_flow(scan_project(ROOT))
    assert findings == [], "RepoMentor's own code must have no dead code or unclosed resources"


# --- Guard-aware taint --------------------------------------------------------------------------------------

GUARDED = '''
import os, re
from pathlib import Path
from flask import Flask, request, abort
app = Flask(__name__)
ALLOWED = {"a", "b"}
BASE = Path("/srv")


@app.route("/digits")
def digits():
    code = request.args.get("code")
    if not code.isdigit():
        abort(400)
    os.system("echo " + code)


@app.route("/allow")
def allow():
    name = request.args.get("name")
    if name not in ALLOWED:
        return "no"
    os.system("echo " + name)


@app.route("/branch")
def branch():
    x = request.args.get("x")
    if x.isalnum():
        os.system("echo " + x)
    else:
        os.system("echo " + x)


@app.route("/nested")
def nested():
    x = request.args.get("x")
    if request.args.get("mode"):
        if not x.isdigit():
            abort(400)
    os.system("echo " + x)


@app.route("/prefix")
def prefix():
    x = request.args.get("x")
    if not x.startswith("/safe"):
        abort(400)
    os.system("echo " + x)


@app.route("/member")
def member():
    x = request.args.get("x")
    if x not in request.args:
        abort(400)
    os.system("echo " + x)


@app.route("/both")
def both():
    a = request.args.get("a")
    b = request.args.get("b")
    if not re.fullmatch(r"[a-z]+", a) or not b.isdigit():
        return "bad"
    os.system(f"echo {a} {b}")


@app.route("/file")
def file():
    p = request.args.get("p")
    if not (BASE / p).resolve().is_relative_to(BASE):
        abort(403)
    return open(BASE / p).read()
'''


def test_guards_clear_validated_input(make_project):
    flows, _ = find_taint_flows(scan_project(make_project({"web.py": GUARDED})))
    reported = sorted(f.function for f in flows)
    # validated: digits, allow, both, file and the `if x.isalnum():` branch
    # still reported: the unvalidated else branch, a check on one path only, a prefix check, a user-controlled allow-list
    assert reported == ["branch", "member", "nested", "prefix"]
    assert next(f for f in flows if f.function == "branch").line == 32
