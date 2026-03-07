from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import WorkspaceCreate, WorkspaceResponse

router = APIRouter(prefix="/api", tags=["workspaces"])


@router.get("/repos/{repo_id}/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces(repo_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        return await request.app.state.services.workspace_service.list_workspaces(db, repo_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/repos/{repo_id}/workspaces", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    repo_id: int,
    body: WorkspaceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await request.app.state.services.workspace_service.create_workspace(
            db,
            repo_id,
            body.name,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        await request.app.state.services.workspace_service.delete_workspace(db, workspace_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
