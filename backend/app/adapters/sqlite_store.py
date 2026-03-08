from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm.attributes import set_committed_value

from app.core.policies import should_mark_needs_attention, slugify
from app.models import ArchivedTask, Approval, Repo, Run, Task, TaskStatus, Workspace, WorkspaceKind


class SQLiteStore:
    async def get_repo(self, db, repo_id: int):
        return await db.get(Repo, repo_id)

    async def list_repos(self, db):
        result = await db.execute(select(Repo).order_by(Repo.created_at.desc()))
        return result.scalars().all()

    async def create_repo(self, db, name: str, path: str, default_branch: str):
        repo = Repo(name=name, path=path, default_branch=default_branch)
        db.add(repo)
        await db.commit()
        await db.refresh(repo)
        return repo

    async def delete_repo(self, db, repo: Repo) -> None:
        await db.delete(repo)
        await db.commit()

    async def get_workspace(self, db, workspace_id: int):
        return await db.get(Workspace, workspace_id)

    async def get_main_workspace(self, db, repo_id: int):
        result = await db.execute(
            select(Workspace).where(
                Workspace.repo_id == repo_id,
                Workspace.kind == WorkspaceKind.MAIN,
            )
        )
        return result.scalar_one_or_none()

    async def ensure_main_workspace(self, db, repo: Repo):
        workspace = await self.get_main_workspace(db, repo.id)
        if workspace is not None:
            return workspace
        return await self.create_workspace(
            db,
            repo_id=repo.id,
            name="Main",
            kind=WorkspaceKind.MAIN,
            base_branch=repo.default_branch,
        )

    async def list_workspaces(self, db, repo_id: int):
        result = await db.execute(
            select(Workspace).where(Workspace.repo_id == repo_id).order_by(Workspace.created_at.asc())
        )
        workspaces = result.scalars().all()
        workspaces.sort(key=lambda workspace: (workspace.kind != WorkspaceKind.MAIN, workspace.created_at))
        await self.attach_workspace_metadata(db, workspaces)
        return workspaces

    async def create_workspace(
        self,
        db,
        *,
        repo_id: int,
        name: str,
        kind: WorkspaceKind,
        base_branch: str,
    ):
        workspace = Workspace(
            repo_id=repo_id,
            name=name,
            kind=kind,
            base_branch=base_branch,
            branch_name="",
            workspace_path=None,
            is_active=True,
        )
        db.add(workspace)
        await db.flush()
        if kind == WorkspaceKind.MAIN:
            workspace.branch_name = f"workspace/main/{repo_id}"
        else:
            workspace.branch_name = f"workspace/{workspace.id}/{slugify(name)}"
        await db.commit()
        await db.refresh(workspace)
        workspace.task_count = 0
        return workspace

    async def delete_workspace(self, db, workspace: Workspace) -> None:
        await db.delete(workspace)
        await db.commit()

    async def count_workspace_tasks(self, db, workspace_id: int) -> int:
        result = await db.execute(
            select(func.count(Task.id)).where(Task.workspace_id == workspace_id)
        )
        return int(result.scalar_one() or 0)

    async def get_task(self, db, task_id: int):
        task = await db.get(Task, task_id)
        if task and should_mark_needs_attention(task):
            task.status = TaskStatus.NEEDS_ATTENTION
            await db.commit()
            await db.refresh(task)
        return task

    async def list_tasks(self, db, status=None, repo_id=None):
        stmt = select(Task).order_by(Task.created_at.desc())
        if status is not None and status != TaskStatus.FAILED:
            stmt = stmt.where(Task.status == status)
        if repo_id is not None:
            stmt = stmt.where(Task.repo_id == repo_id)

        result = await db.execute(stmt)
        tasks = result.scalars().all()
        changed = False
        for task in tasks:
            if should_mark_needs_attention(task):
                task.status = TaskStatus.NEEDS_ATTENTION
                changed = True
        if changed:
            await db.commit()
        await self.attach_task_metadata(db, tasks)
        if status == TaskStatus.FAILED:
            return [task for task in tasks if task.status == TaskStatus.FAILED]
        return tasks

    async def create_task(
        self,
        db,
        *,
        repo_id: int,
        workspace_id: int,
        title: str,
        description: str,
        scheduled_for,
        blocked_by_task_id,
        branch_name: str | None,
        workspace_path: str | None,
    ):
        task = Task(
            repo_id=repo_id,
            workspace_id=workspace_id,
            title=title,
            description=description,
            scheduled_for=scheduled_for,
            blocked_by_task_id=blocked_by_task_id,
            branch_name=branch_name,
            workspace_path=workspace_path,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    async def create_approval(self, db, task_id: int, phase: str, decision: str, comment: str):
        approval = Approval(
            task_id=task_id,
            phase=phase,
            decision=decision,
            comment=comment,
        )
        db.add(approval)
        await db.commit()
        return approval

    async def create_archived_task(
        self,
        db,
        *,
        original_task_id: int,
        repo_id: int,
        workspace_id: int | None,
        title: str,
        status: str,
        snapshot_json: str,
    ):
        archived_task = ArchivedTask(
            original_task_id=original_task_id,
            repo_id=repo_id,
            workspace_id=workspace_id,
            title=title,
            status=status,
            snapshot_json=snapshot_json,
        )
        db.add(archived_task)
        await db.flush()
        return archived_task

    async def attach_task_metadata(self, db, tasks: list[Task]) -> None:
        dependency_ids = {task.blocked_by_task_id for task in tasks if task.blocked_by_task_id}
        dependency_titles: dict[int, str] = {}
        workspace_ids = {task.workspace_id for task in tasks if task.workspace_id}
        workspace_map: dict[int, Workspace] = {}
        workspace_counts: dict[int, int] = {}

        if dependency_ids:
            result = await db.execute(select(Task.id, Task.title).where(Task.id.in_(dependency_ids)))
            dependency_titles = {task_id: title for task_id, title in result.all()}

        if workspace_ids:
            workspace_result = await db.execute(
                select(Workspace).where(Workspace.id.in_(workspace_ids))
            )
            workspace_map = {workspace.id: workspace for workspace in workspace_result.scalars().all()}

            count_result = await db.execute(
                select(Task.workspace_id, func.count(Task.id))
                .where(Task.workspace_id.in_(workspace_ids))
                .group_by(Task.workspace_id)
            )
            workspace_counts = {
                workspace_id: int(count)
                for workspace_id, count in count_result.all()
                if workspace_id is not None
            }

        for task in tasks:
            task.blocked_by_title = dependency_titles.get(task.blocked_by_task_id)
            workspace = workspace_map.get(task.workspace_id)
            task.workspace_name = workspace.name if workspace else None
            task.workspace_kind = workspace.kind if workspace else None
            task.workspace_task_count = workspace_counts.get(task.workspace_id or -1, 0)
            if workspace:
                task.workspace_path = workspace.workspace_path or task.workspace_path
                task.branch_name = workspace.branch_name

    async def attach_task_runs(self, db, task: Task) -> None:
        result = await db.execute(
            select(Run)
            .where(Run.task_id == task.id)
            .order_by(Run.started_at.asc(), Run.id.asc())
        )
        set_committed_value(task, "runs", list(result.scalars().all()))

    async def attach_workspace_metadata(self, db, workspaces: list[Workspace]) -> None:
        workspace_ids = [workspace.id for workspace in workspaces]
        if not workspace_ids:
            return

        count_result = await db.execute(
            select(Task.workspace_id, func.count(Task.id))
            .where(Task.workspace_id.in_(workspace_ids))
            .group_by(Task.workspace_id)
        )
        counts = {
            workspace_id: int(count)
            for workspace_id, count in count_result.all()
            if workspace_id is not None
        }
        for workspace in workspaces:
            workspace.task_count = counts.get(workspace.id, 0)

    async def list_task_runs(self, db, task_id: int) -> list[Run]:
        result = await db.execute(
            select(Run)
            .where(Run.task_id == task_id)
            .order_by(Run.started_at.asc(), Run.id.asc())
        )
        return list(result.scalars().all())

    async def list_task_approvals(self, db, task_id: int) -> list[Approval]:
        result = await db.execute(
            select(Approval)
            .where(Approval.task_id == task_id)
            .order_by(Approval.decided_at.asc(), Approval.id.asc())
        )
        return list(result.scalars().all())

    async def delete_task_records(self, db, task_id: int) -> None:
        runs = (await db.execute(select(Run).where(Run.task_id == task_id))).scalars().all()
        approvals = (
            await db.execute(select(Approval).where(Approval.task_id == task_id))
        ).scalars().all()

        for run in runs:
            await db.delete(run)
        for approval in approvals:
            await db.delete(approval)

    async def find_dependent_task(self, db, task_id: int):
        result = await db.execute(
            select(Task.id, Task.title).where(Task.blocked_by_task_id == task_id)
        )
        return result.first()

    async def find_repo_task(self, db, repo_id: int):
        result = await db.execute(
            select(Task.id, Task.title, Task.status)
            .where(Task.repo_id == repo_id)
            .order_by(Task.created_at.desc())
        )
        return result.first()
