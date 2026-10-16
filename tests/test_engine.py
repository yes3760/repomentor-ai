"""RepoMentor's own algorithms: taint analysis, cognitive complexity, structural clones,
import graph and the debt / hotspot model."""

import ast
from pathlib import Path

import pytest

from repomentor.analyzer.code_metrics import annotation_counts, cognitive_complexity, find_clones
from repomentor.analyzer.file_tree import scan_project
from repomentor.analyzer.import_graph import analyze_imports, module_name, shortest_cycle, strongly_connected, to_dot
from repomentor.analyzer.insights import hotspots, technical_debt
from repomentor.analyzer.security_analyzer import analyze_security
from repomentor.analyzer.taint import find_taint_flows
from repomentor.models.analysis_result import QualityReport
from repomentor.models.issue import Issue, Location
from tests.conftest import EXAMPLES, analyze

ROOT = Path(__file__).resolve().parent.parent

WEB_APP = '''
import os, shlex, subprocess, pickle, requests
import streamlit as st
from flask import Flask, request, redirect, render_template_string, send_file
from helpers import run_backup, build_query

app = Flask(__name__)


@app.route("/user/<name>")
def user(name):
    return render_template_string("<h1>" + name + "</h1>")


@app.route("/backup")
def backup():
    target = request.form["target"]
    run_backup(target)


@app.route("/safe")
def safe():
    page = int(request.args.get("page", 1))
    os.system(f"echo {page}")
    q = shlex.quote(request.args.get("q", ""))
    subprocess.run(f"grep {q} log.txt", shell=True)
    requests.get(f"https://api.github.com/users/{request.args['u']}")
    return "ok"


@app.route("/proxy")
def proxy():
    url = request.args.get("url")
    requests.get(url)
    return redirect(request.args.get("next"))


@app.route("/reassign")
def reassign():
    name = request.args.get("n")
    name = "sabit"
    os.system("echo " + name)
    data = request.get_data()
    obj = pickle.loads(data)
    path = os.path.join("/srv/files", request.args.get("f"))
    return send_file(path)


@app.get("/items/{item_id}")
def item(item_id: int, q: str = ""):
    cur = None
    cur.execute(build_query(q))
    cur.execute("SELECT * FROM t WHERE id = ?", (item_id,))
    os.system(f"rm {item_id}")
    return {}


text = st.text_input("Mesaj")
st.markdown(f"<b>{text}</b>", unsafe_allow_html=True)
expr = input("İfade: ")
print(eval(expr))
'''
HELPERS = '''
import os


def run_backup(folder):
    command = "tar czf backup.tgz " + folder
    os.system(command)


def build_query(term):
    return f"SELECT * FROM items WHERE name LIKE '%{term}%'"
'''


@pytest.fixture
def web_flows(make_project):
    root = make_project({"web.py": WEB_APP, "helpers.py": HELPERS, ".gitignore": ".env\n"})
    flows, _ = find_taint_flows(scan_project(root))
    return root, {(f.kind, f.line): f for f in flows}


# --- Taint analysis ---------------------------------------------------------------------------------

def test_every_sink_kind_is_found_with_its_path(web_flows):
    _, flows = web_flows
    assert {kind for kind, _ in flows} == {"template", "command", "ssrf", "redirect", "deserialize", "path", "sql", "xss", "code"}
    assert flows[("template", 12)].source == "istek parametresi `name`", "route parameters are user input"
    assert flows[("path", 46)].path == ["path"], "os.path.join keeps the mark"
    assert flows[("deserialize", 44)].source == "request.get_data()"


def test_flows_through_helper_functions(web_flows):
    _, flows = web_flows
    backup = flows[("command", 18)]
    assert backup.via == "run_backup" and "helpers.py:7" in backup.sink, "a parameter that reaches os.system in another module"
    assert flows[("sql", 52)].path == ["q", "build_query()"], "a helper that returns its parameter propagates the mark"


def test_sanitisers_fixed_hosts_reassignment_and_validated_params_stop_flows(web_flows):
    _, flows = web_flows
    lines = {line for _, line in flows}
    assert not lines & set(range(23, 29)), "int(), shlex.quote() and a fixed-host URL are safe"
    assert ("command", 42) not in flows, "re-assigning a clean value clears the mark"
    assert ("command", 54) not in flows and ("sql", 53) not in flows, "typed FastAPI params and bound SQL parameters are safe"


def test_console_input_is_reported_as_local(web_flows):
    root, flows = web_flows
    assert flows[("code", 61)].remote is False
    _, issues = analyze_security(scan_project(root), "local", run_tools=False)
    local = next(i for i in issues if i.rule_id == "TNT001")
    assert local.severity == "high" and local.title.endswith("yerel girdi"), "one level below a remote code injection"


