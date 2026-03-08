from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.project_policy import ProjectPolicy
from app.core.task_commands import TaskCommandService
from app.models import TaskStatus, WorkspaceKind


class FakeStore:
    def __init__(self):
        self.repo = SimpleNamespace(id=1, default_branch="main", path="D:/repo")
        self.main_workspace = SimpleNamespace(
            id=10,
            repo_id=1,
            name="Main",
            kind=WorkspaceKind.MAIN,
            branch_name="workspace/main/1",
            workspace_path=None,
        )
        self.feature_workspace = SimpleNamespace(
            id=11,
            repo_id=1,
            name="Feature",
            kind=WorkspaceKind.FEATURE,
            branch_name="workspace/11/feature",
            workspace_path="D:/workspaces/repo-1/workspace-11-feature",
        )
        self.created_task = None
        self.deleted_workspace = None
        self.created_workspace_names = []

    async def get_repo(self, db, repo_id: int):
        return self.repo if repo_id == self.repo.id else None

    async def get_task(self, db, task_id: int):
        return None

    async def get_workspace(self, db, workspace_id: int):
        if workspace_id == self.main_workspace.id:
            return self.main_workspace
        if workspace_id == self.feature_workspace.id:
            return self.feature_workspace
        return None

    async def ensure_main_workspace(self, db, repo):
        return self.main_workspace

    async def create_workspace(self, db, *, repo_id: int, name: str, kind, base_branch: str):
        self.created_workspace_names.append(name)
        return self.feature_workspace

    async def create_task(self, db, **kwargs):
        self.created_task = SimpleNamespace(
            id=5,
            blocked_by_title=None,
            workspace_name=None,
            workspace_kind=None,
            workspace_task_count=0,
            **kwargs,
        )
        return self.created_task

    async def count_workspace_tasks(self, db, workspace_id: int) -> int:
        return 1

    async def find_dependent_task(self, db, task_id: int):
        return None

    async def delete_task_records(self, db, task_id: int):
        return None

    async def delete_workspace(self, db, workspace):
        self.deleted_workspace = workspace


class FakeWorkflow:
    def __init__(self):
        self.codex = SimpleNamespace(cancel=self.cancel)
        self.git = SimpleNamespace(cleanup_worktree=self.cleanup_worktree)
        self.cancelled = []
        self.cleaned = []

    async def cancel(self, task_id: int):
        self.cancelled.append(task_id)

    async def cleanup_worktree(self, repo_path: Path, workspace_path: Path):
        self.cleaned.append((repo_path, workspace_path))


class FakeEvents:
    async def log(self, task_id: int, line: str):
        return None

    async def broadcast_state_change(self, task_id: int, old_status: str, new_status: str):
        return None

    async def broadcast_task_deleted(self, task_id: int):
        return None


class FakeWorkerPool:
    def __init__(self):
        self.enqueued = []

    async def enqueue(self, task_id: int):
        self.enqueued.append(task_id)


class FakeDB:
    def __init__(self):
        self.deleted = []

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None


def make_policy():
    return ProjectPolicy(
        plan_required=True,
        critique_required=True,
        critique_max_rounds=2,
        test_fix_loops=2,
        review_required=True,
        merge_human_approval=True,
        allow_user_override=False,
        allow_repo_override=False,
        main_allow_feature_work=False,
        main_allow_hotfix=True,
        main_allow_plan_review=True,
        auto_fork_feature_workspace_from_main=True,
        hotfix_keywords=("fix", "bug", "patch"),
        plan_review_keywords=("plan", "review", "triage"),
    )


@pytest.mark.asyncio
async def test_create_task_defaults_to_main_workspace():
    store = FakeStore()
    worker_pool = FakeWorkerPool()
    service = TaskCommandService(store, FakeWorkflow(), FakeEvents(), worker_pool, make_policy())

    task = await service.create_task(
        FakeDB(),
        repo_id=1,
        title="Build Tetris",
        description="",
        scheduled_for=None,
        blocked_by_task_id=None,
        workspace_id=None,
        create_workspace=None,
    )

    assert task.workspace_id == 11
    assert task.branch_name == "workspace/11/feature"
    assert worker_pool.enqueued == [5]


@pytest.mark.asyncio
async def test_create_task_uses_existing_workspace():
    store = FakeStore()
    worker_pool = FakeWorkerPool()
    service = TaskCommandService(store, FakeWorkflow(), FakeEvents(), worker_pool, make_policy())

    task = await service.create_task(
        FakeDB(),
        repo_id=1,
        title="Build Tetris",
        description="",
        scheduled_for=None,
        blocked_by_task_id=None,
        workspace_id=11,
        create_workspace=None,
    )

    assert task.workspace_id == 11
    assert task.branch_name == "workspace/11/feature"


@pytest.mark.asyncio
async def test_create_task_keeps_hotfix_on_main_workspace():
    store = FakeStore()
    worker_pool = FakeWorkerPool()
    service = TaskCommandService(store, FakeWorkflow(), FakeEvents(), worker_pool, make_policy())

    task = await service.create_task(
        FakeDB(),
        repo_id=1,
        title="Fix regression in queue ordering",
        description="Patch the queue sorting bug.",
        scheduled_for=None,
        blocked_by_task_id=None,
        workspace_id=None,
        create_workspace=None,
    )

    assert task.workspace_id == 10
    assert store.created_workspace_names == []


@pytest.mark.asyncio
async def test_delete_task_can_delete_empty_feature_workspace():
    store = FakeStore()
    workflow = FakeWorkflow()
    service = TaskCommandService(store, workflow, FakeEvents(), FakeWorkerPool(), make_policy())
    db = FakeDB()
    task = SimpleNamespace(
        id=7,
        repo_id=1,
        workspace_id=11,
        status=TaskStatus.CANCELLED,
    )

    async def get_task(db, task_id: int):
        return task

    async def count_workspace_tasks(db, workspace_id: int) -> int:
        return 0

    store.get_task = get_task
    store.count_workspace_tasks = count_workspace_tasks

    await service.delete_task(
        db,
        task_id=7,
        delete_workspace_if_empty=True,
    )

    assert db.deleted == [task]
    assert store.deleted_workspace is store.feature_workspace
