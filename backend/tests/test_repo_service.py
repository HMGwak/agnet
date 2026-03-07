from types import SimpleNamespace

import pytest

from app.core.repo_service import RepoService
from app.models import TaskStatus


class FakeStore:
    def __init__(self, repo=None, task=None):
        self.repo = repo
        self.task = task
        self.deleted_repo = None

    async def get_repo(self, db, repo_id: int):
        return self.repo

    async def find_repo_task(self, db, repo_id: int):
        return self.task

    async def delete_repo(self, db, repo):
        self.deleted_repo = repo


@pytest.mark.asyncio
async def test_delete_repo_removes_registration_when_repo_has_no_tasks():
    repo = SimpleNamespace(id=1, name="demo")
    service = RepoService(FakeStore(repo=repo), workspace_manager=None)

    await service.delete_repo(db=None, repo_id=1)

    assert service.store.deleted_repo is repo


@pytest.mark.asyncio
async def test_delete_repo_rejects_registered_repo_with_tasks():
    repo = SimpleNamespace(id=1, name="demo")
    task = (7, "Build dashboard", TaskStatus.IMPLEMENTING)
    service = RepoService(FakeStore(repo=repo, task=task), workspace_manager=None)

    with pytest.raises(ValueError, match="Cannot delete repo while task #7"):
        await service.delete_repo(db=None, repo_id=1)


@pytest.mark.asyncio
async def test_delete_repo_raises_when_repo_is_missing():
    service = RepoService(FakeStore(repo=None), workspace_manager=None)

    with pytest.raises(LookupError, match="Repo not found"):
        await service.delete_repo(db=None, repo_id=1)
