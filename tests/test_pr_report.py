"""Pull request summary: score change, new and resolved findings, quality gates."""

import pytest

from repomentor.analyzer.pr_report import MARKER, build_pr_comment
from repomentor.cli import main
from tests.conftest import analyze

BASE = {
    "app.py": '"""Notes service."""\n\n\ndef total(values: list[int]) -> int:\n    """Sum the values."""\n    return sum(values)\n',
    "README.md": "# Notes\n",
}
RISKY = BASE["app.py"] + (
    "\n\ndef calculate() -> int:\n"
    '    """Evaluate what the user typed."""\n'
    '    return eval(input("İfade: "))\n'
)


@pytest.fixture
def versions(tmp_path):
    """(base folder, head folder): the head adds an eval of user input."""
    def write(name: str, files: dict[str, str]):
        root = tmp_path / name
        for rel, content in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(content, encoding="utf-8")
        return root
    return write("base", BASE), write("head", {**BASE, "app.py": RISKY})


def test_comment_shows_score_change_and_new_findings(versions):
    base, head = (analyze(path, check_dependencies=False, run_tools=False) for path in versions)
    comment = build_pr_comment(head, base, [("Skor en az 50 olmalı", True)])
    assert comment.startswith(MARKER + "\n## 🧭 RepoMentor AI · ")
    assert f"**{base.score.overall} → {head.score.overall}**" in comment and head.score.overall < base.score.overall
    assert "### Yeni bulgular" in comment and "`app.py:" in comment
    assert "✅ Skor en az 50 olmalı" in comment
    assert "| Güvenlik |" in comment


def test_reverse_direction_lists_resolved_findings(versions):
    base, head = (analyze(path, check_dependencies=False, run_tools=False) for path in versions)
    comment = build_pr_comment(base, head)
    assert "### Giderilen bulgular" in comment and "### Yeni bulgular" not in comment


def test_unchanged_code_says_so(versions):
    base = analyze(versions[0], check_dependencies=False, run_tools=False)
    assert "yeni bir bulgu eklemiyor" in build_pr_comment(base, base)


def test_without_baseline_it_summarises_the_current_state(versions):
    head = analyze(versions[1], check_dependencies=False, run_tools=False)
    comment = build_pr_comment(head)
    assert "Temel dala göre" not in comment and "bulgu · teknik borç notu" in comment


def test_secrets_are_masked_in_the_comment(tmp_path):
    token = "sk_" + "live_" + "51HxRealLookingValue1234"   # assembled at run time: no key-shaped literal in the repository
    (tmp_path / "app.py").write_text(f'API_KEY = "{token}"\n', encoding="utf-8")
    comment = build_pr_comment(analyze(tmp_path, check_dependencies=False, run_tools=False))
    assert "51HxRealLookingValue1234" not in comment


def test_cli_compares_versions_and_enforces_max_drop(versions, tmp_path, monkeypatch):
    base, head = versions
    outputs = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    out = tmp_path / "comment.md"
    code = main([str(head), "--baseline", str(base), "--format", "pr", "-o", str(out), "--no-osv", "--max-drop", "0"])
    assert code == 1, "the head lowers the score, so a zero-tolerance gate fails"
    text = out.read_text(encoding="utf-8")
    assert text.startswith(MARKER) and "❌ Skor en fazla 0 puan düşebilir" in text
    values = dict(line.split("=", 1) for line in outputs.read_text(encoding="utf-8").splitlines())
    assert int(values["score-delta"]) < 0 and int(values["score"]) > 0
    assert main([str(head), "--baseline", str(base), "--format", "pr", "-o", str(out), "--no-osv", "--max-drop", "50"]) == 0


def test_max_drop_needs_a_baseline(versions, capsys):
    assert main([str(versions[1]), "--no-osv", "--max-drop", "3"]) == 2
    assert "--baseline" in capsys.readouterr().err
