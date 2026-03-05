import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Approval, Repo, Task, TaskStatus
from app.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:50]


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreate, request: Request, db: AsyncSession = Depends(get_db)):
    repo = await db.get(Repo, body.repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    task = Task(repo_id=body.repo_id, title=body.title, description=body.description)
    db.add(task)
    await db.flush()
    task.branch_name = f"task/{task.id}/{slugify(body.title)}"
    await db.commit()
    await db.refresh(task)
    await request.app.state.worker_pool.enqueue(task.id)
    return task


@router.get("", response_model=list[TaskListResponse])
async def list_tasks(
    status: TaskStatus | None = Query(None),
    repo_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Task).order_by(Task.created_at.desc())
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if repo_id is not None:
        stmt = stmt.where(Task.repo_id == repo_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
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
        task.status = TaskStatus.IMPLEMENTING
        await db.commit()
        await request.app.state.worker_pool.enqueue(task.id)
    elif body.decision == "rejected":
        task.status = TaskStatus.FAILED
        task.error_message = f"Plan rejected: {body.comment}"
        await db.commit()

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
        task.status = TaskStatus.MERGING
        await db.commit()
        await request.app.state.worker_pool.enqueue(task.id)
    elif body.decision == "rejected":
        task.status = TaskStatus.FAILED
        task.error_message = f"Merge rejected: {body.comment}"
        await db.commit()

    await db.refresh(approval)
    return approval


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED):
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel task in {task.status} status"
        )
    task.status = TaskStatus.CANCELLED
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/{task_id}/logs")
async def get_task_logs(task_id: int):
    log_path = Path(settings.LOGS_DIR) / f"task-{task_id}.log"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    content = log_path.read_text()
    return PlainTextResponse(content)
