from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.repos import router as repos_router
from app.api.tasks import router as tasks_router
from app.api.websocket import router as ws_router
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Phase 6: worker pool start here
    yield
    # Phase 6: worker pool stop here


app = FastAPI(title="AI Dev Automation", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repos_router)
app.include_router(tasks_router)
app.include_router(ws_router)
