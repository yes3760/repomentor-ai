"""Detect what kind of project this is and which technologies it uses."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import PurePosixPath

from repomentor.analyzer.file_tree import ProjectFiles, language_breakdown
from repomentor.models.analysis_result import ProjectInfo
from repomentor.utils.constants import (
    CODE_LANGUAGES,
    DATABASES,
    DEPENDENCY_FILES,
    ENTRY_POINT_NAMES,
    FRAMEWORKS,
    ML_LIBRARIES,
    TEST_TOOLS,
)

REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
CI_PATHS = (".github/workflows/", ".gitlab-ci.yml", ".circleci/", "azure-pipelines.yml", "Jenkinsfile", ".travis.yml")


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_names(lines: list[str]) -> list[str]:
    names = []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http://", "https://")):
            continue
        if match := REQUIREMENT_NAME.match(line):
            names.append(_normalise(match.group(1)))
    return names


def _load_toml(project: ProjectFiles, path: str) -> dict:
    try:
        return tomllib.loads(project.text(path) or "")
    except tomllib.TOMLDecodeError:
        return {}


def _from_requirements(project: ProjectFiles) -> list[str]:
    paths = project.by_name("requirements.txt", "requirements-dev.txt", "requirements_dev.txt", "dev-requirements.txt")
    paths += [f.path for f in project.files if PurePosixPath(f.path).parent.name == "requirements" and f.path.endswith(".txt")]
    return [name for path in paths for name in _requirement_names((project.text(path) or "").splitlines())]


def _from_pyproject(data: dict) -> tuple[list[str], str | None]:
    proj = data.get("project", {})
    poetry = data.get("tool", {}).get("poetry", {})
    groups = list(proj.get("optional-dependencies", {}).values()) + list(data.get("dependency-groups", {}).values())
    deps = _requirement_names(proj.get("dependencies", []))
    deps += [name for group in groups for name in _requirement_names([g for g in group if isinstance(g, str)])]
    poetry_tables = [poetry.get("dependencies", {}), poetry.get("dev-dependencies", {})]
    poetry_tables += [g.get("dependencies", {}) for g in poetry.get("group", {}).values()]
    deps += [_normalise(n) for table in poetry_tables for n in table if n.lower() != "python"]
    version = proj.get("requires-python") or poetry.get("dependencies", {}).get("python")
    return deps, version


def _from_setup_py(text: str) -> list[str]:
    match = re.search(r"install_requires\s*=\s*\[(.*?)\]", text, re.S)
    return _requirement_names(re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))) if match else []


def parse_dependencies(project: ProjectFiles) -> tuple[list[str], str | None]:
    """Return (dependency names, declared python version) from common manifests."""
    deps = _from_requirements(project)
    python_version: str | None = None
    for path in project.by_name("pyproject.toml")[:1]:
        found, python_version = _from_pyproject(_load_toml(project, path))
        deps += found
    for path in project.by_name("setup.py")[:1]:
        deps += _from_setup_py(project.text(path) or "")
    for path in project.by_name("Pipfile")[:1]:
        data = _load_toml(project, path)
        deps += [_normalise(n) for n in {**data.get("packages", {}), **data.get("dev-packages", {})}]
    for path in project.at_root(".python-version", "runtime.txt"):
        python_version = python_version or (project.text(path) or "").strip().replace("python-", "") or None
    return sorted(set(deps)), python_version


def collect_imports(project: ProjectFiles) -> set[str]:
    """Top-level third-party/stdlib module names imported anywhere in the project."""
    local_modules = {PurePosixPath(p).parts[0].removesuffix(".py") for p in project.python_files}
    local_modules |= {PurePosixPath(p).stem for p in project.python_files}
    imports: set[str] = set()
    for _, tree in project.parsed_python():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imports.add(node.module)
                imports.add(node.module.split(".")[0])
    return {i for i in imports if i.split(".")[0] not in local_modules}


def _match(table: dict[str, str], names: set[str]) -> list[str]:
    found: list[str] = []
    for key, label in table.items():
        if (key in names or _normalise(key) in names) and label not in found:
            found.append(label)
    return found


def find_entry_points(project: ProjectFiles) -> list[str]:
    entries = [p for p in project.by_name(*ENTRY_POINT_NAMES) if p.count("/") <= 2 and "test" not in p]
    for path in project.source_python_files:
        if path in entries:
            continue
        text = project.text(path) or ""
        if re.search(r"""if\s+__name__\s*==\s*['"]__main__['"]""", text) and path.count("/") <= 2:
            entries.append(path)
    return entries[:6]


