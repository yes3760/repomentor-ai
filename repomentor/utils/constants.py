"""Central limits and lookup tables used across the analyzers."""

APP_NAME = "RepoMentor AI"
APP_VERSION = "1.2.0"

# --- Input limits -----------------------------------------------------------
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024          # compressed upload / download
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024    # zip-bomb guard
MAX_ARCHIVE_ENTRIES = 10_000
MAX_FILE_SIZE = 200_000                        # bytes; larger files are listed, not parsed
MAX_LOCK_FILE_SIZE = 3_000_000                 # dependency lock files are large but only parsed, never sent anywhere
MAX_NOTEBOOK_SIZE = 5_000_000                  # notebooks carry outputs (images); only the code cells are kept
MAX_ANALYZED_FILES = 400                       # text files read into memory
TOOL_TIMEOUT_SECONDS = 90                      # bandit / ruff subprocess timeout

IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", ".env.d", "virtualenv",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", "dist", "build", ".eggs", "site-packages", ".idea", ".vscode",
    ".ipynb_checkpoints", "htmlcov", ".next", ".cache", "__MACOSX",
}
IGNORED_SUFFIXES = (".egg-info",)

TEXT_EXTENSIONS = {
    ".py", ".pyi", ".md", ".rst", ".txt", ".json", ".yml", ".yaml", ".toml",
    ".cfg", ".ini", ".env", ".example", ".sample", ".sh", ".dockerfile",
    ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb", ".php",
    ".c", ".cpp", ".h", ".cs", ".kt", ".swift", ".html", ".css", ".sql",
}
TEXT_FILENAMES = {
    "Dockerfile", "Makefile", "Procfile", "LICENSE", "LICENCE", "COPYING",
    ".gitignore", ".dockerignore", ".env", ".python-version", "Pipfile",
}

LANGUAGE_BY_EXTENSION = {
    ".py": "Python", ".pyi": "Python", ".ipynb": "Jupyter Notebook",
    ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".php": "PHP", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++",
    ".cs": "C#", ".swift": "Swift", ".html": "HTML", ".css": "CSS", ".scss": "CSS",
    ".sql": "SQL", ".sh": "Shell", ".md": "Markdown", ".rst": "reStructuredText",
    ".yml": "YAML", ".yaml": "YAML", ".json": "JSON", ".toml": "TOML",
}
CODE_LANGUAGES = {
    "Python", "JavaScript", "TypeScript", "Java", "Kotlin", "Go", "Rust", "Ruby",
    "PHP", "C", "C++", "C#", "Swift", "Shell", "Jupyter Notebook",
}

# --- Detection tables (dependency name -> display name) ----------------------
FRAMEWORKS = {
    "streamlit": "Streamlit", "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
    "gradio": "Gradio", "dash": "Dash", "tornado": "Tornado", "aiohttp": "aiohttp",
    "sanic": "Sanic", "starlette": "Starlette", "typer": "Typer", "click": "Click",
    "scrapy": "Scrapy", "pygame": "Pygame", "kivy": "Kivy", "pyqt5": "PyQt", "pyqt6": "PyQt",
    "pyside6": "PySide", "tkinter": "Tkinter", "discord": "discord.py", "telegram": "python-telegram-bot",
    "aiogram": "aiogram", "celery": "Celery", "langchain": "LangChain", "llama_index": "LlamaIndex",
}
ML_LIBRARIES = {
    "torch": "PyTorch", "tensorflow": "TensorFlow", "keras": "Keras", "sklearn": "scikit-learn",
    "scikit-learn": "scikit-learn", "xgboost": "XGBoost", "lightgbm": "LightGBM",
    "transformers": "Hugging Face Transformers", "pandas": "pandas", "numpy": "NumPy",
    "matplotlib": "Matplotlib", "seaborn": "Seaborn", "plotly": "Plotly", "cv2": "OpenCV",
    "opencv-python": "OpenCV", "openai": "OpenAI SDK", "anthropic": "Anthropic SDK",
    "google.generativeai": "Gemini SDK", "groq": "Groq SDK", "ollama": "Ollama",
}
DATABASES = {
    "sqlite3": "SQLite", "sqlalchemy": "SQLAlchemy", "psycopg2": "PostgreSQL",
    "psycopg2-binary": "PostgreSQL", "psycopg": "PostgreSQL", "asyncpg": "PostgreSQL",
    "pymysql": "MySQL", "mysql": "MySQL", "mysql-connector-python": "MySQL",
    "pymongo": "MongoDB", "motor": "MongoDB", "redis": "Redis", "peewee": "Peewee",
    "tortoise": "Tortoise ORM", "sqlmodel": "SQLModel", "firebase_admin": "Firebase",
    "supabase": "Supabase", "chromadb": "ChromaDB", "faiss": "FAISS",
}
TEST_TOOLS = {
    "pytest": "pytest", "unittest": "unittest", "nose": "nose", "nose2": "nose2",
    "hypothesis": "Hypothesis", "tox": "tox", "coverage": "coverage", "pytest-cov": "pytest-cov",
}

ENTRY_POINT_NAMES = ("main.py", "app.py", "run.py", "manage.py", "server.py", "bot.py", "cli.py", "__main__.py", "streamlit_app.py", "wsgi.py", "asgi.py")
DEPENDENCY_FILES = ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "environment.yml", "poetry.lock", "uv.lock")
LOCK_FILES = ("poetry.lock", "uv.lock", "Pipfile.lock", "pdm.lock", "requirements.lock")
TEXT_FILENAMES |= set(LOCK_FILES)

# --- Thresholds (deliberately simple; shown to users as "this tool's scale") -
COMPLEXITY_BANDS = [
    (5, "Düşük"),
    (10, "Orta"),
    (20, "Yüksek"),
    (10**9, "Çok yüksek – refactor önerilir"),
]
LONG_FUNCTION_LINES = 50
LONG_FILE_LINES = 500
MAX_PARAMS = 6
HIGH_COMPLEXITY = 11
VERY_HIGH_COMPLEXITY = 21
DUPLICATE_WINDOW = 6

# --- Score weights (must sum to 1.0) -----------------------------------------
SCORE_WEIGHTS = {
    "quality": 0.25,
    "security": 0.25,
    "testing": 0.15,
    "documentation": 0.15,
    "organization": 0.10,
    "runnable": 0.10,
}
CATEGORY_LABELS = {
    "quality": "Kod kalitesi",
    "security": "Güvenlik",
    "testing": "Test yapısı",
    "documentation": "README & dokümantasyon",
    "organization": "Proje organizasyonu",
    "runnable": "Çalıştırılabilirlik",
}
SCORE_BANDS = [
    (90, "Çok iyi"),
    (75, "İyi"),
    (60, "Geliştirilebilir"),
    (0, "Temel iyileştirmelere ihtiyaç var"),
]
