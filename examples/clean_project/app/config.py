"""Application settings loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()


def database_path() -> str:
    """Return the SQLite file path, defaulting to a local file."""
    return os.getenv("DATABASE_PATH", "tasks.db")
