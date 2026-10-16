"""SQLite access helpers. All queries are parameterised."""

import sqlite3
from contextlib import contextmanager

from app.config import database_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo'
)
"""


@contextmanager
def connect(path: str | None = None):
    """Yield a connection and commit on success."""
    connection = sqlite3.connect(path or database_path())
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(path: str | None = None) -> None:
    """Create tables if they do not exist."""
    with connect(path) as conn:
        conn.execute(SCHEMA)