MANIFEST_TYPES = (
    (("package.json",), "Node.js / JavaScript projesi"),
    (("pom.xml", "build.gradle"), "Java projesi"),
    (("go.mod",), "Go projesi"),
    (("Cargo.toml",), "Rust projesi"),
)
LLM_SDKS = {"OpenAI SDK", "Anthropic SDK", "Gemini SDK", "Groq SDK", "Ollama", "LangChain", "LlamaIndex"}
ML_CORE = {"PyTorch", "TensorFlow", "Keras", "scikit-learn", "XGBoost", "LightGBM", "Hugging Face Transformers"}
# First matching rule wins; each rule is (technologies that trigger it, project type).
PYTHON_TYPES = (
    ({"FastAPI", "Starlette", "Sanic"}, "Python web API'si"),
    ({"Flask", "Django", "aiohttp", "Tornado"}, "Python web uygulaması"),
    ({"Streamlit", "Gradio", "Dash"}, "Python veri / yapay zekâ arayüz uygulaması"),
    (LLM_SDKS, "Python LLM / yapay zekâ uygulaması"),
    (ML_CORE, "Python makine öğrenmesi projesi"),
    ({"discord.py", "python-telegram-bot", "aiogram"}, "Python bot projesi"),
    ({"Pygame", "Kivy"}, "Python oyun / etkileşimli uygulama"),
    ({"PyQt", "PySide", "Tkinter"}, "Python masaüstü uygulaması"),
    ({"Scrapy"}, "Python web kazıma (scraping) projesi"),
    ({"Typer", "Click", "argparse"}, "Python komut satırı aracı"),
)


def detect_project_type(info: ProjectInfo, project: ProjectFiles, imports: set[str] = frozenset()) -> str:
    if info.primary_language != "Python":
        paths = set(project.paths)
        for manifests, label in MANIFEST_TYPES:
            if paths & set(manifests):
                return label
        return f"{info.primary_language} projesi" if info.primary_language else "Bilinmeyen proje türü"

    techs = set(info.frameworks) | set(info.ml_libraries) | ({"argparse"} & imports)
    for triggers, label in PYTHON_TYPES:
        if techs & triggers:
            return label
    if project.at_root("pyproject.toml", "setup.py") and not info.entry_points:
        return "Python kütüphanesi / paketi"
    return "Python projesi"


DOCKER_FILES = ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml")


def _primary_language(project: ProjectFiles, languages: dict[str, int]) -> str | None:
    primary = next((lang for lang in languages if lang in CODE_LANGUAGES), None)
    if primary is None and any(p.endswith(".ipynb") for p in project.paths):
        return "Jupyter Notebook"
    return primary


def _implicit_test_tool(project: ProjectFiles, imports: set[str]) -> list[str]:
    """Tests exist but no test tool is declared: infer pytest/unittest."""
    if not project.test_python_files:
        return []
    return ["unittest"] if "unittest" in imports else ["pytest"]


def detect_project(project: ProjectFiles, name: str, source: str, source_url: str | None, github: dict | None) -> ProjectInfo:
    """Languages, frameworks, databases, tooling, entry points and project type."""
    languages = language_breakdown(project)
    deps, python_version = parse_dependencies(project)
    imports = collect_imports(project)
    names = set(deps) | {_normalise(i) for i in imports} | imports
    info = ProjectInfo(
        name=name, source=source, source_url=source_url, github=github,
        primary_language=_primary_language(project, languages),
        languages=languages,
        frameworks=_match(FRAMEWORKS, names),
        ml_libraries=_match(ML_LIBRARIES, names),
        databases=_match(DATABASES, names),
        test_tools=_match(TEST_TOOLS, names) or _implicit_test_tool(project, imports),
        has_docker=bool(project.by_name(*DOCKER_FILES)),
        has_ci=any(p.startswith(CI_PATHS) or p in CI_PATHS for p in project.paths),
        dependency_files=[p for p in project.by_name(*DEPENDENCY_FILES) if p.count("/") <= 1],
        dependencies=deps,
        python_version=python_version,
        entry_points=find_entry_points(project),
    )
    info.project_type = detect_project_type(info, project, imports)
    return info
