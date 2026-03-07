from __future__ import annotations

from pathlib import Path

from app.adapters.sqlite_store import SQLiteStore
from app.models import WorkspaceKind


class WorkspaceService:
    def __init__(self, store: SQLiteStore, workspace_manager):
        self.store = store
        self.workspace_manager = workspace_manager

    async def list_workspaces(self, db, repo_id: int):
        repo = await self.store.get_repo(db, repo_id)
        if repo is None:
            raise LookupError("Repo not found")
        return await self.store.list_workspaces(db, repo_id)

    async def create_workspace(self, db, repo_id: int, name: str):
        repo = await self.store.get_repo(db, repo_id)
        if repo is None:
            raise LookupError("Repo not found")
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Workspace name cannot be empty")
        return await self.store.create_workspace(
            db,
            repo_id=repo_id,
            name=cleaned_name,
            kind=WorkspaceKind.FEATURE,
            base_branch=repo.default_branch,
        )

    async def delete_workspace(self, db, workspace_id: int):
        workspace = await self.store.get_workspace(db, workspace_id)
        if workspace is None:
            raise LookupError("Workspace not found")
        if workspace.kind == WorkspaceKind.MAIN:
            raise ValueError("Main workspace cannot be deleted")

        task_count = await self.store.count_workspace_tasks(db, workspace_id)
        if task_count > 0:
            raise ValueError("Workspace still has tasks. Delete or move them first.")

        repo = await self.store.get_repo(db, workspace.repo_id)
        if workspace.workspace_path and repo:
            try:
                await self.workspace_manager.cleanup_worktree(
                    Path(repo.path),
                    Path(workspace.workspace_path),
                )
            except Exception:
                pass
        await self.store.delete_workspace(db, workspace)
