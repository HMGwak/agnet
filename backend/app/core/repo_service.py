from __future__ import annotations

from pathlib import Path

from app.adapters.sqlite_store import SQLiteStore
from app.core.repo_profile import ensure_repo_profile_file
from app.schemas import RepoProfileDraft


class RepoService:
    def __init__(self, store: SQLiteStore, workspace_manager):
        self.store = store
        self.workspace_manager = workspace_manager

    async def create_repo(
        self,
        db,
        name: str,
        path: str,
        default_branch: str,
        create_if_missing: bool = False,
        profile: RepoProfileDraft | None = None,
    ):
        repo_name = name.strip()
        repo_path = self._resolve_repo_path(repo_name, Path(path), create_if_missing)
        if not repo_path.is_dir():
            if create_if_missing:
                repo_path.mkdir(parents=True, exist_ok=True)
            else:
                raise ValueError("Path does not exist or is not a directory")

        if not (repo_path / ".git").exists():
            await self.workspace_manager.ensure_repository(repo_path, default_branch)
            ensure_repo_profile_file(repo_path)

        repo = await self.store.create_repo(db, name, str(repo_path), default_branch)
        try:
            await self.store.ensure_main_workspace(db, repo)
        except Exception:
            await self.store.delete_repo(db, repo)
            raise
        return repo

    @staticmethod
    def _resolve_repo_path(name: str, requested_path: Path, create_if_missing: bool) -> Path:
        if not create_if_missing:
            return requested_path
        if not requested_path.exists():
            return requested_path
        if not requested_path.is_dir():
            return requested_path
        if requested_path.name.strip().casefold() == name.strip().casefold():
            return requested_path
        return requested_path / name

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

        workspaces = await self.store.list_workspaces(db, repo_id)
        for workspace in workspaces:
            if workspace.workspace_path:
                try:
                    await self.workspace_manager.cleanup_worktree(
                        Path(repo.path),
                        Path(workspace.workspace_path),
                    )
                except Exception:
                    pass
            await self.store.delete_workspace(db, workspace)

        await self.store.delete_repo(db, repo)
