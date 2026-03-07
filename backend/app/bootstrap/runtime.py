from __future__ import annotations

from dataclasses import dataclass

from app.adapters import AppEventSink, CodexAgent, GitManager, SQLiteStore
from app.api.websocket import ws_manager
from app.config import settings
from app.core.repo_service import RepoService
from app.core.task_commands import TaskCommandService
from app.core.task_intake import TaskIntakeService
from app.core.workspace_service import WorkspaceService
from app.core.workflow import SymphonyWorkflowEngine
from app.database import async_session
from app.services.logger import TaskLogger
from app.services.worker import WorkerPool


@dataclass
class AppRuntime:
    git: GitManager
    codex: CodexAgent
    task_logger: TaskLogger
    event_sink: AppEventSink
    store: SQLiteStore
    repo_service: RepoService
    workspace_service: WorkspaceService
    task_intake: TaskIntakeService
    orchestrator: SymphonyWorkflowEngine
    worker_pool: WorkerPool
    task_commands: TaskCommandService

    async def start(self):
        await self.worker_pool.start(async_session)

    async def stop(self):
        await self.worker_pool.stop()


def create_runtime() -> AppRuntime:
    git_mgr = GitManager(settings.WORKSPACES_DIR)
    codex = CodexAgent(settings.CODEX_COMMAND)
    task_logger = TaskLogger(settings.LOGS_DIR)
    task_logger.set_ws_manager(ws_manager)
    event_sink = AppEventSink(task_logger, ws_manager)
    store = SQLiteStore()
    orchestrator = SymphonyWorkflowEngine(git_mgr, codex, event_sink, async_session)
    worker_pool = WorkerPool(orchestrator)
    orchestrator.set_worker_pool(worker_pool)
    repo_service = RepoService(store, git_mgr)
    workspace_service = WorkspaceService(store, git_mgr)
    task_intake = TaskIntakeService(store, codex)
    task_commands = TaskCommandService(store, orchestrator, event_sink, worker_pool)
    return AppRuntime(
        git=git_mgr,
        codex=codex,
        task_logger=task_logger,
        event_sink=event_sink,
        store=store,
        repo_service=repo_service,
        workspace_service=workspace_service,
        task_intake=task_intake,
        orchestrator=orchestrator,
        worker_pool=worker_pool,
        task_commands=task_commands,
    )
