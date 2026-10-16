import pytest
from pydantic import ValidationError

from app.models import TaskCreate, TaskUpdate


def test_title_required():
    with pytest.raises(ValidationError):
        TaskCreate(title="")


def test_invalid_status_rejected():
    with pytest.raises(ValidationError):
        TaskUpdate(status="archived")


def test_valid_update():
    assert TaskUpdate(status="doing").status == "doing"


def test_title_length_limit():
    with pytest.raises(ValidationError):
        TaskCreate(title="x" * 201)


def test_partial_update_defaults():
    assert TaskUpdate().model_dump(exclude_none=True) == {}
