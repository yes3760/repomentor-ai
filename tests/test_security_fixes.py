"""Verified rewrites of SQL and shell-command injection flows."""

import ast
import shutil
import subprocess

import pytest

from repomentor.analyzer.autofix import build_fixes
from repomentor.analyzer.file_tree import scan_project
from repomentor.analyzer.security_fixes import parameterise, shell_arguments, sql_placeholder, string_parts
from repomentor.analyzer.taint import find_taint_flows
from repomentor.ui.visual_views import diff_hunk
from tests.conftest import EXAMPLES, analyze


def sql(expression: str, placeholder: str = "?"):
    parts = string_parts(ast.parse(expression, mode="eval").body)
    result = parameterise(parts, placeholder) if parts else None
    return None if result is None else (result[0], ast.unparse(ast.Tuple(elts=result[1], ctx=ast.Load())))


@pytest.mark.parametrize(("expression", "expected"), [
    ("f\"SELECT * FROM t WHERE ad = '{ad}'\"", ("SELECT * FROM t WHERE ad = ?", "(ad,)")),
    ("f\"SELECT * FROM t WHERE id = {user_id}\"", ("SELECT * FROM t WHERE id = ?", "(user_id,)")),
    ("f\"SELECT * FROM t WHERE name LIKE '%{q}%'\"", ("SELECT * FROM t WHERE name LIKE ?", "(f'%{q}%',)")),
    ("\"SELECT * FROM t WHERE a = '\" + a + \"' AND b = \" + str(b)", ("SELECT * FROM t WHERE a = ? AND b = ?", "(a, b)")),
    ("f\"SELECT * FROM t WHERE note = 'it''s' AND x = {x}\"", ("SELECT * FROM t WHERE note = 'it''s' AND x = ?", "(x,)")),
    ("f\"SELECT * FROM t WHERE n = 'O''{name}'\"", ("SELECT * FROM t WHERE n = ?", "(f\"O'{name}\",)")),
])
def test_queries_become_parameterised(expression, expected):
    assert sql(expression) == expected


def test_percent_signs_are_escaped_for_format_style_drivers():
    assert sql("f\"SELECT * FROM t WHERE x % 2 = 0 AND n LIKE '%{q}%'\"", "%s") == (
        "SELECT * FROM t WHERE x %% 2 = 0 AND n LIKE %s", "(f'%{q}%',)")


@pytest.mark.parametrize("expression", [
    "f'SELECT * FROM \"{table}\"'",                 # an identifier cannot be a parameter
    "f\"SELECT * FROM t WHERE a = {a!r}\"",          # repr changes the text
    "f\"SELECT * FROM t WHERE a = {a:>5}\"",
    "f\"SELECT * FROM t WHERE a = '{a}\"",           # unbalanced quote
    "\"SELECT 1\"",                                  # nothing to parameterise
])
def test_uncertain_queries_are_left_alone(expression):
    assert sql(expression) is None


def test_placeholder_follows_the_driver():
    assert sql_placeholder({"sqlite3", "os"}) == "?"
    assert sql_placeholder({"psycopg2"}) == "%s" and sql_placeholder({"mysql.connector"}) == "%s"
    assert sql_placeholder({"sqlite3", "psycopg2"}) is None and sql_placeholder({"os"}) is None


def argv(expression: str):
    parts = string_parts(ast.parse(expression, mode="eval").body)
    result = shell_arguments(parts) if parts else None
    return None if result is None else ast.unparse(ast.List(elts=result, ctx=ast.Load()))


@pytest.mark.parametrize(("expression", "expected"), [
    ('"cp okul.db yedek/" + isim', "['cp', 'okul.db', f'yedek/{isim}']"),
    ("f\"ls -la '{folder}'\"", "['ls', '-la', folder]"),
    ('"ping -c 1 " + host', "['ping', '-c', '1', host]"),
])
def test_commands_become_argument_lists(expression, expected):
    assert argv(expression) == expected


