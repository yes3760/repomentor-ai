import csv
import io
from copy import deepcopy

from repomentor.analyzer.comparison import compare_reports, project_identity
from repomentor.analyzer.finding_query import filter_findings, findings_csv
from repomentor.models.issue import Issue, Location


def finding(rule="SEC001", file="app.py", line=5, title="Risk", minutes=15):
    return Issue(rule, title, "high", "security", "Riskli çağrı", "Parametre kullan", minutes,
                 locations=[Location(file, line)])


def test_line_shifts_and_count_titles_do_not_create_new_issues(clean_result):
    previous, current = deepcopy(clean_result), deepcopy(clean_result)
    previous.issues = [finding(title="3 yerde risk")]
    current.issues = [finding(line=105, title="2 yerde risk")]
    diff = compare_reports(previous, current)
    assert diff.added == diff.resolved == []
    assert diff.unchanged == 1
    assert diff.score_delta == 0


def test_comparison_counts_duplicate_rule_file_pairs(clean_result):
    previous, current = deepcopy(clean_result), deepcopy(clean_result)
    previous.issues = [finding(line=5), finding(line=10)]
    current.issues = [finding(line=20), finding(rule="SEC002")]
    diff = compare_reports(previous, current)
    assert [i.rule_id for i in diff.added] == ["SEC002"]
    assert len(diff.resolved) == 1
    assert diff.unchanged == 1


def test_rule_in_new_file_is_a_new_finding(clean_result):
    previous, current = deepcopy(clean_result), deepcopy(clean_result)
    previous.issues = [finding()]
    current.issues = [finding(file="other.py")]
    diff = compare_reports(previous, current)
    assert len(diff.added) == len(diff.resolved) == 1


def test_comparison_reports_category_deltas(clean_result, problematic_result):
    diff = compare_reports(problematic_result, clean_result)
    assert diff.score_delta > 0
    assert not diff.same_project
    security = next(c for c in diff.categories if c["Kategori"] == "Güvenlik")
    assert security["Fark"] > 0
    assert diff.resolved


def test_github_identity_does_not_confuse_same_repo_name_from_two_owners(clean_result):
    left, right = deepcopy(clean_result), deepcopy(clean_result)
    left.project.source_url = "https://github.com/alice/project"
    right.project.source_url = "https://github.com/bob/project"
    assert project_identity(left) != project_identity(right)
    left.project.source_url = "https://github.com/ALICE/project.git/"
    right.project.source_url = "https://github.com/alice/project"
    assert project_identity(left) == project_identity(right)


def test_github_scope_keeps_case_sensitive_branch_names(clean_result):
    left, right = deepcopy(clean_result), deepcopy(clean_result)
    left.project.source_url = "https://github.com/alice/project/tree/Release/src"
    right.project.source_url = "https://github.com/alice/project/tree/release/src"
    assert project_identity(left) != project_identity(right)


def test_search_combines_terms_across_rule_and_file():
    issues = [finding(), finding(file="service.py"), finding(rule="SEC002")]
    assert filter_findings(issues, "sec001 APP.PY") == [issues[0]]
    assert filter_findings(issues, "parametre") == issues
    assert not filter_findings(issues, "eşleşmeyen")


def test_filter_empty_selection_is_distinct_from_no_filter():
    issues = [finding()]
    assert filter_findings(issues) == issues
    assert filter_findings(issues, severities=[]) == []
    assert filter_findings(issues, categories=["quality"]) == []


def test_sort_quick_wins_and_file():
    slow, fast = finding(file="a.py", minutes=60), finding(file="z.py", minutes=5)
    assert filter_findings([slow, fast], sort="effort") == [fast, slow]
    assert filter_findings([fast, slow], sort="file") == [slow, fast]


def test_csv_preserves_turkish_multiline_fields_and_neutralizes_formulas():
    issue = finding(title='=HYPERLINK("https://example.com")', file="+dosya.py")
    issue.explanation = "İlk satır, Türkçe\nİkinci satır"
    rows = list(csv.reader(io.StringIO(findings_csv([issue]).removeprefix("\ufeff"))))
    assert rows[1][3].startswith("'=")
    assert rows[1][4].startswith("'+")
    assert rows[1][5] == issue.explanation
    assert len(rows) == 2
