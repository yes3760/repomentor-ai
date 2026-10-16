from repomentor.analyzer.file_tree import is_user_ignored, scan_project
from repomentor.analyzer.project_detector import detect_project
from repomentor.analyzer.quality_analyzer import analyze_quality, find_duplicates
from repomentor.analyzer.test_analyzer import analyze_tests
from tests.conftest import analyze


def test_complex_function_is_reported(problematic_result):
    titles = [i.title for i in problematic_result.issues if i.rule_id == "QLT001"]
    assert any("not_hesapla" in t for t in titles)


def test_duplicates_and_bare_excepts(problematic_result):
    q = problematic_result.quality
    assert q.duplicates, "copy-pasted report functions should be detected"
    assert q.bare_excepts == 2
    assert q.ruff_ran and q.ruff_total > 0


def test_syntax_errors_are_reported(make_project):
    root = make_project({"ok.py": "x = 1\n", "py2.py": "print 'hello'\n"})
    report, issues = analyze_quality(scan_project(root), run_tools=False)
    assert len(report.syntax_errors) == 1
    assert any(i.rule_id == "QLT006" for i in issues)


def test_duplicate_detector_ignores_unique_code(make_project):
    root = make_project({
        "a.py": "\n".join(f"value_{n} = compute({n}) + offset" for n in range(20)),
        "b.py": "\n".join(f"other_{n} = transform({n}) * scale" for n in range(20)),
    })
    assert find_duplicates(scan_project(root)) == []


def test_module_named_like_a_test_is_not_a_test(make_project):
    """Regression: `test_analyzer.py` holding source code is not a test file."""
    root = make_project({
        "pkg/test_analyzer.py": "def analyze():\n    return 1\n",
        "tests/test_real.py": "def test_one():\n    assert True\n",
    })
    project = scan_project(root)
    info = detect_project(project, "x", "local", None, None)
    report, _ = analyze_tests(project, info)
    assert report.test_files == ["tests/test_real.py"]
    assert report.test_functions == 1
    assert "pkg/test_analyzer.py" in project.source_python_files


def test_project_detection(clean_result, medium_result, problematic_result):
    assert clean_result.project.project_type == "Python web API'si"
    assert "FastAPI" in clean_result.project.frameworks
    assert clean_result.project.python_version == ">=3.11"
    assert clean_result.project.has_docker and clean_result.project.has_ci
    assert "Streamlit" in medium_result.project.frameworks
    assert "scikit-learn" in medium_result.project.ml_libraries
    assert "Flask" in problematic_result.project.frameworks
    assert "SQLite" in problematic_result.project.databases


def test_readme_checks(clean_result, problematic_result):
    assert all(clean_result.documentation.checks.values())
    assert not problematic_result.documentation.checks["has_installation"]


def test_test_analysis(clean_result, problematic_result):
    assert clean_result.tests.test_functions == 10
    assert clean_result.tests.ci_runs_tests
    assert clean_result.tests.status == "İyi"
    assert problematic_result.tests.status == "Yok"


def test_repomentorignore(make_project):
    root = make_project({
        "app.py": "x = 1\n",
        "examples/bad/app.py": "eval(input())\n",
        "notes.tmp": "x",
        ".repomentorignore": "# demo projects\nexamples/\n*.tmp\n",
    })
    project = scan_project(root)
    assert set(project.paths) == {"app.py", ".repomentorignore"}
    assert any("repomentorignore" in w for w in project.warnings)
    assert is_user_ignored("examples/x/y.py", ["examples/"])
    assert not is_user_ignored("src/examples.py", ["examples/"])


def test_ignored_folders_are_skipped(make_project):
    root = make_project({"app.py": "x = 1\n", ".venv/lib/site.py": "x", "node_modules/a.js": "x", "__pycache__/a.pyc": "x"})
    assert scan_project(root).paths == ["app.py"]


def test_non_python_project_gets_warning(make_project):
    root = make_project({"package.json": "{}", "index.js": "console.log(1)\n" * 30, "README.md": "# x"})
    result = analyze(root)
    assert result.project.project_type == "Node.js / JavaScript projesi"
    assert any("JavaScript" in w for w in result.warnings)


def test_methods_are_counted_once(make_project):
    """Regression: radon reports methods twice (inside the class and top-level)."""
    root = make_project({"svc.py": "class A:\n    def run(self, x):\n        if x:\n            return 1\n        return 2\n\n    def stop(self):\n        return 0\n"})
    report, _ = analyze_quality(scan_project(root), run_tools=False)
    assert report.functions == 2
    assert sorted(f.name for f in report.most_complex) == ["A.run", "A.stop"]
