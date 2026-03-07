from __future__ import annotations

from pathlib import Path

from app.core.contracts import AgentRunner, EventSink, WorkspaceManager
from app.models import Repo, Run, Task, TaskStatus, Workspace


class SymphonyWorkflowEngine:
    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        agent_runner: AgentRunner,
        event_sink: EventSink,
        session_factory,
    ):
        self.git = workspace_manager
        self.codex = agent_runner
        self.events = event_sink
        self.session_factory = session_factory
        self.worker_pool = None

    def set_worker_pool(self, pool):
        self.worker_pool = pool

    async def _update_status(self, session, task, new_status: TaskStatus):
        old = task.status
        task.status = new_status
        await session.commit()
        await self.events.broadcast_state_change(task.id, old.value, new_status.value)
        await self.events.log(task.id, f"Status: {old.value} -> {new_status.value}")

    async def process_task(self, task_id: int):
        async with self.session_factory() as session:
            task = await session.get(Task, task_id)
            repo = await session.get(Repo, task.repo_id)
            workspace = await session.get(Workspace, task.workspace_id) if task.workspace_id else None

            try:
                task_input = self.codex.format_task_input(task.title, task.description)

                if task.status == TaskStatus.PENDING:
                    await self._update_status(session, task, TaskStatus.PREPARING_WORKSPACE)
                    if workspace is None:
                        raise RuntimeError("Workspace not found for task")

                    workspace_path = Path(workspace.workspace_path) if workspace.workspace_path else None
                    if workspace_path is None or not workspace_path.exists():
                        workspace_path = await self.git.create_worktree(
                            Path(repo.path),
                            workspace.branch_name,
                            workspace.id,
                            repo.id,
                            repo.name,
                            workspace.name,
                            workspace.base_branch,
                        )
                        workspace.workspace_path = str(workspace_path)
                    task.workspace_path = str(workspace_path)
                    task.branch_name = workspace.branch_name
                    await session.commit()

                    await self._update_status(session, task, TaskStatus.PLANNING)
                    log_cb = lambda line: self.events.log(task.id, line)  # noqa: E731
                    exit_code, output = await self.codex.generate_plan(
                        Path(task.workspace_path),
                        task_input,
                        log_callback=log_cb,
                        task_id=task.id,
                    )
                    run = Run(
                        task_id=task.id,
                        phase="plan",
                        exit_code=exit_code,
                        log_path=str(self.events.get_log_path(task.id)),
                    )
                    session.add(run)
                    if exit_code != 0:
                        raise RuntimeError(f"Plan generation failed: {output[-500:]}")
                    task.plan_text = output
                    await session.commit()

                    await self._update_status(session, task, TaskStatus.AWAIT_PLAN_APPROVAL)
                    return

                if task.status == TaskStatus.IMPLEMENTING:
                    log_cb = lambda line: self.events.log(task.id, line)  # noqa: E731
                    exit_code, output = await self.codex.implement_plan(
                        Path(task.workspace_path),
                        task.plan_text,
                        task_input,
                        log_callback=log_cb,
                        task_id=task.id,
                    )
                    run = Run(
                        task_id=task.id,
                        phase="implement",
                        exit_code=exit_code,
                        log_path=str(self.events.get_log_path(task.id)),
                    )
                    session.add(run)
                    if exit_code != 0:
                        raise RuntimeError(f"Implementation failed: {output[-500:]}")

                    await self._update_status(session, task, TaskStatus.TESTING)
                    exit_code, output = await self.codex.run_tests(
                        Path(task.workspace_path),
                        log_callback=log_cb,
                        task_id=task.id,
                    )
                    run = Run(
                        task_id=task.id,
                        phase="test",
                        exit_code=exit_code,
                        log_path=str(self.events.get_log_path(task.id)),
                    )
                    session.add(run)

                    task.diff_text = await self.git.get_diff(
                        Path(task.workspace_path), workspace.base_branch if workspace else repo.default_branch
                    )
                    await session.commit()

                    await self._update_status(session, task, TaskStatus.AWAIT_MERGE_APPROVAL)
                    return

                if task.status == TaskStatus.MERGING:
                    await self.events.log(task.id, "Merging to main...")
                    success, msg = await self.git.merge_to_main(
                        Path(repo.path),
                        workspace.branch_name if workspace else task.branch_name,
                        workspace.base_branch if workspace else repo.default_branch,
                    )
                    run = Run(
                        task_id=task.id,
                        phase="merge",
                        exit_code=0 if success else 1,
                        log_path=str(self.events.get_log_path(task.id)),
                    )
                    session.add(run)
                    if not success:
                        raise RuntimeError(f"Merge failed: {msg}")
                    await self._update_status(session, task, TaskStatus.DONE)

            except Exception as exc:
                await self.events.log(task.id, f"ERROR: {exc}")
                task.error_message = str(exc)
                if task.retry_count < 1:
                    task.retry_count += 1
                    task.status = TaskStatus.PENDING
                    await session.commit()
                    if self.worker_pool:
                        await self.worker_pool.enqueue(task.id)
                else:
                    await self._update_status(session, task, TaskStatus.FAILED)
