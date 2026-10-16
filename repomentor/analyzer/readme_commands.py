"""Check that the commands a README tells people to run would actually work.

Commands are read from fenced shell blocks (and inline code that starts with a
known command), followed through `cd`, and checked against the project:
files, modules, ASGI attributes, requirement files, Makefile targets, tests.
Commands RepoMentor cannot judge (network, package managers, tools it does not
know) are skipped rather than guessed.
"""

from __future__ import annotations

import ast
import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.models.analysis_result import BrokenCommand

SHELL_LANGS = {"", "bash", "sh", "shell", "console", "zsh", "terminal", "powershell", "ps1", "cmd", "bat", "text"}
FENCE = re.compile(r"^```\s*([\w+-]*)\s*$")
INLINE = re.compile(r"`((?:python3?|py|streamlit|uvicorn|pip3?|pytest|docker|flask|make)\s[^`]+)`")
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PROMPT = re.compile(r"^(?:\(?[\w.-]*\)?\s*)?(?:\$|>|PS>)\s+")
CODE_SPAN = re.compile(r"`[^`]*`")
PLACEHOLDER = re.compile(r"…|\.\.\.|<[^>]*>")
# Prose around inline code that marks a description, not an instruction: example lists and questions.
DESCRIPTIVE = re.compile(r"\bgibi\b|\börne[ğg]in\b|\börn?\.|\be\.g\.|\bsuch as\b|\blike\b|\bfor example\b|\?", re.I)
# Verbs that ask the reader to run something ("`python app.py` ile başlatın", "Run `make test`").
INSTRUCTION = re.compile(
    r"\b(?:run|execute|start|launch|type|enter|install|invoke|çalıştır\w*|başlat\w*|"
    r"kur(?:un|unuz|mak|up|ulum|duktan|arak)|yükle(?:yin|yiniz|yip|mek)|yaz(?:ın|ınız|arak)|uygula(?:yın|yınız|mak))\b",
    re.I,
)
KNOWN_MODULES = {
    "pip", "venv", "pytest", "unittest", "http", "ensurepip", "streamlit", "uvicorn", "flask", "black", "ruff", "mypy",
    "build", "twine", "spacy", "nltk", "json", "pydoc", "doctest", "timeit", "cProfile", "py_compile", "compileall",
    "site", "sqlite3", "webbrowser", "pipx", "poetry", "pdm", "uv", "gunicorn", "jupyter", "notebook", "isort",
    "coverage", "tox", "nox", "pre_commit", "django", "alembic", "celery", "locust", "playwright", "ipykernel", "idlelib",
}


@dataclass
class _Line:
    text: str
    number: int


def _inline_commands(raw: str, number: int) -> list[tuple[_Line, bool]]:
    """Inline commands on one prose line, each with whether the sentence asks the reader to run it.

    Example lists ("commands like `a`, `b`, `c`"), questions ("does `python x.py` exist?") and
    placeholders (`pip install -r …`) describe commands; they are never checked.
    """
    commands = [match.group(1) for match in INLINE.finditer(raw)]
    prose = CODE_SPAN.sub(" ", raw)
    if not commands or len(commands) >= 3 or DESCRIPTIVE.search(prose):
        return []
    told = bool(INSTRUCTION.search(prose))
    return [(_Line(command, number), told) for command in commands if not PLACEHOLDER.search(command)]


def _block_command(raw: str) -> str | None:
    """A shell-block line without its prompt; `#` lines are comments in READMEs, not root prompts."""
    line = raw.strip()
    return None if line.startswith(("#", "//")) else PROMPT.sub("", line) or None


def shell_lines(readme: str) -> list[_Line]:
    """Commands a reader is told to run, in document order.

    Every line of a shell code block counts. Inline code counts when its sentence is an instruction
    ("`python app.py` ile başlatın"), or, in a README without any shell block, unless it is clearly a
    description. Fenced blocks are what readers copy and run, so next to them unexplained inline code
    is more often prose about a command than a command.
    """
    found: list[tuple[_Line, bool]] = []      # (line, counts even next to shell blocks)
    in_block, shell, has_block = False, False, False
    for number, raw in enumerate(readme.splitlines(), 1):
        fence = FENCE.match(raw.strip())
        if fence:
            in_block, shell = (not in_block), fence.group(1).lower() in SHELL_LANGS
            continue
        if in_block and shell:
            has_block = True
            found += [(_Line(text, number), True)] if (text := _block_command(raw)) else []
        elif not in_block:
            found += _inline_commands(raw, number)
    return [line for line, certain in found if certain or not has_block]


