import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Repo
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
async def create_repo(body: RepoCreate, db: AsyncSession = Depends(get_db)):
    repo_path = Path(body.path)
    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail="Path does not exist or is not a directory")
    if not (repo_path / ".git").exists():
        raise HTTPException(status_code=400, detail="Path is not a git repository")

    repo = Repo(name=body.name, path=str(repo_path), default_branch=body.default_branch)
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


@router.get("", response_model=list[RepoResponse])
async def list_repos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Repo).order_by(Repo.created_at.desc()))
    return result.scalars().all()


@router.get("/{repo_id}", response_model=RepoResponse)
async def get_repo(repo_id: int, db: AsyncSession = Depends(get_db)):
    repo = await db.get(Repo, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo
