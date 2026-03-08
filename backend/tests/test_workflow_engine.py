from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.workflow import SymphonyWorkflowEngine
from app.models import Repo, Task, TaskStatus, Workspace, WorkspaceKind


class FakeWorkspaceManager:
    def __init__(self, *, has_changes: bool = True):
        self.has_changes = has_changes

    async def create_worktree(
        self,
        repo_path: Path,
        branch_name: str,
        workspace_id: int,
        repo_id: int | None = None,
        repo_name: str | None = None,
        workspace_name: str | None = None,
        base_branch: str = "main",
    ) -> Path:
        if repo_id is None:
            return Path(f"D:/workspaces/workspace-{workspace_id}")
        return Path(f"D:/workspaces/repo-{repo_id}-demo/workspace-{workspace_id}-main")

    async def cleanup_worktree(self, repo_path: Path, workspace_path: Path) -> None:
        return None

    async def has_working_tree_changes(self, workspace_path: Path) -> bool:
        return self.has_changes

    async def get_diff(self, workspace_path: Path, base_branch: str = "main") -> str:
        return "diff"

    async def merge_to_main(
        self,
        repo_path: Path,
        branch_name: str,
        base_branch: str = "main",
    ) -> tuple[bool, str]:
        return True, "ok"

    async def ensure_repository(self, repo_path: Path, default_branch: str = "main") -> None:
        return None


class FakeAgentRunner:
    def __init__(
        self,
        critique_output: str | None = None,
        review_output: str | None = None,
        test_output: str | None = None,
    ):
        self.policy = SimpleNamespace(
            critique_max_rounds=2,
            test_fix_loops=2,
            critique_required=True,
            review_required=True,
        )
        self.critique_output = (
            critique_output
            or "VERDICT: APPROVED\nSUMMARY: Plan looks good.\nPLAN:\n1. Do work"
        )
        self.review_output = (
            review_output
            or "VERDICT: PASS\nSUMMARY: Ready for merge.\nDETAILS:\nLooks good."
        )
        self.test_output = (
            test_output
            or "VERDICT: PASS\nSUMMARY: Tests passed.\nDETAILS:\npytest ok."
        )

    def format_task_input(self, task_title: str, task_description: str) -> str:
        return task_title if not task_description else f"{task_title}\n{task_description}"

    async def cancel(self, task_id: int) -> None:
        return None

    async def generate_plan(self, workspace_path: Path, task_description: str, **kw) -> tuple[int, str]:
        return 0, "1. Do work"

    async def critique_plan(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        **kw,
    ) -> tuple[int, str]:
        return 0, self.critique_output

    async def implement_plan(self, workspace_path: Path, plan_text: str, task_description: str, **kw) -> tuple[int, str]:
        return 0, "implemented"

    async def run_tests(self, workspace_path: Path, **kw) -> tuple[int, str]:
        return 0, self.test_output

    async def review_result(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        test_output: str,
        diff_text: str,
        **kw,
    ) -> tuple[int, str]:
        return 0, self.review_output


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
    def __init__(self, task: Task, repo: Repo, workspace: Workspace):
        self.task = task
        self.repo = repo
        self.workspace = workspace
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
        if model is Workspace:
            return self.workspace
        return None

    def add(self, obj):
        self.objects.append(obj)

    async def commit(self):
        return None


class FakeSessionFactory:
    def __init__(self, task: Task, repo: Repo, workspace: Workspace):
        self.task = task
        self.repo = repo
        self.workspace = workspace

    def __call__(self):
        return FakeSession(self.task, self.repo, self.workspace)


@pytest.mark.asyncio
async def test_workflow_engine_moves_pending_task_to_merge_approval():
    task = Task(
        id=1,
        repo_id=2,
        workspace_id=5,
        title="Implement feature",
        description="",
        status=TaskStatus.PENDING,
    )
    repo = Repo(id=2, name="demo", path="D:/repo", default_branch="main")
    workspace = Workspace(
        id=5,
        repo_id=2,
        name="Main",
        kind=WorkspaceKind.MAIN,
        base_branch="main",
        branch_name="workspace/main/2",
        workspace_path=None,
        is_active=True,
    )
    events = FakeEventSink()
    engine = SymphonyWorkflowEngine(
        FakeWorkspaceManager(),
        FakeAgentRunner(),
        events,
        FakeSessionFactory(task, repo, workspace),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.AWAIT_MERGE_APPROVAL
    assert task.plan_text == "1. Do work"
    assert task.diff_text == "diff"
    assert (
        task.workspace_path
        == "D:\\workspaces\\repo-2-demo\\workspace-5-main"
        or task.workspace_path == "D:/workspaces/repo-2-demo/workspace-5-main"
    )
    assert workspace.workspace_path == task.workspace_path
    assert events.transitions == [
        (1, "PENDING", "PREPARING_WORKSPACE"),
        (1, "PREPARING_WORKSPACE", "PLANNING"),
        (1, "PLANNING", "IMPLEMENTING"),
        (1, "IMPLEMENTING", "TESTING"),
        (1, "TESTING", "AWAIT_MERGE_APPROVAL"),
    ]


@pytest.mark.asyncio
async def test_workflow_engine_moves_to_needs_attention_when_critique_does_not_converge():
    task = Task(
        id=1,
        repo_id=2,
        workspace_id=5,
        title="Implement feature",
        description="",
        status=TaskStatus.PENDING,
    )
    repo = Repo(id=2, name="demo", path="D:/repo", default_branch="main")
    workspace = Workspace(
        id=5,
        repo_id=2,
        name="Main",
        kind=WorkspaceKind.MAIN,
        base_branch="main",
        branch_name="workspace/main/2",
        workspace_path=None,
        is_active=True,
    )
    events = FakeEventSink()
    engine = SymphonyWorkflowEngine(
        FakeWorkspaceManager(),
        FakeAgentRunner(
            critique_output="VERDICT: REVISE\nSUMMARY: Needs work.\nPLAN:\n1. Try again"
        ),
        events,
        FakeSessionFactory(task, repo, workspace),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.NEEDS_ATTENTION
    assert "Plan critique did not converge" in task.error_message


@pytest.mark.asyncio
async def test_workflow_engine_moves_to_needs_attention_when_implementation_makes_no_changes():
    task = Task(
        id=1,
        repo_id=2,
        workspace_id=5,
        title="Implement feature",
        description="",
        status=TaskStatus.PENDING,
    )
    repo = Repo(id=2, name="demo", path="D:/repo", default_branch="main")
    workspace = Workspace(
        id=5,
        repo_id=2,
        name="Main",
        kind=WorkspaceKind.MAIN,
        base_branch="main",
        branch_name="workspace/main/2",
        workspace_path=None,
        is_active=True,
    )
    events = FakeEventSink()
    engine = SymphonyWorkflowEngine(
        FakeWorkspaceManager(has_changes=False),
        FakeAgentRunner(),
        events,
        FakeSessionFactory(task, repo, workspace),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.NEEDS_ATTENTION
    assert "Implementation completed without creating any file changes" in task.error_message
