import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Approval, Repo, Run, Task, TaskStatus
from app.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    TaskCreate,
    TaskListResponse,
    TaskResumeRequest,
    TaskResponse,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:50]


def _should_mark_needs_attention(task: Task) -> bool:
    if task.status != TaskStatus.FAILED:
        return False
    message = (task.error_message or "").strip()
    return message.startswith("Plan rejected:") or message.startswith("Merge rejected:")


async def _attach_task_metadata(db: AsyncSession, tasks: list[Task]) -> None:
    dependency_ids = {task.blocked_by_task_id for task in tasks if task.blocked_by_task_id}
    dependency_titles: dict[int, str] = {}

    if dependency_ids:
        result = await db.execute(select(Task.id, Task.title).where(Task.id.in_(dependency_ids)))
        dependency_titles = {task_id: title for task_id, title in result.all()}

    for task in tasks:
        task.blocked_by_title = dependency_titles.get(task.blocked_by_task_id)


def _append_follow_up_instructions(description: str, comment: str) -> str:
    cleaned_comment = comment.strip()
    if not cleaned_comment:
        return description

    block = f"Follow-up instructions:\n{cleaned_comment}"
    cleaned_description = description.strip()
    if not cleaned_description:
        return block
    return f"{cleaned_description}\n\n{block}"


async def _commit_status_change(
    request: Request,
    db: AsyncSession,
    task: Task,
    new_status: TaskStatus,
) -> None:
    old_status = task.status
    task.status = new_status
    await db.commit()
    await db.refresh(task)
    await request.app.state.orchestrator.ws.broadcast_state_change(
        task.id,
        old_status.value,
        new_status.value,
    )
    await request.app.state.orchestrator.logger.log(
        task.id,
        f"Status: {old_status.value} -> {new_status.value}",
    )


