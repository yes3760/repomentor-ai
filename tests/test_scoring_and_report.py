import csv
import io
import json
from copy import deepcopy

from repomentor.analyzer.readme_template import build_readme
from repomentor.analyzer.report_builder import build_csv, build_json, build_markdown
from repomentor.analyzer.roadmap import build_roadmap, first_sentence
from repomentor.models.issue import Issue, format_effort
from repomentor.utils.constants import SCORE_WEIGHTS


def test_weights_sum_to_one():
    assert abs(sum(SCORE_WEIGHTS.values()) - 1) < 1e-9


def test_scores_rank_projects_sensibly(clean_result, medium_result, problematic_result):
    assert clean_result.score.overall >= 90
    assert problematic_result.score.overall < 50
    assert clean_result.score.overall > medium_result.score.overall > problematic_result.score.overall


def test_every_category_is_bounded_and_explained(problematic_result):
    for category in problematic_result.score.categories:
        assert 0 <= category.score <= 100
        assert category.factors, f"{category.key} needs at least one explanation"


def test_issues_are_sorted_by_priority(problematic_result):
    keys = [i.sort_key for i in problematic_result.issues]
    assert keys == sorted(keys)
    assert problematic_result.issues[0].severity == "critical"


def _issue(severity, minutes, title="x"):
    return Issue(rule_id="T", title=title, severity=severity, category="quality", explanation="e", recommendation="Do it. Then more.", effort_minutes=minutes)


def test_roadmap_respects_time_boxes():
    phases = build_roadmap([_issue("high", 20), _issue("medium", 25), _issue("low", 60), _issue("low", 300), _issue("low", 500)])
    by_key = {p.key: p for p in phases}
    assert sum(s.effort_minutes for s in by_key["first_30m"].steps) <= 30
    assert sum(s.effort_minutes for s in by_key["first_2h"].steps) <= 90
    assert by_key["later"].steps[0].effort_minutes == 500


def test_critical_always_comes_first():
    phases = build_roadmap([_issue("low", 5), _issue("critical", 45)])
    assert phases[0].steps[0].severity == "critical"


def test_first_sentence_keeps_abbreviations():
    assert first_sentence("Dosyaları ayırın (örn. `app/`). Sonra test edin.") == "Dosyaları ayırın (örn. `app/`)"


def test_effort_labels():
    assert format_effort(10) == "10 dakika"
    assert format_effort(90) == "1,5 saat"
    assert format_effort(600) == "1,2 gün"


def test_markdown_report_sections(problematic_result):
    markdown = build_markdown(problematic_result)
    for heading in ["## Genel Skor", "## Bulgular", "## Kod Kalitesi", "## Güvenlik", "## Öncelikli Yol Haritası", "## CV ve LinkedIn"]:
        assert heading in markdown
    assert "profesyonel bir güvenlik denetiminin" in markdown


def test_json_report_round_trips(clean_result):
    data = json.loads(build_json(clean_result))
    assert data["score"]["overall"] == clean_result.score.overall
    assert data["issues"] == [] or "effort_label" in data["issues"][0]


def _csv_rows(result):
    report = build_csv(result)
    assert report.startswith("\ufeff")
    return list(csv.DictReader(io.StringIO(report.removeprefix("\ufeff"))))


def test_csv_report_includes_every_finding_and_all_scores(problematic_result):
    rows = _csv_rows(problematic_result)
    assert len(rows) == len(problematic_result.issues)
    assert [r["Kural"] for r in rows] == [i.rule_id for i in problematic_result.issues]
    assert rows[0]["Proje"] == problematic_result.project.name
    assert int(rows[0]["Genel skor (0-100)"]) == problematic_result.score.overall
    for category in problematic_result.score.categories:
        assert int(rows[0][f"{category.label} (0-100)"]) == category.score
    assert rows[0]["Çözüm önerisi"] == problematic_result.issues[0].recommendation


def test_csv_report_without_findings_still_exports_project(clean_result):
    result = deepcopy(clean_result)
    result.issues = []
    rows = _csv_rows(result)
    assert len(rows) == 1
    assert rows[0]["Proje"] == result.project.name
    assert rows[0]["Başlık"] == "Bulgu tespit edilmedi"
    assert rows[0]["Kural"] == ""


def test_csv_report_handles_untrusted_names_multiline_text_and_secrets(problematic_result):
    result = deepcopy(problematic_result)
    result.project.name = '=HYPERLINK("https://example.com")'
    result.issues[0].explanation = 'İlk satır, Türkçe\npassword="my-production-password-123"'
    rows = _csv_rows(result)
    assert rows[0]["Proje"].startswith("'=")
    assert rows[0]["Neden önemli"].startswith("İlk satır, Türkçe\n")
    assert "my-production-password-123" not in build_csv(result)


def test_readme_template_uses_detected_commands(clean_result, medium_result):
    assert "uvicorn app.main:app --reload" in build_readme(clean_result)
    assert "streamlit run src/app.py" in build_readme(medium_result)
    assert "pytest" in build_readme(clean_result)


def test_career_texts_only_claim_detected_facts(problematic_result):
    text = " ".join(problematic_result.career.cv_bullets) + problematic_result.career.linkedin_post
    assert "Docker" not in text
    assert "test yazdım" not in text
