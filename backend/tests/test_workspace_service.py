from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.workspace_service import WorkspaceService
from app.models import WorkspaceKind


class FakeStore:
    def __init__(self):
        self.repo = SimpleNamespace(id=1, path="D:/repo")
        self.main_workspace = SimpleNamespace(
            id=10,
            repo_id=1,
            name="Main",
            kind=WorkspaceKind.MAIN,
            task_count=0,
            workspace_path=None,
        )
        self.empty_feature_workspace = SimpleNamespace(
            id=11,
            repo_id=1,
            name="Feature A",
            kind=WorkspaceKind.FEATURE,
            task_count=0,
            workspace_path="D:/workspaces/repo-1/workspace-11-feature-a",
        )
        self.active_feature_workspace = SimpleNamespace(
            id=12,
            repo_id=1,
            name="Feature B",
            kind=WorkspaceKind.FEATURE,
            task_count=1,
            workspace_path="D:/workspaces/repo-1/workspace-12-feature-b",
        )
        self.deleted = []

    async def get_repo(self, db, repo_id: int):
        return self.repo if repo_id == self.repo.id else None

    async def list_workspaces(self, db, repo_id: int):
        workspaces = [
            self.main_workspace,
            self.empty_feature_workspace,
            self.active_feature_workspace,
        ]
        return [workspace for workspace in workspaces if workspace not in self.deleted]

    async def delete_workspace(self, db, workspace):
        self.deleted.append(workspace)


class FakeWorkspaceManager:
    def __init__(self):
        self.cleaned = []

    async def cleanup_worktree(self, repo_path: Path, workspace_path: Path):
        self.cleaned.append((repo_path, workspace_path))


@pytest.mark.asyncio
async def test_list_workspaces_prunes_empty_feature_workspaces():
    store = FakeStore()
    workspace_manager = FakeWorkspaceManager()
    service = WorkspaceService(store, workspace_manager)

    workspaces = await service.list_workspaces(db=None, repo_id=1)

    assert [workspace.id for workspace in workspaces] == [10, 12]
    assert store.deleted == [store.empty_feature_workspace]
    assert workspace_manager.cleaned == [
        (Path("D:/repo"), Path("D:/workspaces/repo-1/workspace-11-feature-a"))
    ]