def _top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        names.update(t.id for t in targets if isinstance(t, ast.Name))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


class _Checker:
    def __init__(self, project: ProjectFiles, dependencies: list[str]):
        self.project = project
        self.paths = set(project.paths)
        self.dirs = {str(parent) for p in project.paths for parent in PurePosixPath(p).parents if str(parent) != "."}
        self.dependencies = {d.replace("-", "_").lower() for d in dependencies}
        self.cwd = ""
        self.cloned = False

    # helpers
    def _rel(self, path: str) -> str:
        joined = PurePosixPath(self.cwd) / path if self.cwd else PurePosixPath(path)
        parts: list[str] = []
        for part in joined.parts:
            if part == "..":
                parts = parts[:-1]
            elif part not in {".", ""}:
                parts.append(part)
        return "/".join(parts)

    def exists(self, path: str) -> bool:
        rel = self._rel(path.rstrip("/"))
        return rel == "" or rel in self.paths or rel in self.dirs

    def module_file(self, dotted: str) -> str | None:
        base = self._rel(dotted.replace(".", "/"))
        candidates = [f"{base}.py", f"{base}/__init__.py", f"{base}/__main__.py", f"src/{base}.py", f"src/{base}/__init__.py"]
        return next((c for c in candidates if c in self.paths), None)

    def defines(self, path: str, name: str) -> bool:
        tree = self.project.tree(path) if path.endswith(".py") and path in self.project.texts else None
        return tree is None or name in _top_level_names(tree)   # unparsable: cannot tell, do not report

    # commands
    def check(self, argv: list[str]) -> str | None:
        command = PurePosixPath(argv[0]).name.lower()
        handler = {
            "cd": self._cd, "python": self._python, "python3": self._python, "py": self._python,
            "streamlit": self._streamlit, "uvicorn": self._asgi, "gunicorn": self._asgi, "flask": self._flask,
            "pip": self._pip, "pip3": self._pip, "cp": self._copy, "copy": self._copy, "mv": self._copy,
            "docker": self._docker, "pytest": self._pytest, "make": self._make, "git": self._git,
        }.get(command)
        return handler(argv[1:]) if handler else None

    def _git(self, args: list[str]) -> None:
        self.cloned = self.cloned or (args[:1] == ["clone"])

    def _cd(self, args: list[str]) -> str | None:
        target = args[0] if args else ""
        if not target or target in {"~", "-"} or target.startswith(("$", "/", "~")):
            return None
        if self.exists(target):
            self.cwd = self._rel(target)
            return None
        if self.cloned and "/" not in target.strip("/"):
            self.cloned = False          # `cd repo-name` right after `git clone`: the repository root
            self.cwd = ""
            return None
        return f"`{target}` klasörü projede yok"

    def _python(self, args: list[str]) -> str | None:
        args = [a for a in args if not a.startswith("-") or a in {"-m", "-c"}]
        if not args or args[0] == "-c":
            return None
        if args[0] == "-m":
            return self._module(args[1]) if len(args) > 1 else None
        script = args[0]
        if script.endswith((".py", ".pyw")) and not self.exists(script):
            return f"`{script}` dosyası projede yok"
        return None

    def _module(self, dotted: str) -> str | None:
        top = dotted.split(".")[0]
        if top in KNOWN_MODULES or top.replace("-", "_").lower() in self.dependencies or self.module_file(dotted):
            return None
        return f"`{dotted}` modülü projede bulunamadı"

    def _streamlit(self, args: list[str]) -> str | None:
        if len(args) >= 2 and args[0] == "run" and args[1].endswith(".py") and not self.exists(args[1]):
            return f"`{args[1]}` dosyası projede yok"
        return None

    def _asgi(self, args: list[str]) -> str | None:
        target = next((a for a in args if ":" in a and not a.startswith("-")), None)
        if not target:
            return None
        module, attr = target.split(":", 1)
        path = self.module_file(module)
        if path is None:
            return f"`{module}` modülü projede yok"
        if attr.isidentifier() and not self.defines(path, attr):
            return f"`{path}` içinde `{attr}` tanımlı değil"
        return None

    def _flask(self, args: list[str]) -> str | None:
        if "--app" in args and args.index("--app") + 1 < len(args):
            module = args[args.index("--app") + 1].split(":")[0].removesuffix(".py")
            return None if self.module_file(module) else f"`{module}` modülü projede yok"
        return None

    def _pip(self, args: list[str]) -> str | None:
        for flag in ("-r", "--requirement", "-c", "--constraint"):
            if flag in args and args.index(flag) + 1 < len(args):
                path = args[args.index(flag) + 1]
                if not self.exists(path):
                    return f"`{path}` dosyası projede yok"
        editable_here = "-e" in args and args.index("-e") + 1 < len(args) and args[args.index("-e") + 1] in {".", "./"}
        if editable_here and not any(self.exists(p) for p in ("setup.py", "pyproject.toml", "setup.cfg")):
            return "`pip install -e .` için setup.py / pyproject.toml yok"
        return None

    def _copy(self, args: list[str]) -> str | None:
        sources = [a for a in args if not a.startswith("-")][:-1]
        missing = [s for s in sources if not any(ch in s for ch in "*?$") and not s.startswith(("/", "~")) and not self.exists(s)]
        return f"`{missing[0]}` dosyası projede yok" if missing else None

    def _docker(self, args: list[str]) -> str | None:
        if args[:1] == ["build"]:
            dockerfile = args[args.index("-f") + 1] if "-f" in args and args.index("-f") + 1 < len(args) else "Dockerfile"
            return None if self.exists(dockerfile) else f"`{dockerfile}` dosyası projede yok"
        if args[:1] == ["compose"] or args[:1] == ["-compose"]:
            names = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
            return None if any(self.exists(n) for n in names) else "docker compose dosyası projede yok"
        return None

    def _pytest(self, args: list[str]) -> str | None:
        if not self.project.test_python_files:
            return "projede test bulunmuyor"
        missing = [a for a in args if not a.startswith("-") and "/" in a and not self.exists(a.split("::")[0])]
        return f"`{missing[0]}` test yolu yok" if missing else None

    def _make(self, args: list[str]) -> str | None:
        makefile = next((p for p in ("Makefile", "makefile") if self._rel(p) in self.paths), None)
        if makefile is None:
            return "Makefile yok"
        targets = set(re.findall(r"^([\w.-]+)\s*:", self.project.text(self._rel(makefile)) or "", re.M))
        target = next((a for a in args if not a.startswith("-") and "=" not in a), None)
        return f"Makefile'da `{target}` hedefi yok" if target and target not in targets else None


def check_readme_commands(project: ProjectFiles, readme_path: str | None, dependencies: list[str]) -> tuple[int, list[BrokenCommand]]:
    """(commands checked, commands that would fail)."""
    text = project.text(readme_path) if readme_path else None
    if not text:
        return 0, []
    checker = _Checker(project, dependencies)
    checked, broken = 0, []
    for line in shell_lines(text):
        for part, argv in _commands(line.text):
            checked += 1
            if problem := checker.check(argv):
                broken.append(BrokenCommand(command=part, problem=problem, line=line.number))
    return checked, broken


def _commands(text: str) -> list[tuple[str, list[str]]]:
    """(command text, argv) for each command chained with `&&`, `;` or `||`; env assignments dropped."""
    commands = []
    for part in re.split(r"\s*(?:&&|;|\|\|)\s*", text):
        try:
            argv = shlex.split(part, comments=True, posix=True)
        except ValueError:
            continue
        while argv and ENV_ASSIGNMENT.match(argv[0]):   # `FLASK_APP=app.py flask run`
            argv.pop(0)
        if argv:
            commands.append((part.strip(), argv))
    return commands
