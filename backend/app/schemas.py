from datetime import datetime

from pydantic import BaseModel

from app.models import TaskStatus


# --- Repo ---
class RepoCreate(BaseModel):
    name: str
    path: str
    default_branch: str = "main"


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


class TaskResponse(BaseModel):
    id: int
    repo_id: int
    title: str
    description: str
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
