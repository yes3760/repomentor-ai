"""Request and response schemas."""

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["todo", "doing", "done"]


class TaskCreate(BaseModel):
    """Payload for creating a task."""

    title: str = Field(min_length=1, max_length=200)


class TaskUpdate(BaseModel):
    """Payload for updating a task."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Status | None = None


class Task(BaseModel):
    """A stored task."""

    id: int
    title: str
    status: Status
