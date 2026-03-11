from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.workflow import SymphonyWorkflowEngine
from app.models import Repo, Run, Task, TaskStatus, Workspace, WorkspaceKind


class FakeWorkspaceManager:
    def __init__(self, *, has_changes: bool = True):
        self.has_changes = has_changes
        self.commits: list[tuple[Path, str]] = []

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

    async def commit_workspace_changes(self, workspace_path: Path, message: str) -> bool:
        self.commits.append((workspace_path, message))
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
        explore_exit_code: int = 0,
        explore_output: str | list[str] | None = None,
        critique_output: str | None = None,
        review_output: str | list[str] | None = None,
        test_output: str | list[str] | None = None,
        orchestrate_output: str | list[str] | None = None,
        recovery_output: str | list[str] | None = None,
        verify_output: str | list[str] | None = None,
        implement_output: str | list[str] | None = None,
    ):
        self.policy = SimpleNamespace(
            critique_max_rounds=2,
            test_fix_loops=2,
            critique_required=True,
            review_required=True,
        )
        self.explore_exit_code = explore_exit_code
        self.explore_output = explore_output or "SUMMARY: Repo entrypoints found."
        self.critique_output = (
            critique_output
            or "VERDICT: APPROVED\nSUMMARY: Plan looks good.\nPLAN:\n1. Do work"
        )
        self.review_output = review_output or (
            "VERDICT: PASS\nSUMMARY: Ready for merge.\nDETAILS:\nLooks good."
        )
        self.test_output = test_output or (
            "VERDICT: PASS\nSUMMARY: Tests passed.\nDETAILS:\npytest ok."
        )
        self.orchestrate_output = orchestrate_output or (
            "ACTION: ESCALATE\nSUMMARY: Needs user input.\nRATIONALE:\nNo safe automatic path."
        )
        self.recovery_output = recovery_output or "1. Adjust plan"
        self.verify_output = verify_output or (
            "VERDICT: PASS\nSUMMARY: Completion verified.\nDETAILS:\nLooks complete."
        )
        self.implement_output = implement_output or "implemented"
        self.explore_calls: list[dict] = []
        self.orchestrate_calls: list[dict] = []
        self.recovery_calls: list[dict] = []

    def _next(self, value):
        if isinstance(value, list):
            assert value, "No more fake outputs configured"
            return value.pop(0)
        return value

    def format_task_input(self, task_title: str, task_description: str) -> str:
        return task_title if not task_description else f"{task_title}\n{task_description}"

    async def cancel(self, task_id: int) -> None:
        return None

    async def explore_repo(self, workspace_path: Path, task_description: str, **kw) -> tuple[int, str]:
        self.explore_calls.append({"workspace_path": workspace_path, "task_description": task_description, **kw})
        return self.explore_exit_code, self._next(self.explore_output)

    async def generate_plan(self, workspace_path: Path, task_description: str, **kw) -> tuple[int, str]:
        return 0, "1. Do work"

    async def critique_plan(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        **kw,
    ) -> tuple[int, str]:
        return 0, self._next(self.critique_output)

    async def implement_plan(self, workspace_path: Path, plan_text: str, task_description: str, **kw) -> tuple[int, str]:
        return 0, self._next(self.implement_output)

    async def run_tests(self, workspace_path: Path, **kw) -> tuple[int, str]:
        return 0, self._next(self.test_output)

    async def review_result(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        test_output: str,
        diff_text: str,
        **kw,
    ) -> tuple[int, str]:
        return 0, self._next(self.review_output)

    async def orchestrate_next_action(self, workspace_path: Path, **kw) -> tuple[int, str]:
        self.orchestrate_calls.append({"workspace_path": workspace_path, **kw})
        return 0, self._next(self.orchestrate_output)

    async def generate_recovery_plan(
        self,
        workspace_path: Path,
        task_description: str,
        **kw,
    ) -> tuple[int, str]:
        self.recovery_calls.append({"workspace_path": workspace_path, "task_description": task_description, **kw})
        return 0, self._next(self.recovery_output)

    async def verify_completion(self, workspace_path: Path, **kw) -> tuple[int, str]:
        return 0, self._next(self.verify_output)


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
        self.last_session = None

    def __call__(self):
        self.last_session = FakeSession(self.task, self.repo, self.workspace)
        return self.last_session


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
    workspace_manager = FakeWorkspaceManager()
    engine = SymphonyWorkflowEngine(
        workspace_manager,
        FakeAgentRunner(),
        events,
        FakeSessionFactory(task, repo, workspace),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.AWAIT_MERGE_APPROVAL
    assert task.plan_text == "1. Do work"
    assert task.exploration_text == "SUMMARY: Repo entrypoints found."
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
    run_objects = [obj for obj in engine.session_factory.last_session.objects if isinstance(obj, Run)]
    assert [run.phase for run in run_objects] == [
        "explore",
        "plan",
        "critique",
        "implement",
        "test",
        "review",
        "verify",
    ]
    assert all(run.finished_at is not None for run in run_objects)
    assert all(run.exit_code == 0 for run in run_objects)
    assert workspace_manager.commits[-1][1] == "Task #1: Implement feature"


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
    assert "계획 검토가 수렴하지 않았습니다" in task.error_message


@pytest.mark.asyncio
async def test_workflow_engine_proceeds_to_testing_when_implementation_makes_no_changes():
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
        FakeAgentRunner(
            test_output="VERDICT: PASS\nSUMMARY: No changes needed.\nDETAILS:\nLooks good.",
            review_output="VERDICT: PASS\nSUMMARY: No changes needed.\nDETAILS:\nLooks good.",
        ),
        events,
        FakeSessionFactory(task, repo, workspace),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.AWAIT_MERGE_APPROVAL
    assert any("파일 변경을 만들지 않은 상태로 구현이 완료" in log for log in events.logs)
    assert any("병합 가능한 워크스페이스 변경이 남지 않았습니다" in log for log in events.logs)


@pytest.mark.asyncio
async def test_workflow_engine_uses_orchestrator_repair_loop_after_review_block():
    task = Task(
        id=1,
        repo_id=2,
        workspace_id=5,
        title="Implement feature",
        description="",
        status=TaskStatus.PENDING,
        retry_count=1,
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
    agent_runner = FakeAgentRunner(
        explore_output="SUMMARY: Use auth/service.py and tests/test_auth.py.",
        review_output=[
            "VERDICT: NEEDS_ATTENTION\nSUMMARY: Fix the edge case.\nDETAILS:\nBlocked.",
            "VERDICT: PASS\nSUMMARY: Ready for merge.\nDETAILS:\nLooks good.",
        ],
        orchestrate_output=[
            "ACTION: REPAIR\nSUMMARY: Keep the current plan.\nRATIONALE:\nApply a focused fix.",
        ],
    )
    engine = SymphonyWorkflowEngine(
        FakeWorkspaceManager(),
        agent_runner,
        events,
        FakeSessionFactory(task, repo, workspace),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.AWAIT_MERGE_APPROVAL
    assert any("오케스트레이터 판단 (review): REPAIR" in log for log in events.logs)
    assert agent_runner.orchestrate_calls[0]["exploration_text"] == "SUMMARY: Use auth/service.py and tests/test_auth.py."
    run_objects = [obj for obj in engine.session_factory.last_session.objects if isinstance(obj, Run)]
    assert [run.phase for run in run_objects].count("implement") == 2


@pytest.mark.asyncio
async def test_workflow_engine_uses_replan_path_after_test_block():
    task = Task(
        id=1,
        repo_id=2,
        workspace_id=5,
        title="Implement feature",
        description="",
        status=TaskStatus.PENDING,
        retry_count=0,
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
            test_output=[
                "VERDICT: NEEDS_ATTENTION\nSUMMARY: Test coverage failed.\nDETAILS:\nBlocked.",
                "VERDICT: PASS\nSUMMARY: Tests passed.\nDETAILS:\npytest ok.",
            ],
            orchestrate_output=[
                "ACTION: REPLAN\nSUMMARY: Rework the plan.\nRATIONALE:\nThe test failure shows the plan is incomplete.",
            ],
            recovery_output="1. Update the plan\n2. Add the missing test",
            critique_output=[
                "VERDICT: APPROVED\nSUMMARY: Plan looks good.\nPLAN:\n1. Do work",
                "VERDICT: APPROVED\nSUMMARY: Recovered plan looks good.\nPLAN:\n1. Update the plan\n2. Add the missing test",
            ],
        ),
        events,
        FakeSessionFactory(task, repo, workspace),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.AWAIT_MERGE_APPROVAL
    assert task.plan_text == "1. Update the plan\n2. Add the missing test"
    run_objects = [obj for obj in engine.session_factory.last_session.objects if isinstance(obj, Run)]
    assert [run.phase for run in run_objects].count("recover") == 1
    assert [run.phase for run in run_objects].count("implement") == 2


@pytest.mark.asyncio
async def test_workflow_engine_escalates_when_orchestrator_requests_it():
    task = Task(
        id=1,
        repo_id=2,
        workspace_id=5,
        title="Implement feature",
        description="",
        status=TaskStatus.PENDING,
        retry_count=0,
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
            test_output="VERDICT: NEEDS_ATTENTION\nSUMMARY: Cannot validate automatically.\nDETAILS:\nBlocked.",
            orchestrate_output="ACTION: ESCALATE\nSUMMARY: Human input required.\nRATIONALE:\nUnsafe to continue automatically.",
        ),
        events,
        FakeSessionFactory(task, repo, workspace),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.NEEDS_ATTENTION
    assert "오케스트레이터가 자동 진행을 중단했습니다" in (task.error_message or "")


@pytest.mark.asyncio
async def test_workflow_engine_rejects_finish_before_verify():
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
            review_output="VERDICT: NEEDS_ATTENTION\nSUMMARY: Review blocked.\nDETAILS:\nBlocked.",
            orchestrate_output="ACTION: FINISH\nSUMMARY: Stop now.\nRATIONALE:\nThis should only be allowed in verify.",
        ),
        events,
        FakeSessionFactory(task, repo, workspace),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.NEEDS_ATTENTION
    assert "FINISH는 최종 검증 단계에서만 허용됩니다" in (task.error_message or "")


@pytest.mark.asyncio
async def test_workflow_engine_moves_to_needs_attention_when_explore_fails():
    task = Task(
        id=1,
        repo_id=2,
        workspace_id=5,
        title="Implement feature",
        description="",
        status=TaskStatus.PENDING,
        retry_count=1,
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
        FakeAgentRunner(explore_exit_code=1, explore_output="explore failed"),
        events,
        FakeSessionFactory(task, repo, workspace),
    )

    await engine.process_task(1)

    assert task.status == TaskStatus.FAILED
    assert "탐색 실패" in (task.error_message or "")
