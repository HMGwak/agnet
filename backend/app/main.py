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

    from app.api.websocket import ws_manager
    from app.config import settings
    from app.database import async_session
    from app.services.codex_agent import CodexAgent
    from app.services.git_manager import GitManager
    from app.services.logger import TaskLogger
    from app.services.orchestrator import Orchestrator
    from app.services.worker import WorkerPool

    git_mgr = GitManager(settings.WORKSPACES_DIR)
    codex = CodexAgent(settings.CODEX_COMMAND)
    task_logger = TaskLogger(settings.LOGS_DIR)
    task_logger.set_ws_manager(ws_manager)

    orchestrator = Orchestrator(git_mgr, codex, task_logger, ws_manager, async_session)
    worker_pool = WorkerPool(orchestrator)
    orchestrator.set_worker_pool(worker_pool)

    app.state.worker_pool = worker_pool
    app.state.orchestrator = orchestrator
    app.state.task_logger = task_logger

    await worker_pool.start(async_session)
    yield
    await worker_pool.stop()


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
