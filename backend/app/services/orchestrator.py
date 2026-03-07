from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.models import Repo, Run, Task, TaskStatus

if TYPE_CHECKING:
    from app.api.websocket import WebSocketManager
    from app.services.codex_agent import CodexAgent
    from app.services.git_manager import GitManager
    from app.services.logger import TaskLogger
    from app.services.worker import WorkerPool


class Orchestrator:
    def __init__(
        self,
        git_manager: GitManager,
        codex_agent: CodexAgent,
        task_logger: TaskLogger,
        ws_manager: WebSocketManager,
        session_factory,
    ):
        self.git = git_manager
        self.codex = codex_agent
        self.logger = task_logger
        self.ws = ws_manager
        self.session_factory = session_factory
        self.worker_pool: WorkerPool | None = None

    def set_worker_pool(self, pool: WorkerPool):
        self.worker_pool = pool

    async def _update_status(self, session, task, new_status: TaskStatus):
        old = task.status
        task.status = new_status
        await session.commit()
        await self.ws.broadcast_state_change(task.id, old.value, new_status.value)
        await self.logger.log(task.id, f"Status: {old.value} -> {new_status.value}")

    async def process_task(self, task_id: int):
        async with self.session_factory() as session:
            task = await session.get(Task, task_id)
            repo = await session.get(Repo, task.repo_id)

            try:
                task_input = self.codex.format_task_input(task.title, task.description)

                # Phase A: PENDING -> AWAIT_PLAN_APPROVAL
                if task.status == TaskStatus.PENDING:
                    await self._update_status(session, task, TaskStatus.PREPARING_WORKSPACE)
                    workspace = await self.git.create_worktree(
                        Path(repo.path), task.branch_name, task.id
                    )
                    task.workspace_path = str(workspace)
                    await session.commit()

                    await self._update_status(session, task, TaskStatus.PLANNING)
                    log_cb = lambda line: self.logger.log(task.id, line)  # noqa: E731
                    exit_code, output = await self.codex.generate_plan(
                        Path(task.workspace_path), task_input,
                        log_callback=log_cb, task_id=task.id,
                    )
                    run = Run(
                        task_id=task.id, phase="plan", exit_code=exit_code,
                        log_path=str(self.logger.get_log_path(task.id)),
                    )
                    session.add(run)
                    if exit_code != 0:
                        raise RuntimeError(f"Plan generation failed: {output[-500:]}")
                    task.plan_text = output
                    await session.commit()

                    await self._update_status(session, task, TaskStatus.AWAIT_PLAN_APPROVAL)
                    return

                # Phase B: IMPLEMENTING -> AWAIT_MERGE_APPROVAL
                if task.status == TaskStatus.IMPLEMENTING:
                    log_cb = lambda line: self.logger.log(task.id, line)  # noqa: E731
                    exit_code, output = await self.codex.implement_plan(
                        Path(task.workspace_path), task.plan_text,
                        task_input, log_callback=log_cb, task_id=task.id,
                    )
                    run = Run(
                        task_id=task.id, phase="implement", exit_code=exit_code,
                        log_path=str(self.logger.get_log_path(task.id)),
                    )
                    session.add(run)
                    if exit_code != 0:
                        raise RuntimeError(f"Implementation failed: {output[-500:]}")

                    await self._update_status(session, task, TaskStatus.TESTING)
                    exit_code, output = await self.codex.run_tests(
                        Path(task.workspace_path), log_callback=log_cb, task_id=task.id,
                    )
                    run = Run(
                        task_id=task.id, phase="test", exit_code=exit_code,
                        log_path=str(self.logger.get_log_path(task.id)),
                    )
                    session.add(run)

                    task.diff_text = await self.git.get_diff(
                        Path(task.workspace_path), repo.default_branch
                    )
                    await session.commit()

                    await self._update_status(session, task, TaskStatus.AWAIT_MERGE_APPROVAL)
                    return

                # Phase C: MERGING -> DONE
                if task.status == TaskStatus.MERGING:
                    await self.logger.log(task.id, "Merging to main...")
                    success, msg = await self.git.merge_to_main(
                        Path(repo.path), task.branch_name
                    )
                    run = Run(
                        task_id=task.id, phase="merge",
                        exit_code=0 if success else 1,
                        log_path=str(self.logger.get_log_path(task.id)),
                    )
                    session.add(run)
                    if not success:
                        raise RuntimeError(f"Merge failed: {msg}")
                    await self.git.cleanup_worktree(
                        Path(repo.path), Path(task.workspace_path)
                    )
                    await self._update_status(session, task, TaskStatus.DONE)

            except Exception as e:
                await self.logger.log(task.id, f"ERROR: {e}")
                task.error_message = str(e)
                if task.retry_count < 1:
                    task.retry_count += 1
                    task.status = TaskStatus.PENDING
                    await session.commit()
                    if self.worker_pool:
                        await self.worker_pool.enqueue(task.id)
                else:
                    await self._update_status(session, task, TaskStatus.FAILED)
