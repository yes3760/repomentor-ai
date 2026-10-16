"""HTTP routes."""

from fastapi import FastAPI, HTTPException

from app import repository
from app.database import init_db
from app.models import Task, TaskCreate, TaskUpdate

app = FastAPI(title="Görev Takip API")


@app.on_event("startup")
def startup() -> None:
    """Make sure the database schema exists."""
    init_db()


@app.get("/tasks", response_model=list[Task])
def get_tasks(status: str | None = None) -> list[Task]:
    """List tasks."""
    return repository.list_tasks(status)


@app.post("/tasks", response_model=Task, status_code=201)
def post_task(data: TaskCreate) -> Task:
    """Create a task."""
    return repository.create_task(data)


@app.patch("/tasks/{task_id}", response_model=Task)
def patch_task(task_id: int, data: TaskUpdate) -> Task:
    """Update a task."""
    task = repository.update_task(task_id, data)
    if task is None:
        raise HTTPException(status_code=404, detail="Görev bulunamadı")
    return task


@app.delete("/tasks/{task_id}", status_code=204)
def remove_task(task_id: int) -> None:
    """Delete a task."""
    if not repository.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Görev bulunamadı")
