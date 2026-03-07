from __future__ import annotations

from sqlalchemy import select

from app.core.policies import should_mark_needs_attention, slugify
from app.models import Approval, Repo, Run, Task, TaskStatus


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

    async def get_task(self, db, task_id: int):
        task = await db.get(Task, task_id)
        if task and should_mark_needs_attention(task):
            task.status = TaskStatus.NEEDS_ATTENTION
            await db.commit()
            await db.refresh(task)
        return task

    async def list_tasks(self, db, status=None, repo_id=None):
        if status == TaskStatus.FAILED:
            stmt = select(Task).order_by(Task.created_at.desc())
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
            return [task for task in tasks if task.status == TaskStatus.FAILED]

        stmt = select(Task).order_by(Task.created_at.desc())
        if status is not None:
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
        return tasks

    async def create_task(
        self,
        db,
        *,
        repo_id: int,
        title: str,
        description: str,
        scheduled_for,
        blocked_by_task_id,
    ):
        task = Task(
            repo_id=repo_id,
            title=title,
            description=description,
            scheduled_for=scheduled_for,
            blocked_by_task_id=blocked_by_task_id,
        )
        db.add(task)
        await db.flush()
        task.branch_name = f"task/{task.id}/{slugify(title)}"
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

    async def attach_task_metadata(self, db, tasks: list[Task]) -> None:
        dependency_ids = {task.blocked_by_task_id for task in tasks if task.blocked_by_task_id}
        dependency_titles: dict[int, str] = {}

        if dependency_ids:
            result = await db.execute(select(Task.id, Task.title).where(Task.id.in_(dependency_ids)))
            dependency_titles = {task_id: title for task_id, title in result.all()}

        for task in tasks:
            task.blocked_by_title = dependency_titles.get(task.blocked_by_task_id)

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
