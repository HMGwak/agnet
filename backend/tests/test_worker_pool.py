from datetime import datetime, timedelta

import pytest

from app.models import Task, TaskStatus
from app.services.worker import WorkerPool


class DummyOrchestrator:
    pass


class FakeSession:
    def __init__(self, dependency: Task | None = None):
        self.dependency = dependency

    async def get(self, model, task_id):
        return self.dependency


@pytest.mark.asyncio
async def test_pending_task_waits_for_future_schedule():
    pool = WorkerPool(DummyOrchestrator())
    task = Task(
        repo_id=1,
        title="scheduled",
        status=TaskStatus.PENDING,
        scheduled_for=datetime.now() + timedelta(minutes=10),
    )

    ready = await pool._is_task_ready(FakeSession(), task)

    assert ready is False


@pytest.mark.asyncio
async def test_pending_task_waits_for_dependency_until_done():
    pool = WorkerPool(DummyOrchestrator())
    dependency = Task(repo_id=1, title="first", status=TaskStatus.IMPLEMENTING)
    task = Task(
        repo_id=1,
        title="second",
        status=TaskStatus.PENDING,
        blocked_by_task_id=7,
    )

    ready = await pool._is_task_ready(FakeSession(dependency), task)

    assert ready is False


@pytest.mark.asyncio
async def test_pending_task_runs_after_dependency_done():
    pool = WorkerPool(DummyOrchestrator())
    dependency = Task(repo_id=1, title="first", status=TaskStatus.DONE)
    task = Task(
        repo_id=1,
        title="second",
        status=TaskStatus.PENDING,
        blocked_by_task_id=7,
    )

    ready = await pool._is_task_ready(FakeSession(dependency), task)

    assert ready is True
