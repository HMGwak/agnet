from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.models import TaskStatus, WorkspaceKind


def normalize_repo_path(value: str) -> str:
    cleaned = value.strip()
    while len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def normalize_text(value: str) -> str:
    return value.strip()


def normalize_text_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = value.splitlines()
    else:
        items = value
    if not isinstance(items, list):
        raise ValueError("Expected a list of strings")
    return [str(item).strip() for item in items if str(item).strip()]


class RepoProfileDraft(BaseModel):
    language: str = ""
    frameworks: list[str] = []
    package_manager: str = ""
    dev_commands: list[str] = []
    test_commands: list[str] = []
    build_commands: list[str] = []
    lint_commands: list[str] = []
    deploy_considerations: str = ""
    main_branch_protection: str = ""
    deployment_sensitivity: str = ""
    environment_notes: list[str] = []
    safety_rules: list[str] = []

    @field_validator(
        "language",
        "package_manager",
        "deploy_considerations",
        "main_branch_protection",
        "deployment_sensitivity",
        mode="before",
    )
    @classmethod
    def validate_text_fields(cls, value) -> str:
        if value is None:
            return ""
        return normalize_text(str(value))

    @field_validator(
        "frameworks",
        "dev_commands",
        "test_commands",
        "build_commands",
        "lint_commands",
        "environment_notes",
        "safety_rules",
        mode="before",
    )
    @classmethod
    def validate_list_fields(cls, value) -> list[str]:
        return normalize_text_list(value)

    def missing_required_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.language:
            missing.append("language")
        if not self.package_manager:
            missing.append("package_manager")
        if not self.dev_commands:
            missing.append("dev_commands")
        if not self.test_commands:
            missing.append("test_commands")
        if not self.deploy_considerations:
            missing.append("deploy_considerations")
        return missing


# --- Repo ---
class RepoCreate(BaseModel):
    name: str
    path: str
    default_branch: str = "main"
    create_if_missing: bool = False
    profile: RepoProfileDraft | None = None

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


class WorkspaceCreate(BaseModel):
    name: str


class WorkspaceResponse(BaseModel):
    id: int
    repo_id: int
    name: str
    kind: WorkspaceKind
    base_branch: str
    branch_name: str
    workspace_path: str | None
    is_active: bool
    task_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Task ---
class TaskCreate(BaseModel):
    repo_id: int
    title: str
    description: str = ""
    scheduled_for: datetime | None = None
    blocked_by_task_id: int | None = None
    workspace_id: int | None = None
    create_workspace: WorkspaceCreate | None = None


class TaskIntakeTurn(BaseModel):
    role: Literal["user", "assistant"]
    message: str


class TaskIntakeDraft(BaseModel):
    workspace_mode: Literal["existing", "new", "unspecified"] = "unspecified"
    workspace_id: int | None = None
    new_workspace_name: str | None = None
    title: str = ""
    description: str = ""
    blocked_by_task_id: int | None = None
    scheduled_for: datetime | None = None


class TaskIntakeRequest(BaseModel):
    repo_id: int
    user_request: str
    conversation: list[TaskIntakeTurn] = []
    draft: TaskIntakeDraft | None = None
    repo_profile: RepoProfileDraft | None = None


class TaskIntakeResponse(BaseModel):
    draft: TaskIntakeDraft
    questions: list[str] = []
    needs_confirmation: bool
    notes: list[str] = []
    repo_profile: RepoProfileDraft | None = None
    repo_profile_missing_fields: list[str] = []


class TaskResumeRequest(BaseModel):
    comment: str = ""


class RunResponse(BaseModel):
    id: int
    task_id: int
    phase: str
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    log_path: str | None

    model_config = {"from_attributes": True}


class TaskResponse(BaseModel):
    id: int
    repo_id: int
    workspace_id: int | None = None
    workspace_name: str | None = None
    workspace_kind: WorkspaceKind | None = None
    workspace_task_count: int = 0
    title: str
    description: str
    scheduled_for: datetime | None = None
    blocked_by_task_id: int | None = None
    blocked_by_title: str | None = None
    status: TaskStatus
    branch_name: str | None
    workspace_path: str | None
    exploration_text: str | None
    plan_text: str | None
    diff_text: str | None
    error_message: str | None
    retry_count: int
    runs: list[RunResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    id: int
    repo_id: int
    workspace_id: int | None = None
    workspace_name: str | None = None
    workspace_kind: WorkspaceKind | None = None
    workspace_task_count: int = 0
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
