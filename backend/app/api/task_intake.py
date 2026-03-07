from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import TaskIntakeRequest, TaskIntakeResponse

router = APIRouter(prefix="/api/task-intake", tags=["task-intake"])


@router.post("/analyze", response_model=TaskIntakeResponse)
async def analyze_task_intake(
    body: TaskIntakeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await request.app.state.services.task_intake.analyze(db, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/refine", response_model=TaskIntakeResponse)
async def refine_task_intake(
    body: TaskIntakeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await request.app.state.services.task_intake.analyze(db, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
