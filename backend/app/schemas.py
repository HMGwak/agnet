from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models import TaskStatus


def normalize_repo_path(value: str) -> str:
    cleaned = value.strip()
    while len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


# --- Repo ---
class RepoCreate(BaseModel):
    name: str
    path: str
    default_branch: str = "main"

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        cleaned = normalize_repo_path(value)
        if not cleaned:
            raise ValueError("Path cannot be empty")
        return cleaned


class RepoPathPickResponse(BaseModel):
    path: str | None


class RepoResponse(BaseModel):
    id: int
    name: str
    path: str
    default_branch: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Task ---
class TaskCreate(BaseModel):
    repo_id: int
    title: str
    description: str = ""
    scheduled_for: datetime | None = None
    blocked_by_task_id: int | None = None


class TaskResumeRequest(BaseModel):
    comment: str = ""


class TaskResponse(BaseModel):
    id: int
    repo_id: int
    title: str
    description: str
    scheduled_for: datetime | None = None
    blocked_by_task_id: int | None = None
    blocked_by_title: str | None = None
    status: TaskStatus
    branch_name: str | None
    workspace_path: str | None
    plan_text: str | None
    diff_text: str | None
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    id: int
    repo_id: int
    title: str
    scheduled_for: datetime | None = None
    blocked_by_task_id: int | None = None
    blocked_by_title: str | None = None
    status: TaskStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Approval ---
class ApprovalRequest(BaseModel):
    decision: str  # "approved" or "rejected"
    comment: str = ""


class ApprovalResponse(BaseModel):
    id: int
    task_id: int
    phase: str
    decision: str
    comment: str | None
    decided_at: datetime

    model_config = {"from_attributes": True}


# --- Run ---
class RunResponse(BaseModel):
    id: int
    task_id: int
    phase: str
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    log_path: str | None

    model_config = {"from_attributes": True}
