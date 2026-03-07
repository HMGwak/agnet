from __future__ import annotations

from pathlib import Path

from app.adapters.sqlite_store import SQLiteStore


class RepoService:
    def __init__(self, store: SQLiteStore, workspace_manager):
        self.store = store
        self.workspace_manager = workspace_manager

    async def create_repo(self, db, name: str, path: str, default_branch: str):
        repo_path = Path(path)
        if not repo_path.is_dir():
            raise ValueError("Path does not exist or is not a directory")

        if not (repo_path / ".git").exists():
            await self.workspace_manager.ensure_repository(repo_path, default_branch)

        return await self.store.create_repo(db, name, str(repo_path), default_branch)

    async def list_repos(self, db):
        return await self.store.list_repos(db)

    async def get_repo(self, db, repo_id: int):
        return await self.store.get_repo(db, repo_id)

    async def delete_repo(self, db, repo_id: int) -> None:
        repo = await self.store.get_repo(db, repo_id)
        if repo is None:
            raise LookupError("Repo not found")

        task = await self.store.find_repo_task(db, repo_id)
        if task is not None:
            task_id, title, status = task
            raise ValueError(
                f"Cannot delete repo while task #{task_id} ({title}) is still registered with status {status.value}"
            )

        await self.store.delete_repo(db, repo)
