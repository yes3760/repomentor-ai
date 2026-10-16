"""Task persistence."""

from app.database import connect
from app.models import Task, TaskCreate, TaskUpdate


def list_tasks(status: str | None = None, path: str | None = None) -> list[Task]:
    """Return all tasks, optionally filtered by status."""
    with connect(path) as conn:
        if status:
            rows = conn.execute("SELECT * FROM tasks WHERE status = ?", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks").fetchall()
    return [Task(**dict(row)) for row in rows]


def create_task(data: TaskCreate, path: str | None = None) -> Task:
    """Insert a task and return it."""
    with connect(path) as conn:
        cursor = conn.execute("INSERT INTO tasks (title) VALUES (?)", (data.title,))
        task_id = cursor.lastrowid
    return Task(id=task_id, title=data.title, status="todo")


def update_task(task_id: int, data: TaskUpdate, path: str | None = None) -> Task | None:
    """Apply a partial update; return None when the task does not exist."""
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        merged = {**dict(row), **data.model_dump(exclude_none=True)}
        conn.execute("UPDATE tasks SET title = ?, status = ? WHERE id = ?", (merged["title"], merged["status"], task_id))
    return Task(**merged)


def delete_task(task_id: int, path: str | None = None) -> bool:
    """Delete a task; return whether a row was removed."""
    with connect(path) as conn:
        return conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,)).rowcount > 0
