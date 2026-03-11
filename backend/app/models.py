import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    PREPARING_WORKSPACE = "PREPARING_WORKSPACE"
    PLANNING = "PLANNING"
    AWAIT_PLAN_APPROVAL = "AWAIT_PLAN_APPROVAL"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    AWAIT_MERGE_APPROVAL = "AWAIT_MERGE_APPROVAL"
    MERGING = "MERGING"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkspaceKind(str, enum.Enum):
    MAIN = "MAIN"
    FEATURE = "FEATURE"


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    path: Mapped[str] = mapped_column(String(1024))
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="repo")
    tasks: Mapped[list["Task"]] = relationship(back_populates="repo")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[WorkspaceKind] = mapped_column(Enum(WorkspaceKind), default=WorkspaceKind.FEATURE)
    base_branch: Mapped[str] = mapped_column(String(100), default="main")
    branch_name: Mapped[str] = mapped_column(String(200))
    workspace_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    repo: Mapped["Repo"] = relationship(back_populates="workspaces")
    tasks: Mapped[list["Task"]] = relationship(back_populates="workspace")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"))
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    blocked_by_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING
    )
    branch_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    workspace_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    exploration_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    repo: Mapped["Repo"] = relationship(back_populates="tasks")
    workspace: Mapped[Workspace | None] = relationship(back_populates="tasks")
    runs: Mapped[list["Run"]] = relationship(back_populates="task")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="task")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    phase: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="runs")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    phase: Mapped[str] = mapped_column(String(20))
    decision: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    task: Mapped["Task"] = relationship(back_populates="approvals")


class ArchivedTask(Base):
    __tablename__ = "archived_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_task_id: Mapped[int] = mapped_column(Integer)
    repo_id: Mapped[int] = mapped_column(Integer)
    workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50))
    snapshot_json: Mapped[str] = mapped_column(Text)
    archived_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
