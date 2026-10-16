"""Call graph: dead code without false alarms, and what the tests can reach."""

from repomentor.analyzer.call_graph import build_call_graph
from repomentor.analyzer.file_tree import scan_project
from repomentor.analyzer.usage_analyzer import analyze_usage, find_unused
from repomentor.cli import main
from tests.conftest import EXAMPLES, ROOT


def unused_names(root, library=False):
    return {u.name for u in find_unused(build_call_graph(scan_project(root)), library)}


def test_unused_functions_and_classes(make_project):
    root = make_project({"app.py": (
        "def used():\n    return 1\n\n"
        "def never_called():\n    return 2\n\n"
        "class Ghost:\n    def method(self):\n        return 3\n\n"
        "print(used())\n"
    )})
    assert unused_names(root) == {"never_called", "Ghost"}, "a dead class is reported once, not per method"


def test_references_that_are_not_calls_keep_code_alive(make_project):
    root = make_project({
        "views.py": (
            "def render_a():\n    pass\n\ndef render_b():\n    pass\n\n"
            "TABS = (('A', render_a), ('B', render_b))\n\n"
            "def on_save():\n    pass\n\n"
            "def draw(button):\n    button('Kaydet', on_click=on_save)\n"
        ),
        "app.py": "from views import TABS, draw\nfor _, render in TABS:\n    render()\ndraw(print)\n",
        "unused_import.py": "from views import draw\n",
    })
    assert unused_names(root) == set(), "tables and callbacks are references; importing alone is not"


def test_dynamic_dispatch_inheritance_and_framework_callbacks(make_project):
    root = make_project({
        "engine.py": (
            "import ast\n\n"
            "class Visitor:\n"
            "    def visit(self, node):\n        return getattr(self, f'_v_{type(node).__name__}')(node)\n"
            "    def _v_Name(self, node):\n        return node.id\n"
            "    def _v_Call(self, node):\n        return node\n"
            "    _v_Await = _v_Call\n\n"
            "class Base:\n    def hook(self):\n        return 0\n    def run(self):\n        return self.hook()\n\n"
            "class Child(Base):\n    def hook(self):\n        return super().hook() + 1\n\n"
            "class Renamer(ast.NodeTransformer):\n    def visit_Name(self, node):\n        return node\n\n"
            "Visitor().visit(None)\nChild().run()\nRenamer()\n"
        ),
    })
    assert unused_names(root) == set()


def test_entry_points(make_project):
    root = make_project({
        "web.py": "from flask import Flask\napp = Flask(__name__)\n\n@app.route('/')\ndef index():\n    return 'ok'\n",
        "pkg/__init__.py": "from pkg.core import exported\n__all__ = ['listed']\n\ndef listed():\n    pass\n",
        "pkg/core.py": "def exported():\n    pass\n\ndef _helper():\n    pass\n",
        "tool.py": "def main():\n    pass\n",
        "pyproject.toml": '[project]\nname = "x"\n\n[project.scripts]\ntool = "tool:main"\n',
        "client.py": "import pkg\npkg.exported()\n",
    })
    assert unused_names(root) == {"_helper"}, "routes, __all__, re-exports and console scripts are entry points"


def test_library_mode_reports_only_private_names(make_project):
    root = make_project({"lib/api.py": "def public_api():\n    pass\n\ndef _internal():\n    pass\n"})
    assert unused_names(root, library=True) == {"_internal"}
    assert unused_names(root) == {"public_api", "_internal"}


def test_problematic_example_dead_functions(problematic_result):
    names = {u.name for u in problematic_result.usage.unused}
    assert {"not_hesapla", "hava_durumu", "yukle", "ayar_oku"} <= names
    assert not {"hesapla", "ogrenci_bul", "yedek"} & names, "Flask routes are registered by their decorator"
    assert any(i.rule_id == "DEAD001" for i in problematic_result.issues)


def test_static_test_reach(make_project):
    root = make_project({
        "calc/__init__.py": "from calc.ops import add\n",
        "calc/ops.py": "def add(a, b):\n    return _check(a) + b\n\ndef _check(x):\n    return x\n\ndef sub(a, b):\n    return a - b\n",
        "tests/test_ops.py": "from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    })
    report, issues = analyze_usage(scan_project(root))
    assert (report.test_reached, report.test_total) == (2, 3), "add and its helper are reached through the re-export"
    assert [u.name for u in report.untested] == ["sub"]
    assert any(i.rule_id == "TST005" and "%67" in i.title for i in issues)


def test_scripts_and_http_clients_count_as_test_reach(make_project):
    root = make_project({
        "app.py": "import streamlit as st\n\ndef page():\n    st.write('x')\n\npage()\n",
        "api.py": "from fastapi import FastAPI\napi = FastAPI()\n\n@api.get('/items')\ndef items():\n    return []\n",
        "tests/test_app.py": (
            "from streamlit.testing.v1 import AppTest\nfrom fastapi.testclient import TestClient\nfrom api import api\n\n"
            "def test_app():\n    AppTest.from_file(\"app.py\").run()\n\n"
            "def test_api():\n    assert TestClient(api).get('/items').json() == []\n"
        ),
    })
    report, _ = analyze_usage(scan_project(root))
    assert report.untested == [] and report.test_total == 2


def test_clean_example_routes_are_honestly_untested(clean_result):
    untested = {u.name for u in clean_result.usage.untested}
    assert {"get_tasks", "post_task"} <= untested, "its tests call the repository directly, never the HTTP routes"
    assert 0.4 < clean_result.usage.test_reach < 0.8


def test_repomentor_has_no_dead_code():
    """Dogfooding: every function in RepoMentor is reachable from an entry point."""
    report, _ = analyze_usage(scan_project(ROOT))
    assert report.unused == [], [u.name for u in report.unused]
    assert report.test_reach > 0.95


def test_cli_writes_report_and_enforces_min_score(tmp_path):
    output = tmp_path / "rapor.md"
    assert main([str(EXAMPLES / "clean_project"), "--no-osv", "-o", str(output)]) == 0
    assert output.read_text(encoding="utf-8").startswith("# RepoMentor AI Analiz Raporu")
    assert main([str(EXAMPLES / "problematic_project"), "--no-osv", "--format", "json", "-o", str(tmp_path / "r.json"), "--min-score", "80"]) == 1
    assert main([str(tmp_path / "olmayan-klasor"), "--no-osv"]) == 2
