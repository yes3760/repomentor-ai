"""Jupyter notebooks: code cells become one virtual script, findings point back at cells."""

import json

import pytest

from repomentor.analyzer.autofix import build_fixes
from repomentor.analyzer.file_tree import scan_project
from repomentor.analyzer.notebooks import NotebookMap, cell_code, notebook_source
from repomentor.models.issue import Issue
from tests.conftest import EXAMPLES, analyze


def notebook(*cells, language="python") -> str:
    """cells: ("md", text) or ("code", text)."""
    return json.dumps({
        "cells": [{"cell_type": "markdown" if kind == "md" else "code", "metadata": {}, "source": text,
                   **({"outputs": [], "execution_count": None} if kind == "code" else {})} for kind, text in cells],
        "metadata": {"kernelspec": {"language": language, "name": language}},
        "nbformat": 4, "nbformat_minor": 5,
    })


@pytest.mark.parametrize(("source", "expected"), [
    ("%matplotlib inline\nx = 1", "pass\nx = 1"),
    ("!pip install pandas", "pass"),
    ("files = !ls\nprint(files)", "files = None\nprint(files)"),
    ("df?", "pass"),
    ("if True:\n    %time f()", "if True:\n    pass"),
    ("%%time\ny = 2", "\ny = 2"),                      # a Python cell magic keeps its body
])
def test_ipython_syntax_is_neutralised_line_for_line(source, expected):
    assert cell_code(source) == expected


def test_cells_in_another_language_are_left_out():
    assert cell_code("%%bash\nls -la") is None
    assert cell_code("%%sql\nSELECT 1") is None


def test_virtual_script_and_cell_map():
    raw = notebook(("md", "# Başlık"), ("code", "import os"), ("code", "print(\n"), ("md", "not"), ("code", "x = 1\ny = 2"))
    text, mapping = notebook_source(raw)
    assert text == "# %% [hücre 2]\nimport os\n# %% [hücre 3]\n# %% [hücre 5]\nx = 1\ny = 2\n"
    assert mapping.cells == [2, 3, 5] and mapping.skipped == [3], "a cell that does not parse is emptied, not fatal"
    assert mapping.locate(6) == (5, 2) and mapping.label("nb.ipynb", 2) == "nb.ipynb › hücre 2:1"


def test_other_kernels_old_formats_and_broken_json():
    assert notebook_source(notebook(("code", "x <- 1"), language="R")) is None
    assert notebook_source("{not json") is None
    old = json.dumps({"worksheets": [{"cells": [{"cell_type": "code", "input": ["x = 1"]}]}], "nbformat": 3})
    assert notebook_source(old)[0] == "# %% [hücre 1]\nx = 1\n"


def test_locate_before_the_first_cell():
    assert NotebookMap(starts=[3], cells=[2]).locate(1) == (2, 1)


def test_notebooks_are_read_as_python_but_never_given_to_external_tools(make_project):
    root = make_project({
        "analysis.ipynb": notebook(("code", "import yaml\ntry:\n    yaml.load(open('c.yml'))\nexcept:\n    pass")),
        "lab.ipynb": notebook(("code", "x <- 1"), language="R"),
    })
    project = scan_project(root)
    assert project.python_files == ["analysis.ipynb"] and project.python_modules == []
    assert next(f for f in project.files if f.path == "lab.ipynb").skipped_reason
    issues = [Issue(rule_id=r, title="", severity="low", category="quality", explanation="", recommendation="", effort_minutes=0)
              for r in ("SEC012", "QLT007")]
    assert build_fixes(project, issues).files == [], "a JSON notebook is never patched as Python"


def test_cross_cell_flows_point_at_cells(make_project):
    root = make_project({"nb.ipynb": notebook(
        ("code", "import os"),
        ("code", "name = input('Ad: ')"),
        ("md", "## Komut"),
        ("code", "os.system('echo ' + name)"),
    )})
    result = analyze(root, check_dependencies=False)
    flow = result.security.taint_flows[0]
    assert (flow.file, flow.line, flow.source_line) == ("nb.ipynb › hücre 4", 1, 1)
    assert flow.source.endswith("(hücre 2)"), "the source lives in another cell"
    issue = next(i for i in result.issues if i.rule_id == "TNT002")
    assert str(issue.locations[0]) == "nb.ipynb › hücre 4:1"


def test_notebook_example():
    result = analyze(EXAMPLES / "notebook_project", check_dependencies=False)
    found = {i.rule_id: [str(loc) for loc in i.locations] for i in result.issues}
    assert found["LEAK001"] == ["churn_eda.ipynb › hücre 7:4"], "scaler fitted in cell 7, data split in cell 9"
    assert found["PD001"] == ["churn_eda.ipynb › hücre 6:1"]
    assert found["SEC002"] == ["churn_eda.ipynb › hücre 4:1"]
    assert found["DEAD001"] == ["churn_eda.ipynb › hücre 10:1"]
    assert "ORG007" in found and "ORG003" not in found, "a notebook is its own entry point"
    leak = next(i for i in result.issues if i.rule_id == "LEAK001")
    assert "(churn_eda.ipynb › hücre 9:2)" in leak.explanation
    assert any("hücre 11" in w for w in result.warnings), "the %%bash cell is reported as skipped"
    assert result.project.primary_language == "Jupyter Notebook" and "scikit-learn" in result.project.ml_libraries
