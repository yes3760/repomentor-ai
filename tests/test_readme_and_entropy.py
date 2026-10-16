"""README command verification and entropy-based secret detection."""

import pytest

from repomentor.analyzer.entropy import find_high_entropy, looks_random, shannon
from repomentor.analyzer.file_tree import scan_project
from repomentor.analyzer.readme_commands import check_readme_commands, shell_lines
from tests.conftest import EXAMPLES, ROOT, analyze

PROJECT = {
    "app/__init__.py": "",
    "app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    "run.py": "print('ok')\n",
    "requirements.txt": "fastapi\n",
    "Makefile": "test:\n\tpytest\n",
}


def broken(make_project, readme: str, extra: dict | None = None, deps: list[str] | None = None) -> list[str]:
    root = make_project({**PROJECT, **(extra or {}), "README.md": readme})
    return [b.command for b in check_readme_commands(scan_project(root), "README.md", deps or ["fastapi"])[1]]


def test_shell_lines_from_fences_prompts_and_comments():
    readme = "```bash\n$ pip install -r requirements.txt\n# a comment\n(.venv) $ pytest -q\n```\n\n```python\nprint('not a shell line')\n```\n"
    assert [line.text for line in shell_lines(readme)] == ["pip install -r requirements.txt", "pytest -q"]


BLOCK = "```bash\npip install -r requirements.txt\n```\n"


@pytest.mark.parametrize(("readme", "inline"), [
    (BLOCK + "Then run `python app.py` to start.\n", ["python app.py"]),                    # an instruction
    (BLOCK + "Uygulamayı `streamlit run main.py` ile başlatın.\n", ["streamlit run main.py"]),
    (BLOCK + "Satır içi kod (`python app.py`) da kontrol edilir.\n", []),                     # prose next to a block
    (BLOCK + "`python x.py` gibi komutlar.\n", []),                                           # an example list
    (BLOCK + "- `python x.py`: dosya var mı?\n", []),                                         # a question
    ("Start it with `python run.py`.\n", ["python run.py"]),                                  # no block: inline is all there is
    ("Supports commands such as `python x.py`.\n", []),
    ("Run `pip install -r <dosya>` or `make …`.\n", []),                                      # placeholders
])
def test_inline_commands_count_only_as_instructions(readme, inline):
    found = [line.text for line in shell_lines(readme)]
    assert [c for c in found if c != "pip install -r requirements.txt"] == inline


def test_working_commands_pass(make_project):
    readme = (
        "```bash\ngit clone https://github.com/x/demo.git\ncd demo\npython -m venv .venv\n"
        "pip install -r requirements.txt   # bağımlılıklar\npython run.py\nuvicorn app.main:app --reload\n"
        "FASTAPI_ENV=dev python -m app.main\npython -m pip install -U pip\nmake test\n```\n"
    )
    assert broken(make_project, readme, {"tests/test_x.py": "def test_x():\n    pass\n"}) == []


@pytest.mark.parametrize(("command", "extra"), [
    ("python main.py", {}),
    ("python -m application", {}),
    ("uvicorn app.main:application", {}),
    ("streamlit run dashboard.py", {}),
    ("pip install -r requirements-dev.txt", {}),
    ("cp .env.example .env", {}),
    ("docker build -t demo .", {}),
    ("pytest", {}),
    ("make lint", {}),
    ("cd backend", {}),
])
def test_broken_commands_are_found(make_project, command, extra):
    assert broken(make_project, f"```bash\n{command}\n```\n", extra) == [command]


def test_cd_changes_where_files_are_looked_up(make_project):
    readme = "```bash\ncd app\npython main.py\npython ../run.py\npython run.py\n```\n"
    assert broken(make_project, readme) == ["python run.py"]


def test_example_and_own_readmes():
    assert analyze(EXAMPLES / "clean_project", check_dependencies=False).documentation.broken_commands == []
    own = analyze(ROOT, check_dependencies=False).documentation
    assert own.commands_checked > 30 and own.broken_commands == [], "RepoMentor's own README must be runnable"


def test_broken_readme_is_reported(make_project):
    root = make_project({"app.py": "print(1)\n", "README.md": "# Demo\n\n```bash\npython main.py\n```\n"})
    issue = next(i for i in analyze(root, check_dependencies=False).issues if i.rule_id == "DOC011")
    assert "`python main.py` (`main.py` dosyası projede yok)" in issue.explanation and issue.locations[0].line == 4


# --- entropy ----------------------------------------------------------------------------------------------

def test_shannon_entropy():
    assert shannon("aaaaaaaa") == 0
    assert shannon("abcd") == 2
    assert 4.3 < shannon("T08B2F9QZ7K3vN5xW1pR4mL6cY0dH8sJ2gA4") < 6


@pytest.mark.parametrize(("value", "random"), [
    ("T08B2F9QZ7K3vN5xW1pR4mL6cY0dH8sJ2gA4", True),          # base64-like token
    ("8f613d880ced5c3f6df240ba28702b3d350714df", True),      # 40 hex characters
    ("ThisIsAVeryLongButNormalIdentifierName1", False),      # identifier, one digit
    ("550e8400-e29b-41d4-a716-446655440000", False),         # UUID
    ("repomentor.analyzer.taint.engine", False),             # dotted name, no digits
    (r"^[A-Za-z0-9+/=_\-]{20,}$", False),                    # regular expression
    ("short1A", False),
])
def test_looks_random(value, random):
    assert looks_random(value) is random


def test_context_decides_and_tests_are_skipped(make_project):
    token = "T08B2F9QZ7K3vN5xW1pR4mL6cY0dH8sJ2gA4"
    digest = "8f613d880ced5c3f6df240ba28702b3d350714df"
    root = make_project({
        "client.py": f'client = Client("{token}")\nfile_sha1 = "{digest}"\nheaders = {{"X-Auth": "{token}"}}\n',
        "settings.yml": f"service:\n  credential_blob: {token}\n  build_version: {digest}\n",
        "tests/test_client.py": f'FAKE = "{token}"\n',
    })
    hits = find_high_entropy(scan_project(root), set())
    assert sorted((h.file, h.line, h.context) for h in hits) == [
        ("client.py", 1, "Client"), ("client.py", 3, "X-Auth"), ("settings.yml", 2, "credential_blob"),
    ]


def test_problematic_example_hardcoded_token(problematic_result):
    issue = next(i for i in problematic_result.issues if i.rule_id == "SEC007")
    assert "T08***A4" in issue.explanation and "T08B2F9QZ7K3" not in issue.explanation, "the value is masked"
