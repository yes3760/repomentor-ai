"""Dependency vulnerability scan. OSV.dev is never contacted: responses are faked
in the shape the real API returns (checked against api.osv.dev)."""

import pytest

from repomentor.analyzer import dependency_analyzer as dep
from repomentor.analyzer.file_tree import scan_project
from tests.conftest import EXAMPLES, analyze

PYYAML_CRITICAL = {
    "id": "GHSA-8q59-q68h-6hv4",
    "aliases": ["CVE-2020-14343", "PYSEC-2021-142"],
    "summary": "Improper Input Validation in PyYAML",
    "database_specific": {"severity": "CRITICAL"},
    "affected": [{"package": {"name": "pyyaml", "ecosystem": "PyPI"},
                  "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "5.4"}]}]}],
}
PYYAML_ALIAS = {"id": "PYSEC-2021-142", "aliases": ["CVE-2020-14343", "GHSA-8q59-q68h-6hv4"], "summary": "", "affected": []}
FLASK_HIGH = {
    "id": "GHSA-562c-5r94-xh97",
    "aliases": ["CVE-2018-1000656"],
    "summary": "Flask is vulnerable to Denial of Service via incorrect encoding of JSON data",
    "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H"}],
    "affected": [{"package": {"name": "Flask", "ecosystem": "PyPI"},
                  "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "0.12.3"}]}]}],
}
FLASK_LATER = {
    "id": "GHSA-m2qf-hxjv-5gpq",
    "summary": "Flask session cookie disclosure",
    "database_specific": {"severity": "HIGH"},
    "affected": [{"package": {"name": "flask", "ecosystem": "PyPI"}, "ranges": [{"type": "ECOSYSTEM", "events": [
        {"introduced": "0"}, {"fixed": "2.2.5"}, {"introduced": "2.3.0"}, {"fixed": "2.3.2"}]}]}],
}
FAKE_DB = {("pyyaml", "5.3"): [PYYAML_CRITICAL, PYYAML_ALIAS], ("flask", "0.12.2"): [FLASK_HIGH, FLASK_LATER]}


@pytest.fixture
def fake_osv(monkeypatch):
    calls = []

    def post(payload):
        calls.append(payload)
        return {"vulns": FAKE_DB.get((payload["package"]["name"], payload["version"]), [])}

    monkeypatch.setattr(dep, "_post_query", post)
    return calls


def test_collects_exact_pins_and_reports_ranges_separately(make_project):
    root = make_project({"requirements.txt": (
        "# web\nFlask==0.12.2  # pinned\nrequests[socks]==2.19.1 ; python_version >= '3.8'\n"
        "PyYAML===5.3 --hash=sha256:abc\nhttpx>=0.27,<1\npandas\n-r dev.txt\n"
        "git+https://github.com/x/y.git\nhttps://example.com/pkg.whl\n"
    )})
    pinned, loose, sources = dep.collect_dependencies(scan_project(root))
    assert {(d.name, d.version, d.line) for d in pinned} == {("flask", "0.12.2", 2), ("requests", "2.19.1", 3), ("pyyaml", "5.3", 4)}
    assert loose == ["httpx", "pandas"], "a package whose name starts with 'http' must not be skipped"
    assert sources == ["requirements.txt"]


def test_large_lock_files_are_read(make_project):
    """Real lock files often exceed the 200 KB source-file limit."""
    padding = "".join(f'[[package]]\nname = "pkg{n}"\nversion = "1.0.{n}"\ndescription = "{"x" * 200}"\n\n' for n in range(1200))
    root = make_project({"poetry.lock": padding + '[[package]]\nname = "Django"\nversion = "3.2.0"\n'})
    pinned, _, _ = dep.collect_dependencies(scan_project(root))
    assert ("django", "3.2.0") in {(d.name, d.version) for d in pinned}


def test_lock_files(make_project):
    root = make_project({
        "poetry.lock": '[[package]]\nname = "Django"\nversion = "3.2.0"\n\n[[package]]\nname = "idna"\nversion = "3.4"\n',
        "uv.lock": '[[package]]\nname = "myapp"\nversion = "0.1.0"\nsource = { editable = "." }\n\n'
                   '[[package]]\nname = "jinja2"\nversion = "2.4.1"\nsource = { registry = "https://pypi.org/simple" }\n',
        "Pipfile.lock": '{"default": {"urllib3": {"version": "==1.26.0"}}, "develop": {"pytest": {"version": "==7.0.0"}}}',
        "pyproject.toml": '[project]\nname = "x"\ndependencies = ["rich==13.0.0", "click>=8"]\n',
    })
    pinned, loose, _ = dep.collect_dependencies(scan_project(root))
    names = {(d.name, d.version) for d in pinned}
    assert names == {("django", "3.2.0"), ("idna", "3.4"), ("jinja2", "2.4.1"), ("urllib3", "1.26.0"), ("pytest", "7.0.0"), ("rich", "13.0.0")}
    assert "myapp" not in {d.name for d in pinned}, "the local project itself is never sent to OSV"
    assert loose == ["click"]


@pytest.mark.parametrize(("vector", "score"), [
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8),
    ("CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:N/A:N", 8.6),   # CVE-2019-10906 (NVD)
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H", 7.5),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", 6.1),   # reflected XSS reference vector
    ("CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H", 8.8),
    ("CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N", 1.8),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0.0),
])
def test_cvss3_base_score(vector, score):
    assert dep.cvss3_base_score(vector) == score


