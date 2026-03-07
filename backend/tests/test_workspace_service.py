from types import SimpleNamespace

import pytest

from app.core.workspace_service import WorkspaceService
from app.models import WorkspaceKind


class FakeStore:
    def __init__(self):
        self.repo = SimpleNamespace(id=1, default_branch="main", path="D:/repo")
        self.workspace = SimpleNamespace(
            id=2,
            repo_id=1,
            name="Feature",
            kind=WorkspaceKind.FEATURE,
            workspace_path="D:/workspaces/repo-1/workspace-2-feature",
        )
        self.deleted_workspace = None

    async def get_repo(self, db, repo_id: int):
        return self.repo if repo_id == 1 else None

    async def list_workspaces(self, db, repo_id: int):
        return [self.workspace]

    async def create_workspace(self, db, *, repo_id: int, name: str, kind, base_branch: str):
        return self.workspace

    async def get_workspace(self, db, workspace_id: int):
        return self.workspace if workspace_id == 2 else None

    async def count_workspace_tasks(self, db, workspace_id: int):
        return 0

    async def delete_workspace(self, db, workspace):
        self.deleted_workspace = workspace


class FakeWorkspaceManager:
    def __init__(self):
        self.cleaned = []

    async def cleanup_worktree(self, repo_path, workspace_path):
        self.cleaned.append((repo_path, workspace_path))


@pytest.mark.asyncio
async def test_list_workspaces_requires_repo():
    service = WorkspaceService(FakeStore(), FakeWorkspaceManager())

    workspaces = await service.list_workspaces(None, 1)

    assert len(workspaces) == 1


@pytest.mark.asyncio
async def test_delete_workspace_rejects_main_workspace():
    store = FakeStore()
    store.workspace.kind = WorkspaceKind.MAIN
    service = WorkspaceService(store, FakeWorkspaceManager())

    with pytest.raises(ValueError, match="Main workspace cannot be deleted"):
        await service.delete_workspace(None, 2)
