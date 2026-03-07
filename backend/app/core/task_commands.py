from __future__ import annotations

from pathlib import Path

from app.adapters.sqlite_store import SQLiteStore
from app.core.policies import append_follow_up_instructions
from app.models import TaskStatus


class TaskCommandService:
    def __init__(self, store: SQLiteStore, workflow, event_sink, worker_pool):
        self.store = store
        self.workflow = workflow
        self.events = event_sink
        self.worker_pool = worker_pool

    async def create_task(
        self,
        db,
        repo_id: int,
        title: str,
        description: str,
        scheduled_for,
        blocked_by_task_id,
    ):
        repo = await self.store.get_repo(db, repo_id)
        if not repo:
            raise ValueError("Repo not found")

        dependency_task = None
        if blocked_by_task_id is not None:
            dependency_task = await self.store.get_task(db, blocked_by_task_id)
            if not dependency_task:
                raise LookupError("Dependency task not found")
            if dependency_task.repo_id != repo_id:
                raise ValueError("Dependency task must belong to the same repository")

        task = await self.store.create_task(
            db,
            repo_id=repo_id,
            title=title,
            description=description,
            scheduled_for=scheduled_for,
            blocked_by_task_id=blocked_by_task_id,
        )
        task.blocked_by_title = dependency_task.title if dependency_task else None
        await self.worker_pool.enqueue(task.id)
        return task

    async def approve_plan(self, db, task_id: int, decision: str, comment: str):
        task = await self.store.get_task(db, task_id)
        if not task:
            raise LookupError("Task not found")
        if task.status != TaskStatus.AWAIT_PLAN_APPROVAL:
            raise ValueError(f"Task status is {task.status}, expected AWAIT_PLAN_APPROVAL")

        approval = await self.store.create_approval(db, task_id, "plan", decision, comment)
        if decision == "approved":
            await self._commit_status_change(db, task, TaskStatus.IMPLEMENTING)
            await self.worker_pool.enqueue(task.id)
        elif decision == "rejected":
            task.error_message = f"Plan rejected: {comment}"
            await self._commit_status_change(db, task, TaskStatus.NEEDS_ATTENTION)
        await db.refresh(approval)
        return approval

    async def approve_merge(self, db, task_id: int, decision: str, comment: str):
        task = await self.store.get_task(db, task_id)
        if not task:
            raise LookupError("Task not found")
        if task.status != TaskStatus.AWAIT_MERGE_APPROVAL:
            raise ValueError(f"Task status is {task.status}, expected AWAIT_MERGE_APPROVAL")

        approval = await self.store.create_approval(db, task_id, "merge", decision, comment)
        if decision == "approved":
            await self._commit_status_change(db, task, TaskStatus.MERGING)
            await self.worker_pool.enqueue(task.id)
        elif decision == "rejected":
            task.error_message = f"Merge rejected: {comment}"
            await self._commit_status_change(db, task, TaskStatus.NEEDS_ATTENTION)
        await db.refresh(approval)
        return approval

    async def cancel_task(self, db, task_id: int):
        task = await self.store.get_task(db, task_id)
        if not task:
            raise LookupError("Task not found")
        if task.status == TaskStatus.DONE:
            raise ValueError("Cannot cancel a completed task")

        await self.workflow.codex.cancel(task_id)
        if task.status != TaskStatus.CANCELLED:
            await self._commit_status_change(db, task, TaskStatus.CANCELLED)
        else:
            await db.refresh(task)
        await self.store.attach_task_metadata(db, [task])
        return task

    async def resume_task(self, db, task_id: int, comment: str):
        task = await self.store.get_task(db, task_id)
        if not task:
            raise LookupError("Task not found")
        if task.status == TaskStatus.DONE:
            raise ValueError("Cannot requeue a completed task")
        if task.status not in (
            TaskStatus.NEEDS_ATTENTION,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ):
            raise ValueError(
                f"Task status is {task.status}, expected NEEDS_ATTENTION, FAILED, or CANCELLED"
            )

        repo = await self.store.get_repo(db, task.repo_id)
        if task.workspace_path and repo:
            try:
                await self.workflow.git.cleanup_worktree(
                    Path(repo.path),
                    Path(task.workspace_path),
                )
            except Exception:
                pass

        task.description = append_follow_up_instructions(task.description, comment)
        task.error_message = None
        task.plan_text = None
        task.diff_text = None
        task.workspace_path = None
        task.retry_count = 0
        await self._commit_status_change(db, task, TaskStatus.PENDING)

        if comment.strip():
            await self.events.log(task.id, f"Follow-up instructions received:\n{comment.strip()}")
        await self.events.log(task.id, "Task re-queued by user.")
        await self.store.attach_task_metadata(db, [task])
        await self.worker_pool.enqueue(task.id)
        return task

    async def delete_task(self, db, task_id: int, logs_dir: Path):
        task = await self.store.get_task(db, task_id)
        if not task:
            raise LookupError("Task not found")
        if task.status != TaskStatus.CANCELLED:
            raise ValueError("Only cancelled tasks can be deleted")

        dependent_task = await self.store.find_dependent_task(db, task_id)
        if dependent_task:
            raise ValueError(
                f"Task #{dependent_task.id} ({dependent_task.title}) depends on this task. "
                "Remove the dependency before deleting it."
            )

        repo = await self.store.get_repo(db, task.repo_id)
        workspace_path = task.workspace_path
        log_path = logs_dir / f"task-{task.id}.log"

        await self.workflow.codex.cancel(task.id)
        if workspace_path and repo:
            try:
                await self.workflow.git.cleanup_worktree(
                    Path(repo.path),
                    Path(workspace_path),
                )
            except Exception:
                pass

        await self.store.delete_task_records(db, task.id)
        await db.delete(task)
        await db.commit()
        if log_path.exists():
            log_path.unlink(missing_ok=True)
        await self.events.broadcast_task_deleted(task_id)

    async def _commit_status_change(self, db, task, new_status: TaskStatus):
        old_status = task.status
        task.status = new_status
        await db.commit()
        await db.refresh(task)
        await self.events.broadcast_state_change(task.id, old_status.value, new_status.value)
        await self.events.log(task.id, f"Status: {old_status.value} -> {new_status.value}")
