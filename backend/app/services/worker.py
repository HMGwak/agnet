from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.policies import is_task_ready
from app.models import Repo, Task, TaskStatus, Workspace

if TYPE_CHECKING:
    from app.services.orchestrator import Orchestrator


class WorkerPool:
    def __init__(self, orchestrator: Orchestrator, max_concurrent: int = 6):
        self.orchestrator = orchestrator
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.repo_locks: dict[int, asyncio.Lock] = {}
        self.queue: asyncio.Queue[int] = asyncio.Queue()
        self.queued_task_ids: set[int] = set()
        self._running = False
        self._workers: list[asyncio.Task] = []
        self._scheduler: asyncio.Task | None = None
        self._session_factory = None

    def get_repo_lock(self, repo_id: int) -> asyncio.Lock:
        if repo_id not in self.repo_locks:
            self.repo_locks[repo_id] = asyncio.Lock()
        return self.repo_locks[repo_id]

    async def enqueue(self, task_id: int):
        if task_id in self.queued_task_ids:
            return
        self.queued_task_ids.add(task_id)
        await self.queue.put(task_id)

    async def _is_task_ready(self, session, task: Task) -> bool:
        return await is_task_ready(session, task)

    async def start(self, session_factory):
        self._running = True
        self._session_factory = session_factory

        git_mgr = self.orchestrator.git
        async with session_factory() as session:
            stuck_statuses = [
                TaskStatus.PREPARING_WORKSPACE,
                TaskStatus.PLANNING,
                TaskStatus.IMPLEMENTING,
                TaskStatus.TESTING,
                TaskStatus.MERGING,
            ]
            result = await session.execute(
                select(Task).where(Task.status.in_(stuck_statuses))
            )
            for task in result.scalars():
                if task.workspace_path:
                    repo = await session.get(Repo, task.repo_id)
                    workspace = await session.get(Workspace, task.workspace_id) if task.workspace_id else None
                    try:
                        await git_mgr.cleanup_worktree(
                            Path(repo.path), Path(task.workspace_path)
                        )
                    except Exception:
                        pass
                    if workspace is not None:
                        workspace.workspace_path = None
                    task.workspace_path = None
                task.status = TaskStatus.PENDING
                task.retry_count = 0
            await session.commit()

            result = await session.execute(
                select(Task).where(Task.status == TaskStatus.PENDING)
            )
            for task in result.scalars():
                if await self._is_task_ready(session, task):
                    await self.enqueue(task.id)

        self._workers = [
            asyncio.create_task(self._worker_loop()) for _ in range(12)
        ]
        self._scheduler = asyncio.create_task(self._scheduler_loop())

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()
        if self._scheduler:
            self._scheduler.cancel()

    async def _scheduler_loop(self):
        while self._running:
            await asyncio.sleep(5)
            async with self._session_factory() as session:
                result = await session.execute(
                    select(Task).where(Task.status == TaskStatus.PENDING)
                )
                for task in result.scalars():
                    if await self._is_task_ready(session, task):
                        await self.enqueue(task.id)

    async def _worker_loop(self):
        while self._running:
            task_id = await self.queue.get()
            self.queued_task_ids.discard(task_id)
            async with self.semaphore:
                async with self._session_factory() as session:
                    task = await session.get(Task, task_id)
                    if not task or task.status in (
                        TaskStatus.DONE,
                        TaskStatus.FAILED,
                        TaskStatus.NEEDS_ATTENTION,
                        TaskStatus.CANCELLED,
                    ):
                        continue
                    if not await self._is_task_ready(session, task):
                        continue
                    repo_id = task.repo_id

                repo_lock = self.get_repo_lock(repo_id)
                async with repo_lock:
                    try:
                        await self.orchestrator.process_task(task_id)
                    except Exception as e:
                        print(f"Worker error for task {task_id}: {e}")
