from pathlib import Path

import pytest

from repomentor.analyzer import dependency_analyzer
from repomentor.analyzer.pipeline import analyze_project
from repomentor.analyzer.repository_loader import load_local

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


@pytest.fixture(scope="session", autouse=True)
def no_osv_network():
    """The suite never reaches OSV.dev; tests that need advisories install their own fake."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(dependency_analyzer, "_post_query", lambda payload: {"vulns": []})
        yield


@pytest.fixture(autouse=True)
def fresh_osv_cache():
    dependency_analyzer._CACHE.clear()
    yield
    dependency_analyzer._CACHE.clear()


def analyze(path: Path, **kwargs):
    with load_local(path) as loaded:
        return analyze_project(loaded, **kwargs)


@pytest.fixture(scope="session")
def clean_result():
    return analyze(EXAMPLES / "clean_project")


@pytest.fixture(scope="session")
def medium_result():
    return analyze(EXAMPLES / "medium_project")


@pytest.fixture(scope="session")
def problematic_result():
    return analyze(EXAMPLES / "problematic_project")


@pytest.fixture
def make_project(tmp_path):
    """Write {relative_path: content} into a temp folder and return its path."""

    def _make(files: dict[str, str]) -> Path:
        for rel, content in files.items():
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return tmp_path

    return _make