@pytest.mark.parametrize("expression", ['"cat " + f + " | grep x"', '"echo $HOME " + x', '"ls " + d + " > out.txt"', '"rm *" + x'])
def test_shell_syntax_is_left_alone(expression):
    assert argv(expression) is None


WEB = '''import os
import sqlite3
from flask import Flask, request

app = Flask(__name__)


@app.route("/search")
def search():
    q = request.args.get("q")
    cur = sqlite3.connect("db.sqlite").cursor()
    cur.execute(
        f"SELECT * FROM items WHERE name LIKE '%{q}%'"
    )
    return str(cur.fetchall())


@app.route("/ping")
def ping():
    status = os.system("ping -c 1 " + request.args.get("host"))
    return str(status)


@app.route("/backup")
def backup():
    import subprocess
    subprocess.run("tar czf backup.tgz " + request.args.get("dir"), shell=True, check=True)
    return "ok"
'''


def fixes_for(root):
    project = scan_project(root)
    flows, _ = find_taint_flows(project)
    return project, flows, build_fixes(project, [], run_tools=False, flows=flows)


def test_web_app_fixes_are_verified(make_project):
    root = make_project({"web.py": WEB})
    _, before, report = fixes_for(root)
    assert {f.kind for f in before} == {"sql", "command"}
    fix = report.files[0]
    assert fix.rules == ["TNT002", "TNT003"] and all(c.endswith("(doğrulandı)") for c in fix.changes)
    assert '+    cur.execute("SELECT * FROM items WHERE name LIKE ?", (f\'%{q}%\',))' in fix.diff, "a multi-line call is replaced whole"
    assert "+    status = subprocess.run(['ping', '-c', '1', request.args.get('host')]).returncode" in fix.diff
    assert "+    subprocess.run(['tar', 'czf', 'backup.tgz', request.args.get('dir')], check=True)" in fix.diff
    assert fix.diff.count("+import subprocess") == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="git yok")
def test_patched_example_has_no_injection_left(tmp_path):
    project = tmp_path / "problematic"
    shutil.copytree(EXAMPLES / "problematic_project", project)
    before = analyze(project, check_dependencies=False)
    assert {"TNT002", "TNT003"} <= {i.rule_id for i in before.issues} <= before.fixes.rules | {i.rule_id for i in before.issues}
    subprocess.run(["git", "apply", "-"], cwd=project, input=before.fixes.patch.encode(), check=True, capture_output=True)
    compile((project / "app.py").read_text(encoding="utf-8"), "app.py", "exec")
    after = analyze(project, check_dependencies=False)
    assert not {"TNT002", "TNT003"} & {i.rule_id for i in after.issues}, "the patch closes both injections"
    assert "TNT001" in {i.rule_id for i in after.issues}, "eval() has no mechanical fix and is still reported"
    assert after.score.overall > before.score.overall


def test_unknown_driver_or_helper_sinks_are_not_touched(make_project):
    root = make_project({
        "db.py": "def run(cur, sql):\n    cur.execute(sql)\n",
        "web.py": "from flask import request\nfrom db import run\n\n\ndef view(cur):\n"
                  "    cur.execute(f\"SELECT * FROM t WHERE a = '{request.args['a']}'\")\n    run(cur, 'x' + request.args['b'])\n",
    })
    _, flows, report = fixes_for(root)
    assert flows and report.files == [], "no driver import: the placeholder style is unknown"


def test_diff_hunk_picks_the_changed_line():
    diff = ("--- a/app.py\n+++ b/app.py\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n@@ -20,3 +20,3 @@\n x\n-y\n+Y\n z\n")
    assert diff_hunk(diff, 21) == "--- a/app.py\n+++ b/app.py\n@@ -20,3 +20,3 @@\n x\n-y\n+Y\n z\n"
    assert diff_hunk(diff, 10) == ""