def test_severity_and_fixed_version():
    assert dep.severity_of(PYYAML_CRITICAL) == "critical"
    assert dep.severity_of(FLASK_HIGH) == "high", "falls back to the CVSS v3 score (7.5)"
    assert dep.severity_of({"id": "X"}) == "medium"
    assert dep.fixed_version(FLASK_LATER, "flask", "2.3.1") == "2.3.2", "picks the fix for the range the version is in"
    assert dep.fixed_version(FLASK_LATER, "flask", "2.2.9") is None


def test_scan_builds_one_issue_per_package(make_project, fake_osv):
    root = make_project({"requirements.txt": "Flask==0.12.2\nPyYAML==5.3\nclick==8.1.7\npandas\n"})
    report, issues = dep.analyze_dependencies(scan_project(root))
    assert report.ran and report.checked == 3 and report.unpinned == ["pandas"]
    assert {p["package"]["name"] for p in fake_osv} == {"flask", "pyyaml", "click"}, "only names and versions are sent"
    assert all(set(p) == {"package", "version"} for p in fake_osv)

    pyyaml, flask = report.vulnerable
    assert (pyyaml.name, pyyaml.severity, len(pyyaml.vulnerabilities), pyyaml.fixed_version) == ("pyyaml", "critical", 1, "5.4")
    assert (flask.severity, flask.fixed_version) == ("high", "2.2.5")
    assert pyyaml.vulnerabilities[0].cve == "CVE-2020-14343"
    assert pyyaml.vulnerabilities[0].url == "https://osv.dev/vulnerability/GHSA-8q59-q68h-6hv4"

    by_id = {i.rule_id: i for i in issues}
    assert set(by_id) == {"DEP-pyyaml", "DEP-flask"}
    assert by_id["DEP-pyyaml"].severity == "critical" and by_id["DEP-pyyaml"].source == "osv"
    assert by_id["DEP-pyyaml"].locations[0].line == 2
    assert "pyyaml>=5.4" in by_id["DEP-pyyaml"].recommendation
    assert "büyük sürüm atlaması" in by_id["DEP-flask"].recommendation, "0.12 → 2.2 needs a changelog warning"
    assert by_id["DEP-flask"].effort_minutes > by_id["DEP-pyyaml"].effort_minutes


def test_disabled_scan_never_calls_osv(make_project, fake_osv):
    root = make_project({"requirements.txt": "Flask==0.12.2\n"})
    report, issues = dep.analyze_dependencies(scan_project(root), enabled=False)
    assert fake_osv == [] and issues == [] and not report.ran
    assert "Kapalı" in dep.coverage_text(report)


def test_network_failure_is_reported_not_raised(make_project, monkeypatch):
    def offline(payload):
        raise dep.requests.ConnectionError("offline")

    monkeypatch.setattr(dep, "_post_query", offline)
    root = make_project({"requirements.txt": "Flask==0.12.2\n"})
    report, issues = dep.analyze_dependencies(scan_project(root))
    assert issues == [] and not report.ran and "bağlanılamadı" in report.error


def test_results_are_cached_per_version(make_project, fake_osv):
    root = make_project({"requirements.txt": "Flask==0.12.2\n"})
    dep.analyze_dependencies(scan_project(root))
    dep.analyze_dependencies(scan_project(root))
    assert len(fake_osv) == 1


def test_vulnerable_dependencies_lower_the_security_score(fake_osv):
    with_scan = analyze(EXAMPLES / "medium_project")
    root_reqs = (EXAMPLES / "problematic_project" / "requirements.txt").read_text()
    assert "PyYAML==5.3" in root_reqs
    problematic = analyze(EXAMPLES / "problematic_project")
    without = analyze(EXAMPLES / "problematic_project", check_dependencies=False)
    assert any(i.rule_id == "DEP-pyyaml" for i in problematic.issues)
    assert not any(i.source == "osv" for i in without.issues)
    assert not with_scan.dependencies.vulnerable
    assert "DEP-pyyaml" in {step.rule_id for phase in problematic.roadmap for step in phase.steps}


def test_report_lists_vulnerable_packages(fake_osv):
    from repomentor.analyzer.report_builder import build_json, build_markdown

    result = analyze(EXAMPLES / "problematic_project")
    markdown = build_markdown(result)
    assert "| `pyyaml` | 5.3 | 1 | Kritik | 5.4 |" in markdown
    assert "[GHSA-8q59-q68h-6hv4](https://osv.dev/vulnerability/GHSA-8q59-q68h-6hv4)" in markdown
    assert '"vulnerability_count": 3' in build_json(result)   # pyyaml 1 (aliases merged) + flask 2