def test_confirmed_flows_replace_pattern_findings_on_the_same_line(problematic_result):
    flows = problematic_result.security.taint_flows
    assert sorted(f.kind for f in flows) == ["code", "command", "sql"]
    pattern_lines = {(loc.file, loc.line) for i in problematic_result.issues if i.rule_id.startswith("SEC01") for loc in i.locations}
    assert not pattern_lines & {(f.file, f.line) for f in flows}


def test_repomentor_itself_has_no_confirmed_flows():
    """Dogfooding: the analyser must not report its own Streamlit inputs as vulnerabilities."""
    flows, functions = find_taint_flows(scan_project(ROOT))
    assert functions > 300 and flows == []


# --- Cognitive complexity -------------------------------------------------------------------------------

def _cognitive(source: str) -> int:
    func = ast.parse(source).body[0]
    return cognitive_complexity(func, source.splitlines())


@pytest.mark.parametrize(("source", "expected"), [
    # SonarSource whitepaper "sumOfPrimes" (Java: for +1, for +2, if +3, continue OUTER +1) – for/else plays the label's role.
    ("def f(n):\n    total = 0\n    for i in range(n):\n        for j in range(2, i):\n            if i % j == 0:\n"
     "                break\n        else:\n            total += i\n    return total\n", 7),
    ("def f(x):\n    match x:\n        case 1:\n            return 'a'\n        case _:\n            return 'b'\n", 1),
    ("def f(x):\n    if x == 1:\n        return 1\n    elif x == 2:\n        return 2\n    else:\n        return 3\n", 3),
    ("def f(x, y):\n    if x:\n        pass\n    else:\n        if y:\n            pass\n", 4),
    ("def f(a, b, c):\n    if a and b or c:\n        return 1\n", 3),
    ("def f(a, b, c, d):\n    return a and b and c and d\n", 1),
    ("def fact(n):\n    return n * fact(n - 1) if n > 1 else 1\n", 2),
    ("def f(items):\n    try:\n        for x in items:\n            if x:\n                pass\n    except ValueError:\n        pass\n", 4),
    ("def f(items):\n    def inner(x):\n        if x:\n            return 1\n    return [inner(i) for i in items]\n", 2),
])
def test_cognitive_complexity_reference_cases(source, expected):
    assert _cognitive(source) == expected


def test_cognitive_complexity_flags_hard_to_read_functions(problematic_result):
    worst = problematic_result.quality.most_complex[0]
    assert worst.name == "not_hesapla" and worst.cognitive >= 30 and worst.cognitive > worst.complexity
    assert problematic_result.quality.very_hard_functions == 1


# --- Structural clones and type hints ---------------------------------------------------------------------

CLONE_A = '''def total_price(items, rate):
    result = 0
    for item in items:
        if item.price > 100:
            result += item.price * rate
        else:
            result += item.price
    return round(result, 2)
'''
CLONE_B = '''def sum_salaries(staff, bonus):
    acc = 0
    for person in staff:
        if person.price > 5000:
            acc += person.price * bonus
        else:
            acc += person.price
    return round(acc, 2)
'''
NOT_A_CLONE = CLONE_B.replace("round(acc, 2)", "len(acc)").replace("sum_salaries", "count_staff")


def test_renamed_copies_are_structural_clones(make_project):
    root = make_project({"a.py": CLONE_A, "b.py": CLONE_B, "c.py": NOT_A_CLONE})
    clones = find_clones(scan_project(root))
    assert len(clones) == 1 and [m.split(" ")[1] for m in clones[0].members] == ["total_price()", "sum_salaries()"]


def test_clones_already_found_as_text_duplicates_are_not_repeated(make_project):
    root = make_project({"a.py": CLONE_A, "b.py": CLONE_B})
    assert find_clones(scan_project(root), covered={"a.py": [(1, 9)], "b.py": [(1, 9)]}) == []


def test_type_hint_coverage(make_project):
    root = make_project({"m.py": "def a(x: int, y) -> int:\n    return x\n\ndef _private(z):\n    return z\n\nclass C:\n    def m(self, q: str):\n        pass\n"})
    assert annotation_counts(scan_project(root)) == (3, 5)


# --- Import graph -----------------------------------------------------------------------------------------

def test_module_names():
    assert module_name("src/shop/orders.py") == "shop.orders"
    assert module_name("shop/__init__.py") == "shop"
    assert module_name("main.py") == "main"


def test_tarjan_components_and_shortest_cycle():
    graph = {"a": ["b"], "b": ["c"], "c": ["a", "d"], "d": ["e"], "e": ["d"], "f": ["g"]}
    components = sorted(sorted(c) for c in strongly_connected(list("abcdefg"), graph))
    assert components == [["a", "b", "c"], ["d", "e"], ["f"], ["g"]]
    assert shortest_cycle(["a", "b", "c"], graph) == ["a", "b", "c", "a"]


