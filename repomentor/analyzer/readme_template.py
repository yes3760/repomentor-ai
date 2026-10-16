"""Generate a README skeleton from what was detected – a concrete fix, not just advice."""

from __future__ import annotations

from pathlib import PurePosixPath

from repomentor.models.analysis_result import AnalysisResult

TODO = "<!-- TODO: doldurun -->"


def run_command(result: AnalysisResult) -> str:
    info = result.project
    entry = info.entry_points[0] if info.entry_points else "main.py"
    module = PurePosixPath(entry).with_suffix("").as_posix().replace("/", ".")
    frameworks = set(info.frameworks)
    if "Streamlit" in frameworks:
        return f"streamlit run {entry}"
    if "FastAPI" in frameworks:
        return f"uvicorn {module}:app --reload"
    if "Django" in frameworks:
        return "python manage.py runserver"
    if "Flask" in frameworks:
        return f"flask --app {module} run"
    return f"python {entry}"


def install_command(result: AnalysisResult) -> str:
    files = result.project.dependency_files
    if "requirements.txt" in files:
        return "pip install -r requirements.txt"
    if any(f.endswith("pyproject.toml") for f in files):
        return "pip install -e ."
    return "pip install -r requirements.txt  # önce requirements.txt oluşturun"


def build_readme(result: AnalysisResult) -> str:
    info = result.project
    description = (info.github or {}).get("description") or f"{TODO} Projenin hangi problemi çözdüğünü 2-3 cümleyle anlatın."
    repo_url = info.source_url or "https://github.com/KULLANICI/PROJE"
    folder = repo_url.rstrip("/").rsplit("/", 1)[-1]
    lines = [
        f"# {info.name}", "",
        description, "",
        "![Ekran görüntüsü](docs/screenshot.png)", "",
        "## Özellikler", "",
        f"- {TODO} Özellik 1",
        f"- {TODO} Özellik 2",
        f"- {TODO} Özellik 3", "",
        "## Kullanılan teknolojiler", "",
        *[f"- {tech}" for tech in info.technologies], "",
        "## Kurulum", "",
        f"Gereksinim: Python {info.python_version or '3.10+'}", "",
        "```bash",
        f"git clone {repo_url}.git",
        f"cd {folder}",
        "python -m venv .venv",
        "source .venv/bin/activate   # Windows: .venv\\Scripts\\activate",
        install_command(result),
    ]
    if result.documentation.has_env_example:
        lines.append("cp .env.example .env   # ardından değerleri doldurun")
    lines += ["```", "", "## Kullanım", "", "```bash", run_command(result), "```", ""]
    if result.tests.test_files:
        lines += ["## Testler", "", "```bash", "pytest", "```", ""]
    if info.has_docker:
        lines += ["## Docker", "", "```bash", f"docker build -t {folder.lower()} .", f"docker run -p 8000:8000 {folder.lower()}", "```", ""]
    lines += [
        "## Proje yapısı", "",
        f"{TODO} Ana klasörleri ve sorumluluklarını kısaca açıklayın.", "",
        "## Lisans", "",
        "MIT" if not result.documentation.license_file else f"Ayrıntılar için [{result.documentation.license_file}]({result.documentation.license_file}) dosyasına bakın.",
        "",
    ]
    return "\n".join(lines)
