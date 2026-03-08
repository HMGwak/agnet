from __future__ import annotations

from app.adapters.sqlite_store import SQLiteStore
from app.core.policies import append_follow_up_instructions
from app.core.project_policy import ProjectPolicy, classify_main_workspace_request
from app.models import TaskStatus, WorkspaceKind


class TaskCommandService:
    def __init__(
        self,
        store: SQLiteStore,
        workflow,
        event_sink,
        worker_pool,
        policy: ProjectPolicy,
    ):
        self.store = store
        self.workflow = workflow
        self.events = event_sink
        self.worker_pool = worker_pool
        self.policy = policy

    async def create_task(
        self,
        db,
        repo_id: int,
        title: str,
        description: str,
        scheduled_for,
        blocked_by_task_id,
        workspace_id,
        create_workspace,
    ):
        repo = await self.store.get_repo(db, repo_id)
        if not repo:
            raise ValueError("Repo not found")

        if workspace_id is not None and create_workspace is not None:
            raise ValueError("Choose an existing workspace or create a new one, not both")

        dependency_task = None
        if blocked_by_task_id is not None:
            dependency_task = await self.store.get_task(db, blocked_by_task_id)
            if not dependency_task:
                raise LookupError("Dependency task not found")
            if dependency_task.repo_id != repo_id:
                raise ValueError("Dependency task must belong to the same repository")

        workspace = None
        auto_routed_from_main = False
        if workspace_id is not None:
            workspace = await self.store.get_workspace(db, workspace_id)
            if workspace is None:
                raise LookupError("Workspace not found")
            if workspace.repo_id != repo_id:
                raise ValueError("Workspace must belong to the same repository")
        elif create_workspace is not None:
            workspace_name = create_workspace.name.strip()
            if not workspace_name:
                raise ValueError("Workspace name cannot be empty")
            workspace = await self.store.create_workspace(
                db,
                repo_id=repo_id,
                name=workspace_name,
                kind=WorkspaceKind.FEATURE,
                base_branch=repo.default_branch,
            )
        else:
            workspace = await self.store.ensure_main_workspace(db, repo)

        if workspace.kind == WorkspaceKind.MAIN:
            intent = classify_main_workspace_request(self.policy, title, description)
            if intent == "feature":
                if not self.policy.main_allow_feature_work:
                    if not self.policy.auto_fork_feature_workspace_from_main:
                        raise ValueError("Feature work is not allowed on the main workspace")
                    workspace = await self.store.create_workspace(
                        db,
                        repo_id=repo_id,
                        name=title.strip() or "Feature Workspace",
                        kind=WorkspaceKind.FEATURE,
                        base_branch=repo.default_branch,
                    )
                    auto_routed_from_main = True
            elif intent == "hotfix" and not self.policy.main_allow_hotfix:
                raise ValueError("Hotfix work is not allowed on the main workspace")
            elif intent == "plan_review" and not self.policy.main_allow_plan_review:
                raise ValueError("Planning and review work are not allowed on the main workspace")

        task = await self.store.create_task(
            db,
            repo_id=repo_id,
            workspace_id=workspace.id,
            title=title,
            description=description,
            scheduled_for=scheduled_for,
            blocked_by_task_id=blocked_by_task_id,
            branch_name=workspace.branch_name,
            workspace_path=workspace.workspace_path,
        )
        task.blocked_by_title = dependency_task.title if dependency_task else None
        task.workspace_name = workspace.name
        task.workspace_kind = workspace.kind
        task.workspace_task_count = await self.store.count_workspace_tasks(db, workspace.id)
        if auto_routed_from_main:
            await self.events.log(
                task.id,
                f"Protected main routed this task to feature workspace '{workspace.name}'.",
            )
        await self.worker_pool.enqueue(task.id)
        await self.store.attach_task_runs(db, task)
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
        await self.store.attach_task_runs(db, task)
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

        task.description = append_follow_up_instructions(task.description, comment)
        task.error_message = None
        task.plan_text = None
        task.diff_text = None
        task.retry_count = 0
        await self._commit_status_change(db, task, TaskStatus.PENDING)

        if comment.strip():
            await self.events.log(task.id, f"Follow-up instructions received:\n{comment.strip()}")
        await self.events.log(task.id, "Task re-queued by user.")
        await self.store.attach_task_metadata(db, [task])
        await self.store.attach_task_runs(db, task)
        await self.worker_pool.enqueue(task.id)
        return task

    async def delete_task(
        self,
        db,
        task_id: int,
        delete_workspace_if_empty: bool = False,
    ):
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

        workspace = None
        if task.workspace_id is not None:
            workspace = await self.store.get_workspace(db, task.workspace_id)

        await self.workflow.codex.cancel(task.id)

        await self.store.delete_task_records(db, task.id)
        await db.delete(task)
        await db.commit()
        await self.events.broadcast_task_deleted(task_id)

        if (
            delete_workspace_if_empty
            and workspace is not None
            and workspace.kind == WorkspaceKind.FEATURE
            and await self.store.count_workspace_tasks(db, workspace.id) == 0
        ):
            repo = await self.store.get_repo(db, workspace.repo_id)
            if workspace.workspace_path and repo:
                try:
                    await self.workflow.git.cleanup_worktree(
                        Path(repo.path),
                        Path(workspace.workspace_path),
                    )
                except Exception:
                    pass
            await self.store.delete_workspace(db, workspace)

    async def _commit_status_change(self, db, task, new_status: TaskStatus):
        old_status = task.status
        task.status = new_status
        await db.commit()
        await db.refresh(task)
        await self.events.broadcast_state_change(task.id, old_status.value, new_status.value)
        await self.events.log(task.id, f"Status: {old_status.value} -> {new_status.value}")
