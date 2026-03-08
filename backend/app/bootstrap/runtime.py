from __future__ import annotations

from dataclasses import dataclass

from app.adapters import AppEventSink, CodexRunner, GitManager, SQLiteStore
from app.api.websocket import ws_manager
from app.bootstrap.codex_sidecar import CodexSidecarManager
from app.config import settings
from app.core.codex_project_config import CodexProjectConfig
from app.core.project_policy import ProjectPolicy, load_project_policy
from app.core.prompt_library import PromptLibrary
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
    sidecar: CodexSidecarManager
    codex: CodexRunner
    policy: ProjectPolicy
    prompts: PromptLibrary
    codex_project: CodexProjectConfig
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
        await self.sidecar.start()
        await self.worker_pool.start(async_session)

    async def stop(self):
        await self.worker_pool.stop()
        await self.sidecar.stop()


def create_runtime() -> AppRuntime:
    policy = load_project_policy(settings.CODEX_POLICY_FILE)
    prompts = PromptLibrary.load_from_directory(settings.CODEX_PROMPTS_DIR)
    codex_project = CodexProjectConfig.load_from_file(settings.CODEX_PROJECT_CONFIG_FILE)
    git_mgr = GitManager(settings.WORKSPACES_DIR)
    sidecar = CodexSidecarManager(settings)
    codex = CodexRunner(
        base_url=f"http://{settings.CODEX_SIDECAR_HOST}:{settings.CODEX_SIDECAR_PORT}",
        model=settings.CODEX_MODEL,
        sandbox_mode=settings.CODEX_SANDBOX_MODE,
        approval_policy=settings.CODEX_APPROVAL_POLICY,
        run_timeout_s=settings.CODEX_RUN_TIMEOUT_S,
        prompt_library=prompts,
        policy=policy,
        project_config=codex_project,
    )
    task_logger = TaskLogger(settings.SESSION_LOGS_DIR)
    task_logger.set_ws_manager(ws_manager)
    event_sink = AppEventSink(task_logger, ws_manager)
    store = SQLiteStore()
    orchestrator = SymphonyWorkflowEngine(git_mgr, codex, event_sink, async_session)
    worker_pool = WorkerPool(orchestrator)
    orchestrator.set_worker_pool(worker_pool)
    repo_service = RepoService(store, git_mgr)
    workspace_service = WorkspaceService(store, git_mgr)
    task_intake = TaskIntakeService(store, codex, policy)
    task_commands = TaskCommandService(store, orchestrator, event_sink, worker_pool, policy)
    return AppRuntime(
        git=git_mgr,
        sidecar=sidecar,
        codex=codex,
        policy=policy,
        prompts=prompts,
        codex_project=codex_project,
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