async def _delete_task_records(db: AsyncSession, task_id: int) -> None:
    runs = (await db.execute(select(Run).where(Run.task_id == task_id))).scalars().all()
    approvals = (
        await db.execute(select(Approval).where(Approval.task_id == task_id))
    ).scalars().all()

    for run in runs:
        await db.delete(run)
    for approval in approvals:
        await db.delete(approval)


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreate, request: Request, db: AsyncSession = Depends(get_db)):
    repo = await db.get(Repo, body.repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    dependency_task = None
    if body.blocked_by_task_id is not None:
        dependency_task = await db.get(Task, body.blocked_by_task_id)
        if not dependency_task:
            raise HTTPException(status_code=404, detail="Dependency task not found")
        if dependency_task.repo_id != body.repo_id:
            raise HTTPException(
                status_code=400,
                detail="Dependency task must belong to the same repository",
            )

    task = Task(
        repo_id=body.repo_id,
        title=body.title,
        description=body.description,
        scheduled_for=body.scheduled_for,
        blocked_by_task_id=body.blocked_by_task_id,
    )
    db.add(task)
    await db.flush()
    task.branch_name = f"task/{task.id}/{slugify(body.title)}"
    await db.commit()
    await db.refresh(task)
    task.blocked_by_title = dependency_task.title if dependency_task else None
    await request.app.state.worker_pool.enqueue(task.id)
    return task


@router.get("", response_model=list[TaskListResponse])
async def list_tasks(
    status: TaskStatus | None = Query(None),
    repo_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if status == TaskStatus.FAILED:
        stmt = select(Task).order_by(Task.created_at.desc())
        if repo_id is not None:
            stmt = stmt.where(Task.repo_id == repo_id)
        result = await db.execute(stmt)
        tasks = result.scalars().all()
        changed = False
        for task in tasks:
            if _should_mark_needs_attention(task):
                task.status = TaskStatus.NEEDS_ATTENTION
                changed = True
        if changed:
            await db.commit()
        await _attach_task_metadata(db, tasks)
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
        if _should_mark_needs_attention(task):
            task.status = TaskStatus.NEEDS_ATTENTION
            changed = True
    if changed:
        await db.commit()
    await _attach_task_metadata(db, tasks)
    return tasks


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if _should_mark_needs_attention(task):
        task.status = TaskStatus.NEEDS_ATTENTION
        await db.commit()
        await db.refresh(task)
    await _attach_task_metadata(db, [task])
    return task


@router.post("/{task_id}/approve-plan", response_model=ApprovalResponse)
async def approve_plan(
    task_id: int, body: ApprovalRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != TaskStatus.AWAIT_PLAN_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Task status is {task.status}, expected AWAIT_PLAN_APPROVAL",
        )

    approval = Approval(
        task_id=task_id, phase="plan", decision=body.decision, comment=body.comment
    )
    db.add(approval)

    if body.decision == "approved":
        await _commit_status_change(request, db, task, TaskStatus.IMPLEMENTING)
        await request.app.state.worker_pool.enqueue(task.id)
    elif body.decision == "rejected":
        task.error_message = f"Plan rejected: {body.comment}"
        await _commit_status_change(request, db, task, TaskStatus.NEEDS_ATTENTION)

    await db.refresh(approval)
    return approval


@router.post("/{task_id}/approve-merge", response_model=ApprovalResponse)
async def approve_merge(
    task_id: int, body: ApprovalRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != TaskStatus.AWAIT_MERGE_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Task status is {task.status}, expected AWAIT_MERGE_APPROVAL",
        )

    approval = Approval(
        task_id=task_id, phase="merge", decision=body.decision, comment=body.comment
    )
    db.add(approval)

    if body.decision == "approved":
        await _commit_status_change(request, db, task, TaskStatus.MERGING)
        await request.app.state.worker_pool.enqueue(task.id)
    elif body.decision == "rejected":
        task.error_message = f"Merge rejected: {body.comment}"
        await _commit_status_change(request, db, task, TaskStatus.NEEDS_ATTENTION)

    await db.refresh(approval)
    return approval


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == TaskStatus.DONE:
        raise HTTPException(status_code=400, detail="Cannot cancel a completed task")

    codex = request.app.state.orchestrator.codex
    await codex.cancel(task_id)
    if task.status != TaskStatus.CANCELLED:
        await _commit_status_change(request, db, task, TaskStatus.CANCELLED)
    else:
        await db.refresh(task)
    await _attach_task_metadata(db, [task])
    return task


@router.post("/{task_id}/resume", response_model=TaskResponse)
async def resume_task(
    task_id: int,
    body: TaskResumeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == TaskStatus.DONE:
        raise HTTPException(status_code=400, detail="Cannot requeue a completed task")

    if task.status not in (
        TaskStatus.NEEDS_ATTENTION,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Task status is {task.status}, expected NEEDS_ATTENTION, FAILED, or CANCELLED",
        )

    repo = await db.get(Repo, task.repo_id)
    if task.workspace_path and repo:
        try:
            await request.app.state.orchestrator.git.cleanup_worktree(
                Path(repo.path),
                Path(task.workspace_path),
            )
        except Exception:
            pass

    task.description = _append_follow_up_instructions(task.description, body.comment)
    task.error_message = None
    task.plan_text = None
    task.diff_text = None
    task.workspace_path = None
    task.retry_count = 0
    await _commit_status_change(request, db, task, TaskStatus.PENDING)

    if body.comment.strip():
        await request.app.state.orchestrator.logger.log(
            task.id,
            f"Follow-up instructions received:\n{body.comment.strip()}",
        )
    await request.app.state.orchestrator.logger.log(task.id, "Task re-queued by user.")

    await _attach_task_metadata(db, [task])
    await request.app.state.worker_pool.enqueue(task.id)
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.CANCELLED:
        raise HTTPException(
            status_code=400,
            detail="Only cancelled tasks can be deleted",
        )

    dependent_task = (
        await db.execute(
            select(Task.id, Task.title).where(Task.blocked_by_task_id == task_id)
        )
    ).first()
    if dependent_task:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Task #{dependent_task.id} ({dependent_task.title}) depends on this task. "
                "Remove the dependency before deleting it."
            ),
        )

    repo = await db.get(Repo, task.repo_id)
    workspace_path = task.workspace_path
    log_path = Path(settings.LOGS_DIR) / f"task-{task.id}.log"

    await request.app.state.orchestrator.codex.cancel(task.id)

    if workspace_path and repo:
        try:
            await request.app.state.orchestrator.git.cleanup_worktree(
                Path(repo.path),
                Path(workspace_path),
            )
        except Exception:
            pass

    await _delete_task_records(db, task.id)
    await db.delete(task)
    await db.commit()

    if log_path.exists():
        log_path.unlink(missing_ok=True)

    await request.app.state.orchestrator.ws.broadcast_task_deleted(task_id)


@router.get("/{task_id}/logs")
async def get_task_logs(task_id: int):
    log_path = Path(settings.LOGS_DIR) / f"task-{task_id}.log"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    content = log_path.read_text()
    return PlainTextResponse(content)
