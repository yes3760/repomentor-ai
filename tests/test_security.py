import ast

import pytest

from repomentor.analyzer.file_tree import scan_project
from repomentor.analyzer.security_analyzer import analyze_security, classify_call


def rule_ids(result):
    return {i.rule_id for i in result.issues}


def test_problematic_project_security_findings(problematic_result):
    ids = rule_ids(problematic_result)
    expected = {"SEC002", "SEC004", "SEC005", "SEC011", "SEC012", "SEC015", "SEC016"}
    assert expected <= ids
    # eval / os.system / SQL receive request data, so the confirmed flows replace the pattern findings.
    assert {"TNT001", "TNT002", "TNT003"} <= ids
    assert not {"SEC010", "SEC013", "SEC014"} & ids


def test_secret_values_never_leak_into_report(problematic_result):
    from repomentor.analyzer.report_builder import build_json, build_markdown

    for report in (build_markdown(problematic_result), build_json(problematic_result)):
        assert "Ankara2024!" not in report
        assert "a1b2c3d4e5f6g7h8i9j0-demo-not-real" not in report


def test_clean_project_has_no_security_issues(clean_result):
    assert not [i for i in clean_result.issues if i.category == "security"]
    assert clean_result.security.gitignore_covers_env


@pytest.mark.parametrize(
    ("code", "rule"),
    [
        ("eval(x)", "SEC010"),
        ("pickle.loads(data)", "SEC011"),
        ("yaml.load(f)", "SEC012"),
        ("subprocess.run(cmd, shell=True)", "SEC013"),
        ("os.system('ls ' + name)", "SEC013"),
        ("cur.execute(f'SELECT * FROM t WHERE id={i}')", "SEC014"),
        ("cur.execute('SELECT * FROM t WHERE id=%s' % i)", "SEC014"),
        ("requests.get(url, verify=False)", "SEC015"),
        ("app.run(debug=True)", "SEC016"),
        ("hashlib.md5(data)", "SEC017"),
    ],
)
def test_dangerous_call_rules(code, rule):
    assert classify_call(ast.parse(code).body[0].value) == rule


@pytest.mark.parametrize(
    "code",
    [
        "yaml.load(f, Loader=yaml.SafeLoader)",
        "yaml.safe_load(f)",
        "subprocess.run(['ls', '-l'])",
        "cur.execute('SELECT * FROM t WHERE id = ?', (i,))",
        "requests.get(url, timeout=5)",
        "hashlib.md5(data, usedforsecurity=False)",
        "ast.literal_eval(x)",
    ],
)
def test_safe_calls_are_not_flagged(code):
    assert classify_call(ast.parse(code).body[0].value) is None


def test_fake_passwords_in_tests_are_ignored(make_project):
    root = make_project({
        "app.py": "def f():\n    return 1\n",
        "tests/test_login.py": 'PASSWORD = "hunter2hunter2"\n\ndef test_login():\n    assert PASSWORD\n',
        ".gitignore": ".env\n",
    })
    _, issues = analyze_security(scan_project(root), "local", run_tools=False)
    assert "SEC002" not in {i.rule_id for i in issues}


def test_env_in_zip_covered_by_gitignore_is_low(make_project):
    root = make_project({".env": "TOKEN=real-value\n", ".gitignore": ".env\n", "app.py": "import os\nos.getenv('TOKEN')\n"})
    _, issues = analyze_security(scan_project(root), "zip", run_tools=False)
    env = [i for i in issues if i.rule_id in {"SEC003", "SEC004"}]
    assert [i.rule_id for i in env] == ["SEC003"]
    assert env[0].severity == "low"


def test_empty_env_template_is_fine(make_project):
    root = make_project({".env": "TOKEN=\n# comment\n", ".gitignore": ".env\n", "app.py": "x = 1\n"})
    _, issues = analyze_security(scan_project(root), "github", run_tools=False)
    assert not [i for i in issues if i.rule_id in {"SEC003", "SEC004"}]


def test_bandit_runs(problematic_result):
    assert problematic_result.security.bandit_ran


def test_widget_keys_are_not_secrets(make_project):
    """Regression: Streamlit `key="..."` arguments were reported as hardcoded API keys."""
    secret = "sk-live-" + "4f9a8b7c6d5e4f3a2b1c"
    root = make_project({
        "app.py": 'import streamlit as st\nst.button("Kaydet", key="save-button")\nst.toggle("x", key="osv-enabled")\n'
                  f'cache = {{"key": "user-settings"}}\nkey = "{secret}"\n',
        ".gitignore": ".env\n",
    })
    _, issues = analyze_security(scan_project(root), "local", run_tools=False)
    hits = [i for i in issues if i.rule_id == "SEC002"]
    assert len(hits) == 1 and [loc.line for loc in hits[0].locations] == [5]
