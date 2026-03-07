from types import SimpleNamespace

import pytest

from app.core.repo_service import RepoService
from app.models import TaskStatus


class FakeStore:
    def __init__(self, repo=None, task=None):
        self.repo = repo
        self.task = task
        self.deleted_repo = None
        self.main_workspace_created_for = None
        self.workspaces = []

    async def get_repo(self, db, repo_id: int):
        return self.repo

    async def find_repo_task(self, db, repo_id: int):
        return self.task

    async def create_repo(self, db, name: str, path: str, default_branch: str):
        self.repo = SimpleNamespace(id=1, name=name, path=path, default_branch=default_branch)
        return self.repo

    async def ensure_main_workspace(self, db, repo):
        self.main_workspace_created_for = repo

    async def list_workspaces(self, db, repo_id: int):
        return self.workspaces

    async def delete_workspace(self, db, workspace):
        self.workspaces.remove(workspace)

    async def delete_repo(self, db, repo):
        self.deleted_repo = repo


class FakeWorkspaceManager:
    def __init__(self):
        self.initialized = None
        self.cleaned_paths = []

    async def ensure_repository(self, repo_path, default_branch: str):
        self.initialized = (repo_path, default_branch)

    async def cleanup_worktree(self, repo_path, workspace_path):
        self.cleaned_paths.append((repo_path, workspace_path))


@pytest.mark.asyncio
async def test_create_repo_initializes_main_workspace(tmp_path):
    service = RepoService(FakeStore(), workspace_manager=FakeWorkspaceManager())

    repo = await service.create_repo(
        db=None,
        name="demo",
        path=str(tmp_path),
        default_branch="main",
    )

    assert repo.name == "demo"
    assert service.store.main_workspace_created_for is repo


@pytest.mark.asyncio
async def test_delete_repo_removes_registration_when_repo_has_no_tasks():
    repo = SimpleNamespace(id=1, name="demo", path="D:/repo")
    store = FakeStore(repo=repo)
    service = RepoService(store, workspace_manager=FakeWorkspaceManager())

    await service.delete_repo(db=None, repo_id=1)

    assert service.store.deleted_repo is repo


@pytest.mark.asyncio
async def test_delete_repo_rejects_registered_repo_with_tasks():
    repo = SimpleNamespace(id=1, name="demo", path="D:/repo")
    task = (7, "Build dashboard", TaskStatus.IMPLEMENTING)
    service = RepoService(FakeStore(repo=repo, task=task), workspace_manager=FakeWorkspaceManager())

    with pytest.raises(ValueError, match="Cannot delete repo while task #7"):
        await service.delete_repo(db=None, repo_id=1)


@pytest.mark.asyncio
async def test_delete_repo_raises_when_repo_is_missing():
    service = RepoService(FakeStore(repo=None), workspace_manager=None)

    with pytest.raises(LookupError, match="Repo not found"):
        await service.delete_repo(db=None, repo_id=1)
