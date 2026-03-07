from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import TaskStatus
from app.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    TaskCreate,
    TaskListResponse,
    TaskResumeRequest,
    TaskResponse,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreate, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        return await request.app.state.services.task_commands.create_task(
            db,
            body.repo_id,
            body.title,
            body.description,
            body.scheduled_for,
            body.blocked_by_task_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[TaskListResponse])
async def list_tasks(
    request: Request,
    status: TaskStatus | None = Query(None),
    repo_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await request.app.state.services.store.list_tasks(db, status, repo_id)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    task = await request.app.state.services.store.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await request.app.state.services.store.attach_task_metadata(db, [task])
    return task


@router.post("/{task_id}/approve-plan", response_model=ApprovalResponse)
async def approve_plan(
    task_id: int, body: ApprovalRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        return await request.app.state.services.task_commands.approve_plan(
            db,
            task_id,
            body.decision,
            body.comment,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{task_id}/approve-merge", response_model=ApprovalResponse)
async def approve_merge(
    task_id: int, body: ApprovalRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        return await request.app.state.services.task_commands.approve_merge(
            db,
            task_id,
            body.decision,
            body.comment,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        return await request.app.state.services.task_commands.cancel_task(db, task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{task_id}/resume", response_model=TaskResponse)
async def resume_task(
    task_id: int,
    body: TaskResumeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await request.app.state.services.task_commands.resume_task(
            db,
            task_id,
            body.comment,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await request.app.state.services.task_commands.delete_task(
            db,
            task_id,
            Path(settings.LOGS_DIR),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{task_id}/logs")
async def get_task_logs(task_id: int):
    log_path = Path(settings.LOGS_DIR) / f"task-{task_id}.log"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    content = log_path.read_text()
    return PlainTextResponse(content)
