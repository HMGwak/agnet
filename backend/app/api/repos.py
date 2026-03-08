import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import RepoCreate, RepoPathPickResponse, RepoResponse

router = APIRouter(prefix="/api/repos", tags=["repos"])


def pick_directory_path() -> str | None:
    try:
        from tkinter import Tk, filedialog
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise RuntimeError("Directory picker is not available") from exc

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(mustexist=True)
    finally:
        root.destroy()
    return selected or None


@router.post("/pick-path", response_model=RepoPathPickResponse)
async def pick_repo_path():
    try:
        path = await asyncio.to_thread(pick_directory_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - OS/UI integration path
        raise HTTPException(status_code=500, detail="Failed to open directory picker") from exc
    return RepoPathPickResponse(path=path)


@router.post("", response_model=RepoResponse, status_code=201)
async def create_repo(
    body: RepoCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await request.app.state.services.repo_service.create_repo(
            db,
            body.name,
            body.path,
            body.default_branch,
            body.create_if_missing,
            body.profile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[RepoResponse])
async def list_repos(request: Request, db: AsyncSession = Depends(get_db)):
    return await request.app.state.services.repo_service.list_repos(db)


@router.get("/{repo_id}", response_model=RepoResponse)
async def get_repo(repo_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    repo = await request.app.state.services.repo_service.get_repo(db, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo


@router.delete("/{repo_id}", status_code=204)
async def delete_repo(repo_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await request.app.state.services.repo_service.delete_repo(db, repo_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
