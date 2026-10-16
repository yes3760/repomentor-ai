"""Automatic fixes: a reviewable patch, never a write to the analysed project."""

import shutil
import subprocess

import pytest

from repomentor.analyzer.autofix import build_fixes, environment_names, unified_diff
from repomentor.analyzer.file_tree import scan_project
from repomentor.cli import main
from repomentor.models.issue import Issue
from tests.conftest import EXAMPLES


def issue(rule_id: str) -> Issue:
    return Issue(rule_id=rule_id, title="", severity="low", category="quality", explanation="", recommendation="", effort_minutes=0)


def fixes_for(root, *rules: str, run_tools: bool = True):
    return build_fixes(scan_project(root), [issue(r) for r in rules], run_tools)


def apply(root, patch: str) -> None:
    subprocess.run(["git", "apply", "-"], cwd=root, input=patch.encode(), check=True, capture_output=True)


SOURCE = (
    "import os\nimport json\nimport yaml\n\n\n"
    "def load(path):\n    with open(path) as f:\n        return yaml.load(f)\n\n\n"
    "def trusted(path):\n    with open(path) as f:\n        return yaml.load(f, Loader=yaml.FullLoader)\n\n\n"
    "def safe(x):\n    try:\n        return int(x)\n    except:  # yorum kalır\n        return None\n\n\n"
    "def name():\n    şehir = 'İzmir';\n    return f'{şehir} şehri'\n\n\nTITLE = f'Rapor'\n"
)


def test_python_fixes(make_project):
    root = make_project({"app.py": SOURCE})
    report = fixes_for(root, "SEC012", "QLT007")
    fix = report.files[0]
    assert fix.path == "app.py" and fix.rules == ["QLT007", "RUFF-E703", "RUFF-F401", "RUFF-F541", "SEC012"]
    assert "-        return yaml.load(f)\n+        return yaml.safe_load(f)" in fix.diff
    assert "yaml.load(f, Loader=yaml.FullLoader)" not in fix.diff, "an explicit Loader is the user's decision"
    assert "+    except Exception:  # yorum kalır" in fix.diff
    assert "-import json" in fix.diff and "-import os" in fix.diff
    assert "+    şehir = 'İzmir'\n" in fix.diff and "+TITLE = 'Rapor'\n" in fix.diff, "non-ASCII lines keep their columns"
    assert "-    return f'{şehir} şehri'" not in fix.diff, "an f-string with a placeholder is left alone"


@pytest.mark.skipif(shutil.which("git") is None, reason="git yok")
def test_patch_applies_and_the_result_parses(make_project):
    root = make_project({"app.py": SOURCE.replace("\n", "\r\n"), "util.py": "x = 1"})   # CRLF, no trailing newline
    original = (root / "app.py").read_bytes()
    report = fixes_for(root, "SEC012", "QLT007", "SEC005")
    assert (root / "app.py").read_bytes() == original, "analysis never touches the project"
    apply(root, report.patch)
    fixed = (root / "app.py").read_bytes()
    assert b"yaml.safe_load(f)\r\n" in fixed and b"except Exception:" in fixed and b"\r\n" in fixed
    compile(fixed, "app.py", "exec")
    assert ".env" in (root / ".gitignore").read_text()


def test_nothing_is_fixed_without_a_matching_issue(make_project):
    root = make_project({"app.py": "import yaml\n\n\ndef f(p):\n    try:\n        return yaml.load(p)\n    except:\n        pass\n"})
    assert fixes_for(root, run_tools=False).files == []


def test_tests_and_init_files_keep_their_imports(make_project):
    root = make_project({
        "pkg/__init__.py": "from pkg.core import run\n",
        "pkg/core.py": "def run():\n    return 1\n",
        "tests/test_core.py": "from tests.fixtures import client\n\n\ndef test_run(client):\n    assert client\n",
    })
    assert fixes_for(root).files == []


def test_gitignore_is_extended(make_project):
    root = make_project({".gitignore": "__pycache__/", "app.py": "import os\nKEY = os.getenv('API_KEY')\n"})
    fix = fixes_for(root, "SEC006", run_tools=False).files[0]
    assert fix.path == ".gitignore" and not fix.new_file
    assert "-__pycache__/\n\\ No newline at end of file\n+__pycache__/\n" in fix.diff and "+.env\n" in fix.diff


def test_env_example_lists_names_never_values(make_project):
    root = make_project({
        "app.py": "import os\nfrom os import environ\nA = os.getenv('API_KEY', 'x')\nB = os.environ['DB_URL']\n"
                  "C = environ.get('DEBUG')\nD = os.getenv(name)\n",
        ".env": "SECRET_TOKEN=abc123\nexport REGION=eu\n# NOT_A_KEY=1\n",
    })
    assert environment_names(scan_project(root)) == ["API_KEY", "DB_URL", "DEBUG", "REGION", "SECRET_TOKEN"]
    fix = fixes_for(root, "DOC009", run_tools=False).files[0]
    assert fix.new_file and "+API_KEY=\n" in fix.diff and "abc123" not in fix.diff and "eu" not in fix.diff.split("+REGION=")[1][:3]


def test_unified_diff_for_new_and_changed_files():
    assert unified_diff("a.txt", None, "x\n").splitlines()[:3] == ["--- /dev/null", "+++ b/a.txt", "@@ -0,0 +1 @@"]
    assert unified_diff("a.txt", "x\n", "x\n") == ""


def test_problematic_example_and_cli(problematic_result, tmp_path, capsys):
    assert {"SEC012", "QLT007", "SEC005"} <= problematic_result.fixes.rules
    out = tmp_path / "fixes.patch"
    assert main([str(EXAMPLES / "problematic_project"), "--no-osv", "-o", str(tmp_path / "r.md"), "--fix-patch", str(out)]) == 0
    assert "+++ b/utils.py" in out.read_text(encoding="utf-8")
    assert "Düzeltme yaması yazıldı" in capsys.readouterr().err
