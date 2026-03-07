from pathlib import Path

import pytest

from app.core.workflow import SymphonyWorkflowEngine
from app.models import Repo, Task, TaskStatus


class FakeWorkspaceManager:
    async def create_worktree(self, repo_path: Path, branch_name: str, task_id: int) -> Path:
        return repo_path / f"task-{task_id}"

    async def cleanup_worktree(self, repo_path: Path, workspace_path: Path) -> None:
        return None

    async def get_diff(self, workspace_path: Path, base_branch: str = "main") -> str:
        return "diff"

    async def merge_to_main(self, repo_path: Path, branch_name: str) -> tuple[bool, str]:
        return True, "ok"

    async def ensure_repository(self, repo_path: Path, default_branch: str = "main") -> None:
        return None


class FakeAgentRunner:
    def format_task_input(self, task_title: str, task_description: str) -> str:
        return task_title if not task_description else f"{task_title}\n{task_description}"

    async def cancel(self, task_id: int) -> None:
        return None

    async def generate_plan(self, workspace_path: Path, task_description: str, **kw) -> tuple[int, str]:
        return 0, "1. Do work"

    async def implement_plan(self, workspace_path: Path, plan_text: str, task_description: str, **kw) -> tuple[int, str]:
        return 0, "implemented"

    async def run_tests(self, workspace_path: Path, **kw) -> tuple[int, str]:
        return 0, "ok"


class FakeEventSink:
    def __init__(self):
        self.logs: list[str] = []
        self.transitions: list[tuple[int, str, str]] = []

    def get_log_path(self, task_id: int) -> Path:
        return Path(f"task-{task_id}.log")

    async def log(self, task_id: int, line: str) -> None:
        self.logs.append(line)

    async def broadcast_state_change(self, task_id: int, old_status: str, new_status: str) -> None:
        self.transitions.append((task_id, old_status, new_status))

    async def broadcast_task_deleted(self, task_id: int) -> None:
        return None


class FakeSession:
    def __init__(self, task: Task, repo: Repo):
        self.task = task
        self.repo = repo
        self.objects = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, value):
        if model is Task:
            return self.task
        if model is Repo:
            return self.repo
        return None

    def add(self, obj):
        self.objects.append(obj)

    async def commit(self):
        return None


class FakeSessionFactory:
    def __init__(self, task: Task, repo: Repo):
        self.task = task
        self.repo = repo

    def __call__(self):
        return FakeSession(self.task, self.repo)


@pytest.mark.asyncio
async def test_workflow_engine_moves_pending_task_to_plan_approval():
    task = Task(
        id=1,
        repo_id=2,
        title="Implement feature",
        description="",
        status=TaskStatus.PENDING,
        branch_name="task/1/implement-feature",
    )
    repo = Repo(id=2, name="demo", path="D:/repo", default_branch="main")
    events = FakeEventSink()
    engine = SymphonyWorkflowEngine(
        FakeWorkspaceManager(),
        FakeAgentRunner(),
        events,
        FakeSessionFactory(task, repo),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.AWAIT_PLAN_APPROVAL
    assert task.plan_text == "1. Do work"
    assert task.workspace_path == "D:\\repo\\task-1" or task.workspace_path == "D:/repo/task-1"
    assert events.transitions == [
        (1, "PENDING", "PREPARING_WORKSPACE"),
        (1, "PREPARING_WORKSPACE", "PLANNING"),
        (1, "PLANNING", "AWAIT_PLAN_APPROVAL"),
    ]
