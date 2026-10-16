from app import repository
from app.models import TaskCreate, TaskUpdate


def test_create_and_list(db_path):
    repository.create_task(TaskCreate(title="a"), db_path)
    assert [t.title for t in repository.list_tasks(path=db_path)] == ["a"]


def test_filter_by_status(db_path):
    task = repository.create_task(TaskCreate(title="a"), db_path)
    repository.update_task(task.id, TaskUpdate(status="done"), db_path)
    assert repository.list_tasks("done", db_path)[0].status == "done"
    assert repository.list_tasks("todo", db_path) == []


def test_update_missing_returns_none(db_path):
    assert repository.update_task(999, TaskUpdate(title="x"), db_path) is None


def test_update_title(db_path):
    task = repository.create_task(TaskCreate(title="a"), db_path)
    assert repository.update_task(task.id, TaskUpdate(title="b"), db_path).title == "b"


def test_delete(db_path):
    task = repository.create_task(TaskCreate(title="a"), db_path)
    assert repository.delete_task(task.id, db_path) is True
    assert repository.delete_task(task.id, db_path) is False
