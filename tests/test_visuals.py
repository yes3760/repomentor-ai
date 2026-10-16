"""Code map, attack-path diagrams and the README badge."""

import pytest

from repomentor.analyzer.badge import badge_markdown, badge_svg
from repomentor.analyzer.code_map import code_map_spec, heat_color
from repomentor.models.analysis_result import TaintFlow
from repomentor.ui.visual_views import flow_dot
from tests.conftest import EXAMPLES, analyze


def leaves(nodes):
    for node in nodes:
        if "children" in node:
            yield from leaves(node["children"])
        else:
            yield node


@pytest.mark.parametrize(("value", "color"), [(0, "#3fa678"), (50, "#e0a83b"), (100, "#d64550"), (-5, "#3fa678"), (140, "#d64550")])
def test_heat_scale(value, color):
    assert heat_color(value) == color


def test_code_map_nests_folders_and_colours_by_risk():
    result = analyze(EXAMPLES / "clean_project", check_dependencies=False, run_tools=False)
    data = code_map_spec(result)["series"][0]["data"]
    app = next(n for n in data if n["name"] == "app")
    assert app["value"] == sum(child["value"] for child in app["children"]), "a folder is as big as its files"
    files = {leaf["path"]: leaf for leaf in leaves(data)}
    assert set(files) == set(result.quality.per_file)
    for leaf in files.values():
        assert leaf["itemStyle"]["color"] == heat_color(leaf["heat"]) and "satır" in leaf["tooltip"]["formatter"]


def test_colour_modes_change_the_measure():
    result = analyze(EXAMPLES / "problematic_project", check_dependencies=False, run_tools=False)
    by_mode = {mode: {leaf["path"]: leaf["heat"] for leaf in leaves(code_map_spec(result, mode)["series"][0]["data"])}
               for mode in ("risk", "cognitive", "issues")}
    assert by_mode["risk"]["app.py"] == 100 and by_mode["cognitive"]["config.py"] == 0


def test_repository_text_is_escaped_in_tooltips(make_project):
    root = make_project({"pkg/<img src=x onerror=alert(1)>.py": "def f():\n    return 1\n", "main.py": "print(1)\n"})
    spec = code_map_spec(analyze(root, check_dependencies=False, run_tools=False))
    tooltips = " ".join(leaf["tooltip"]["formatter"] for leaf in leaves(spec["series"][0]["data"]))
    assert "<img" not in tooltips and "&lt;img" in tooltips


def test_notebook_findings_land_on_the_notebook():
    result = analyze(EXAMPLES / "notebook_project", check_dependencies=False, run_tools=False)
    leaf = next(leaves(code_map_spec(result)["series"][0]["data"]))
    assert leaf["path"] == "churn_eda.ipynb" and "LEAK" not in leaf["tooltip"]["formatter"] and "bulgu" in leaf["tooltip"]["formatter"]
    assert leaf["heat"] > 0


def test_flow_diagram_chains_source_hops_and_sink():
    flow = TaintFlow(kind="sql", file="app.py", line=28, sink='cur.execute(f"SELECT \\"x\\" {q}")', source="request.args.get('q')",
                     source_line=25, path=["q", "build_query()"], function="search", remote=True)
    dot = flow_dot(flow)
    assert "src -> h0 -> h1 -> sink;" in dot and "Kullanıcı girdisi" in dot and "SQL enjeksiyonu" in dot
    assert '\\"' in dot and 'SELECT \\\\\\"x' in dot, "quotes and backslashes in code are escaped for Graphviz"


@pytest.mark.parametrize(("score", "color"), [(96, "brightgreen"), (80, "green"), (65, "yellow"), (23, "orange")])
def test_badge(score, color):
    markdown = badge_markdown(score)
    assert f"RepoMentor_AI-{score}%2F100-{color}" in markdown and markdown.endswith("(https://github.com/yes3760/repomentor-ai)")
    svg = badge_svg(score)
    assert svg.startswith("<svg") and f"{score}/100" in svg and svg.endswith("</svg>")