def test_circular_imports_ignore_lazy_and_type_checking_imports(make_project):
    root = make_project({
        "shop/__init__.py": "from shop.orders import Order\n",
        "shop/orders.py": "from . import payments\n\nclass Order:\n    pass\n",
        "shop/payments.py": "from shop.users import User\n",
        "shop/users.py": "from .orders import Order\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from shop import payments\n\n"
                         "def late():\n    from shop import payments\n    return payments\n\nclass User:\n    pass\n",
        "main.py": "import shop.orders\nimport os\n",
    })
    graph = analyze_imports(scan_project(root))
    assert graph.cycles == [["shop.orders", "shop.payments", "shop.users", "shop.orders"]]
    lazy = [(e.source, e.target) for e in graph.edges if e.lazy]
    assert lazy == [("shop.users", "shop.payments")]
    dot = to_dot(graph)
    assert '"shop.orders" -> "shop.payments" [color="#d03b3b", penwidth=2]' in dot and "style=dashed" in dot

    result = analyze(root)
    assert any(i.rule_id == "ORG008" and "shop.orders → shop.payments" in i.title for i in result.issues)
    assert any(f.label.startswith("Döngüsel import") for f in result.score.category("organization").factors)


def test_coupling_metrics(clean_result):
    modules = {m.name: m for m in clean_result.imports.modules}
    assert modules["app.models"].fan_in == 2 and modules["app.models"].instability == 0.0
    assert modules["app.main"].fan_out == 3 and modules["app.main"].instability == 1.0
    assert clean_result.imports.cycles == []


# --- Technical debt and hotspots -----------------------------------------------------------------------------

def _issue(severity: str, minutes: int, file: str, source: str = "rule") -> Issue:
    return Issue(rule_id="X", title="x", severity=severity, category="quality", explanation="e", recommendation="r",
                 effort_minutes=minutes, locations=[Location(file)], source=source)


@pytest.mark.parametrize(("minutes", "sloc", "rating"), [(0, 100, "A"), (150, 100, "A"), (300, 100, "B"), (600, 100, "C"),
                                                          (1500, 100, "D"), (1501, 100, "E")])
def test_debt_rating_thresholds(minutes, sloc, rating):
    assert technical_debt([_issue("low", minutes, "a.py")], sloc).rating == rating


def test_ai_opinions_are_not_debt():
    debt = technical_debt([_issue("low", 30, "a.py"), _issue("high", 500, "a.py", source="ai")], 100)
    assert debt.minutes == 30


def test_hotspots_rank_findings_complexity_and_size():
    quality = QualityReport(per_file={
        "app.py": {"cognitive": 48, "functions": 6, "lines": 130},
        "config.py": {"cognitive": 0, "functions": 0, "lines": 4},
        "big_but_clean.py": {"cognitive": 3, "functions": 30, "lines": 900},
    })
    issues = [_issue("critical", 15, "app.py"), _issue("high", 10, "app.py"), _issue("high", 10, "config.py")]
    ranked = hotspots(quality, issues)
    assert [h.file for h in ranked] == ["app.py", "config.py"], "a clean file is never a hotspot just for its size"
    assert ranked[1].risk > 0, "any file with a finding ranks above zero"
    assert ranked[0].reasons == ["2 kritik/yüksek bulgu", "bilişsel yük 48"]


def test_report_and_json_include_engine_results(problematic_result):
    from repomentor.analyzer.report_builder import build_json, build_markdown

    markdown = build_markdown(problematic_result)
    assert "## Teknik Borç ve Öncelikli Dosyalar" in markdown and "## Modül Bağımlılıkları" in markdown
    assert "**Kod enjeksiyonu**: `request.args.get('ifade')`" in markdown
    data = build_json(problematic_result)
    for key in ('"taint_flows"', '"hotspots"', '"debt"', '"imports"', '"cognitive"', '"clones"'):
        assert key in data


def test_example_scores_still_rank_sensibly():
    scores = [analyze(EXAMPLES / name, check_dependencies=False).score.overall
              for name in ("clean_project", "medium_project", "problematic_project")]
    assert scores == sorted(scores, reverse=True) and scores[0] >= 90 and scores[2] < 40


def test_strengths_do_not_contradict_the_metrics(problematic_result, clean_result):
    """A low average must not hide one unreadable function (regression: not_hesapla, cognitive 41)."""
    assert not any("sade" in s or "kısa ve odaklı" in s for s in problematic_result.strengths)
    assert any("sade" in s for s in clean_result.strengths)


def test_src_layout_imports_resolve_with_and_without_prefix(medium_result, make_project):
    edges = {(e.source, e.target) for e in medium_result.imports.edges}
    assert {("app", "data"), ("app", "recommender"), ("recommender", "data")} <= edges, "`from src.data import …`"
    root = make_project({"src/pkg/__init__.py": "", "src/pkg/a.py": "from pkg.b import x\n", "src/pkg/b.py": "x = 1\n"})
    assert [(e.source, e.target) for e in analyze_imports(scan_project(root)).edges] == [("pkg.a", "pkg.b")]
