# AI Dev Automation Dashboard - Detailed Implementation Plan

백지상태에서 구현할 수 있도록 각 Phase별 정확한 파일, 코드 구조, 명령어를 기술한다.

---

## Phase 0: 프로젝트 초기화

### 0-1. 디렉토리 생성

```bash
cd /home/planee/python/task_manager
mkdir -p backend/app/api backend/app/services
mkdir -p repos workspaces logs database
```

### 0-2. Backend 프로젝트 설정

**파일: `backend/pyproject.toml`**

```toml
[project]
name = "ai-dev-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi[standard]>=0.115",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.20",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "httpx>=0.27",
    "uvicorn[standard]>=0.30",
    "websockets>=13.0",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "pytest-httpx"]
```

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 0-3. Frontend 프로젝트 설정

```bash
cd /home/planee/python/task_manager
npx create-next-app@latest dashboard \
  --typescript --tailwind --eslint --app --src-dir \
  --import-alias "@/*" --no-turbopack
cd dashboard
npm install swr react-diff-viewer-continued lucide-react
```

### 0-4. 테스트용 Git 레포 생성

```bash
cd /home/planee/python/task_manager/repos
mkdir sample-project && cd sample-project
git init
echo '# Sample Project' > README.md
mkdir src
cat > src/main.py << 'EOF'
def hello():
    return "Hello, World!"

if __name__ == "__main__":
    print(hello())
EOF
cat > src/test_main.py << 'EOF'
from main import hello

def test_hello():
    assert hello() == "Hello, World!"
EOF
git add -A && git commit -m "Initial commit"
```

### 검증

- `backend/.venv/bin/python -c "import fastapi; print('OK')"`
- `cd dashboard && npm run dev` (localhost:3000 접속)
- `cd repos/sample-project && git log --oneline`

---

## Phase 1: Backend 스켈레톤 + DB 모델

### 1-1. 설정 (`backend/app/config.py`)

```python
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent  # task_manager/
    DATABASE_URL: str = ""
    REPOS_DIR: Path = Path("")
    WORKSPACES_DIR: Path = Path("")
    LOGS_DIR: Path = Path("")
    MAX_CONCURRENT_TASKS: int = 6
    CODEX_COMMAND: str = "codex"

    def model_post_init(self, __context):
        if not self.DATABASE_URL:
            self.DATABASE_URL = f"sqlite+aiosqlite:///{self.BASE_DIR / 'database' / 'dev.db'}"
        if self.REPOS_DIR == Path(""):
            self.REPOS_DIR = self.BASE_DIR / "repos"
        if self.WORKSPACES_DIR == Path(""):
            self.WORKSPACES_DIR = self.BASE_DIR / "workspaces"
        if self.LOGS_DIR == Path(""):
            self.LOGS_DIR = self.BASE_DIR / "logs"

settings = Settings()
```

### 1-2. DB 엔진 (`backend/app/database.py`)

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with async_session() as session:
        yield session
```

### 1-3. ORM 모델 (`backend/app/models.py`)

```python
import enum
from datetime import datetime
from sqlalchemy import Integer, String, Text, Enum, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    PREPARING_WORKSPACE = "PREPARING_WORKSPACE"
    PLANNING = "PLANNING"
    AWAIT_PLAN_APPROVAL = "AWAIT_PLAN_APPROVAL"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    AWAIT_MERGE_APPROVAL = "AWAIT_MERGE_APPROVAL"
    MERGING = "MERGING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class Repo(Base):
    __tablename__ = "repos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    path: Mapped[str] = mapped_column(String(1024))
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    tasks: Mapped[list["Task"]] = relationship(back_populates="repo")

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING
    )
    branch_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    workspace_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    plan_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    repo: Mapped["Repo"] = relationship(back_populates="tasks")
    runs: Mapped[list["Run"]] = relationship(back_populates="task")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="task")

class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    phase: Mapped[str] = mapped_column(String(50))  # "plan", "implement", "test", "merge"
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    task: Mapped["Task"] = relationship(back_populates="runs")

class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    phase: Mapped[str] = mapped_column(String(20))  # "plan" or "merge"
    decision: Mapped[str] = mapped_column(String(20))  # "approved" or "rejected"
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    task: Mapped["Task"] = relationship(back_populates="approvals")
```

### 1-4. Pydantic 스키마 (`backend/app/schemas.py`)

```python
from datetime import datetime
from pydantic import BaseModel
from app.models import TaskStatus

# --- Repo ---
class RepoCreate(BaseModel):
    name: str
    path: str
    default_branch: str = "main"

class RepoResponse(BaseModel):
    id: int
    name: str
    path: str
    default_branch: str
    created_at: datetime
    model_config = {"from_attributes": True}

# --- Task ---
class TaskCreate(BaseModel):
    repo_id: int
    title: str
    description: str = ""

class TaskResponse(BaseModel):
    id: int
    repo_id: int
    title: str
    description: str
    status: TaskStatus
    branch_name: str | None
    workspace_path: str | None
    plan_text: str | None
    diff_text: str | None
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class TaskListResponse(BaseModel):
    id: int
    repo_id: int
    title: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

# --- Approval ---
class ApprovalRequest(BaseModel):
    decision: str  # "approved" or "rejected"
    comment: str = ""

class ApprovalResponse(BaseModel):
    id: int
    task_id: int
    phase: str
    decision: str
    comment: str | None
    decided_at: datetime
    model_config = {"from_attributes": True}

# --- Run ---
class RunResponse(BaseModel):
    id: int
    task_id: int
    phase: str
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    log_path: str | None
    model_config = {"from_attributes": True}
```

### 1-5. FastAPI 엔트리포인트 (`backend/app/main.py`)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # TODO: Phase 6에서 worker pool 시작
    yield
    # TODO: Phase 6에서 worker pool 종료

app = FastAPI(title="AI Dev Automation", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터는 Phase 2에서 추가
```

### 1-6. 빈 `__init__.py` 파일들

```bash
touch backend/app/__init__.py
touch backend/app/api/__init__.py
touch backend/app/services/__init__.py
```

### 검증

```bash
cd backend
uvicorn app.main:app --reload --port 8000
# http://localhost:8000/docs 접속 확인
# database/dev.db 파일 생성 확인
```

---

## Phase 2: REST API (CRUD)

### 2-1. Repo API (`backend/app/api/repos.py`)

핵심 로직:
- `POST /api/repos`: path 존재 여부 + git 레포 여부 검증 후 DB 저장
- `GET /api/repos`: 전체 목록 반환
- `GET /api/repos/{id}`: 단건 조회

```python
router = APIRouter(prefix="/api/repos", tags=["repos"])

@router.post("/", response_model=RepoResponse, status_code=201)
# - Path(request.path)가 실존하는 디렉토리인지 확인
# - .git 디렉토리 존재 확인
# - DB에 Repo 저장

@router.get("/", response_model=list[RepoResponse])
# - select(Repo).order_by(Repo.created_at.desc())

@router.get("/{repo_id}", response_model=RepoResponse)
# - 404 처리 포함
```

### 2-2. Task API (`backend/app/api/tasks.py`)

핵심 로직:
- `POST /api/tasks`: Task 생성 (status=PENDING), branch_name 자동 생성 (`task/{id}/{slugified-title}`)
- `GET /api/tasks`: 필터링 (status, repo_id query params)
- `GET /api/tasks/{id}`: 상세 (plan_text, diff_text 포함)
- `POST /api/tasks/{id}/approve-plan`: status가 AWAIT_PLAN_APPROVAL일 때만 처리
- `POST /api/tasks/{id}/approve-merge`: status가 AWAIT_MERGE_APPROVAL일 때만 처리
- `POST /api/tasks/{id}/cancel`: 진행 중인 태스크 취소
- `GET /api/tasks/{id}/logs`: 로그 파일 내용 반환 (HTTP fallback)

```python
router = APIRouter(prefix="/api/tasks", tags=["tasks"])

@router.post("/", response_model=TaskResponse, status_code=201)
# - repo_id 유효성 확인
# - Task 생성, flush로 id 확보
# - branch_name = f"task/{task.id}/{slugify(title)}"
# - commit
# - TODO: Phase 6에서 worker 큐에 추가

@router.get("/", response_model=list[TaskListResponse])
# - Optional[TaskStatus] status 필터
# - Optional[int] repo_id 필터

@router.get("/{task_id}", response_model=TaskResponse)

@router.post("/{task_id}/approve-plan", response_model=ApprovalResponse)
# - task.status != AWAIT_PLAN_APPROVAL 이면 400 에러
# - Approval 레코드 생성 (phase="plan")
# - decision == "approved": task.status = IMPLEMENTING
# - decision == "rejected": task.status = FAILED
# - TODO: Phase 6에서 approved면 worker 재개

@router.post("/{task_id}/approve-merge", response_model=ApprovalResponse)
# - task.status != AWAIT_MERGE_APPROVAL 이면 400 에러
# - Approval 레코드 생성 (phase="merge")
# - decision == "approved": task.status = MERGING
# - decision == "rejected": task.status = FAILED
# - TODO: Phase 6에서 approved면 worker 재개

@router.post("/{task_id}/cancel")
# - DONE, FAILED, CANCELLED 상태면 400
# - task.status = CANCELLED

@router.get("/{task_id}/logs")
# - logs/task-{id}.log 파일 읽어서 PlainTextResponse 반환
```

### 2-3. 라우터 등록 (`backend/app/main.py`에 추가)

```python
from app.api.repos import router as repos_router
from app.api.tasks import router as tasks_router

app.include_router(repos_router)
app.include_router(tasks_router)
```

### 검증

```bash
# 레포 등록
curl -X POST http://localhost:8000/api/repos \
  -H "Content-Type: application/json" \
  -d '{"name":"sample-project","path":"/home/planee/python/task_manager/repos/sample-project"}'

# 태스크 생성
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"repo_id":1,"title":"Add logging","description":"Add logging to main.py"}'

# 태스크 목록
curl http://localhost:8000/api/tasks

# Swagger: http://localhost:8000/docs
```

---

## Phase 3: Git Manager

### 3-1. Git Manager 서비스 (`backend/app/services/git_manager.py`)

asyncio.create_subprocess_exec로 git 명령어 실행. 모든 메서드는 async.

```python
class GitManager:
    def __init__(self, workspaces_dir: Path):
        self.workspaces_dir = workspaces_dir

    async def _run_git(self, *args, cwd: Path | None = None) -> tuple[int, str, str]:
        """git 명령 실행, (returncode, stdout, stderr) 반환"""

    async def create_worktree(self, repo_path: Path, branch_name: str, task_id: int) -> Path:
        """
        1. repo_path에서 default branch 최신으로 pull (선택적, 로컬이므로 skip 가능)
        2. workspace_path = self.workspaces_dir / f"task-{task_id}"
        3. git -C {repo_path} worktree add -b {branch_name} {workspace_path}
        4. return workspace_path
        """

    async def get_diff(self, workspace_path: Path, base_branch: str = "main") -> str:
        """
        git -C {workspace_path} diff {base_branch}...HEAD
        전체 diff 문자열 반환
        """

    async def merge_to_main(self, repo_path: Path, branch_name: str) -> tuple[bool, str]:
        """
        1. git -C {repo_path} checkout main
        2. git -C {repo_path} merge --no-ff {branch_name} -m "Merge {branch_name}"
        3. return (성공여부, 메시지)
        """

    async def cleanup_worktree(self, repo_path: Path, workspace_path: Path):
        """
        1. git -C {repo_path} worktree remove {workspace_path} --force
        2. 혹시 남은 디렉토리면 shutil.rmtree
        """
```

### 3-2. 테스트 (`backend/tests/test_git_manager.py`)

```python
import pytest, tempfile, subprocess
from pathlib import Path
from app.services.git_manager import GitManager

@pytest.fixture
def temp_repo(tmp_path):
    """임시 git 레포 생성"""
    repo = tmp_path / "test-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=repo)
    (repo / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=repo)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo)
    return repo

@pytest.mark.asyncio
async def test_create_worktree(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(temp_repo, "task/1/test-branch", 1)
    assert ws.exists()
    assert (ws / "README.md").exists()

@pytest.mark.asyncio
async def test_merge_to_main(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(temp_repo, "task/2/feature", 2)
    (ws / "new_file.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=ws)
    subprocess.run(["git", "commit", "-m", "add file"], cwd=ws)
    success, msg = await gm.merge_to_main(temp_repo, "task/2/feature")
    assert success
```

### 검증

```bash
cd backend
pytest tests/test_git_manager.py -v
```

---

## Phase 4: Codex Agent Integration

### 4-1. Codex Agent 서비스 (`backend/app/services/codex_agent.py`)

```python
class CodexAgent:
    def __init__(self, codex_command: str = "codex"):
        self.codex_command = codex_command

    async def run_codex(
        self, prompt: str, cwd: Path, log_callback: Callable[[str], Awaitable[None]] | None = None
    ) -> tuple[int, str]:
        """
        codex --quiet --full-auto -p "{prompt}" 실행
        - asyncio.create_subprocess_exec 사용
        - stdout/stderr를 라인 단위로 읽으며 log_callback 호출
        - 전체 출력과 exit_code 반환
        """

    async def generate_plan(self, workspace_path: Path, task_description: str, **kw) -> tuple[int, str]:
        """
        프롬프트:
        "Analyze this repository and create a detailed implementation plan for:
         {task_description}

         Output ONLY the plan as a numbered list. Do not modify any files."
        """
        prompt = f"""Analyze this repository and create a detailed implementation plan for the following task.
Do NOT modify any files. Output ONLY a numbered step-by-step plan.

Task: {task_description}"""
        return await self.run_codex(prompt, cwd=workspace_path, **kw)

    async def implement_plan(self, workspace_path: Path, plan_text: str, task_description: str, **kw) -> tuple[int, str]:
        """
        프롬프트:
        "Implement the following plan:
         {plan_text}

         Original task: {task_description}

         Create all necessary files and make a git commit with your changes."
        """
        prompt = f"""Implement the following plan in this repository.
Make all necessary code changes and commit them.

Original task: {task_description}

Plan:
{plan_text}"""
        return await self.run_codex(prompt, cwd=workspace_path, **kw)

    async def run_tests(self, workspace_path: Path, **kw) -> tuple[int, str]:
        """
        프롬프트:
        "Run the project's test suite. If tests fail, fix the code and re-run.
         Commit any fixes."
        """
        prompt = "Run the project's test suite. If any tests fail, fix the issues and re-run until they pass. Commit any fixes."
        return await self.run_codex(prompt, cwd=workspace_path, **kw)
```

### 4-2. 수동 테스트

```bash
# codex CLI가 설치되어 있는지 확인
which codex

# 직접 실행해서 동작 확인
cd /home/planee/python/task_manager/repos/sample-project
codex --quiet --full-auto -p "List the files in this project and describe what they do"
```

### 검증

- Codex CLI 설치 확인
- `generate_plan()` 호출 시 plan 텍스트가 반환되는지 수동 확인

---

## Phase 5: Logging + WebSocket

### 5-1. Logger 서비스 (`backend/app/services/logger.py`)

```python
class TaskLogger:
    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._ws_manager: "WebSocketManager | None" = None

    def set_ws_manager(self, manager: "WebSocketManager"):
        self._ws_manager = manager

    def get_log_path(self, task_id: int) -> Path:
        return self.logs_dir / f"task-{task_id}.log"

    async def log(self, task_id: int, line: str):
        """
        1. 파일에 append (timestamp prefix)
        2. WebSocket으로 브로드캐스트
        """
        timestamp = datetime.now().isoformat()
        log_line = f"[{timestamp}] {line}\n"
        log_path = self.get_log_path(task_id)
        async with aiofiles.open(log_path, "a") as f:
            await f.write(log_line)
        if self._ws_manager:
            await self._ws_manager.broadcast(task_id, {
                "type": "task_log_line",
                "task_id": task_id,
                "data": {"line": line, "timestamp": timestamp}
            })

    async def read_logs(self, task_id: int) -> str:
        log_path = self.get_log_path(task_id)
        if not log_path.exists():
            return ""
        async with aiofiles.open(log_path, "r") as f:
            return await f.read()
```

> **참고**: aiofiles 추가 필요 → `pyproject.toml`에 `"aiofiles>=24.0"` 추가

### 5-2. WebSocket Manager (`backend/app/api/websocket.py`)

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

router = APIRouter()

class WebSocketManager:
    def __init__(self):
        # task_id -> set of WebSocket connections
        self.connections: dict[int, set[WebSocket]] = {}
        # task_id=0 -> global subscribers (모든 태스크 상태 변경)
        self.global_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, task_id: int | None = None):
        await websocket.accept()
        if task_id:
            self.connections.setdefault(task_id, set()).add(websocket)
        else:
            self.global_connections.add(websocket)

    def disconnect(self, websocket: WebSocket, task_id: int | None = None):
        if task_id and task_id in self.connections:
            self.connections[task_id].discard(websocket)
        self.global_connections.discard(websocket)

    async def broadcast(self, task_id: int, message: dict):
        """task_id 구독자 + global 구독자 모두에게 전송"""
        data = json.dumps(message)
        targets = list(self.connections.get(task_id, set())) + list(self.global_connections)
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:
                pass  # 끊어진 연결은 무시

    async def broadcast_state_change(self, task_id: int, old_status: str, new_status: str):
        await self.broadcast(task_id, {
            "type": "task_state_changed",
            "task_id": task_id,
            "data": {"old_status": old_status, "new_status": new_status}
        })

ws_manager = WebSocketManager()  # 싱글턴

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, task_id: int | None = None):
    await ws_manager.connect(websocket, task_id)
    try:
        while True:
            await websocket.receive_text()  # keep-alive, 클라이언트 메시지 무시
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, task_id)
```

### 5-3. main.py에 WebSocket 라우터 등록

```python
from app.api.websocket import router as ws_router
app.include_router(ws_router)
```

### 검증

```bash
# WebSocket 테스트 (websocat 또는 wscat 사용)
pip install websockets
python -c "
import asyncio, websockets
async def test():
    async with websockets.connect('ws://localhost:8000/ws') as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print(msg)
asyncio.run(test())
"
# 또는
# websocat ws://localhost:8000/ws
```

---

## Phase 6: Orchestrator + Worker Pool (핵심)

### 6-1. Orchestrator (`backend/app/services/orchestrator.py`)

이것이 시스템의 핵심 상태 머신이다.

```python
class Orchestrator:
    def __init__(self, git_manager: GitManager, codex_agent: CodexAgent,
                 task_logger: TaskLogger, ws_manager: WebSocketManager,
                 session_factory):
        self.git = git_manager
        self.codex = codex_agent
        self.logger = task_logger
        self.ws = ws_manager
        self.session_factory = session_factory

    async def _update_status(self, session, task, new_status: TaskStatus):
        old = task.status
        task.status = new_status
        await session.commit()
        await self.ws.broadcast_state_change(task.id, old.value, new_status.value)
        await self.logger.log(task.id, f"Status: {old.value} -> {new_status.value}")

    async def process_task(self, task_id: int):
        """
        메인 태스크 처리 루프. 각 단계를 순차 실행.
        AWAIT_*_APPROVAL 상태에 도달하면 return (워커 해제).
        승인 후 resume_task()가 다시 호출됨.
        """
        async with self.session_factory() as session:
            task = await session.get(Task, task_id)
            repo = await session.get(Repo, task.repo_id)

            try:
                # Step 1: PREPARING_WORKSPACE
                if task.status == TaskStatus.PENDING:
                    await self._update_status(session, task, TaskStatus.PREPARING_WORKSPACE)
                    workspace = await self.git.create_worktree(
                        Path(repo.path), task.branch_name, task.id
                    )
                    task.workspace_path = str(workspace)
                    await session.commit()

                # Step 2: PLANNING
                if task.status == TaskStatus.PREPARING_WORKSPACE:
                    await self._update_status(session, task, TaskStatus.PLANNING)
                    log_cb = lambda line: self.logger.log(task.id, line)
                    exit_code, output = await self.codex.generate_plan(
                        Path(task.workspace_path), task.description, log_callback=log_cb
                    )
                    # Run 레코드 생성
                    run = Run(task_id=task.id, phase="plan", exit_code=exit_code,
                              log_path=str(self.logger.get_log_path(task.id)))
                    session.add(run)
                    if exit_code != 0:
                        raise RuntimeError(f"Plan generation failed: {output[-500:]}")
                    task.plan_text = output
                    await session.commit()

                # Step 3: AWAIT_PLAN_APPROVAL -> return, 사람 대기
                if task.status == TaskStatus.PLANNING:
                    await self._update_status(session, task, TaskStatus.AWAIT_PLAN_APPROVAL)
                    return  # ★ 워커 해제

                # Step 4: IMPLEMENTING (승인 후 resume에서 진입)
                if task.status in (TaskStatus.AWAIT_PLAN_APPROVAL, TaskStatus.IMPLEMENTING):
                    if task.status == TaskStatus.AWAIT_PLAN_APPROVAL:
                        # 이 경우는 resume에서 직접 호출된 것이 아니라면 skip
                        return
                    await self._update_status(session, task, TaskStatus.IMPLEMENTING)
                    log_cb = lambda line: self.logger.log(task.id, line)
                    exit_code, output = await self.codex.implement_plan(
                        Path(task.workspace_path), task.plan_text,
                        task.description, log_callback=log_cb
                    )
                    run = Run(task_id=task.id, phase="implement", exit_code=exit_code,
                              log_path=str(self.logger.get_log_path(task.id)))
                    session.add(run)
                    if exit_code != 0:
                        raise RuntimeError(f"Implementation failed: {output[-500:]}")

                # Step 5: TESTING
                if task.status == TaskStatus.IMPLEMENTING:
                    await self._update_status(session, task, TaskStatus.TESTING)
                    log_cb = lambda line: self.logger.log(task.id, line)
                    exit_code, output = await self.codex.run_tests(
                        Path(task.workspace_path), log_callback=log_cb
                    )
                    run = Run(task_id=task.id, phase="test", exit_code=exit_code,
                              log_path=str(self.logger.get_log_path(task.id)))
                    session.add(run)
                    # diff 생성
                    task.diff_text = await self.git.get_diff(
                        Path(task.workspace_path), repo.default_branch
                    )
                    await session.commit()

                # Step 6: AWAIT_MERGE_APPROVAL -> return
                if task.status == TaskStatus.TESTING:
                    await self._update_status(session, task, TaskStatus.AWAIT_MERGE_APPROVAL)
                    return  # ★ 워커 해제

                # Step 7: MERGING (승인 후 resume에서 진입)
                if task.status == TaskStatus.MERGING:
                    await self.logger.log(task.id, "Merging to main...")
                    success, msg = await self.git.merge_to_main(
                        Path(repo.path), task.branch_name
                    )
                    run = Run(task_id=task.id, phase="merge",
                              exit_code=0 if success else 1,
                              log_path=str(self.logger.get_log_path(task.id)))
                    session.add(run)
                    if not success:
                        raise RuntimeError(f"Merge failed: {msg}")
                    await self.git.cleanup_worktree(Path(repo.path), Path(task.workspace_path))
                    await self._update_status(session, task, TaskStatus.DONE)

            except Exception as e:
                await self.logger.log(task.id, f"ERROR: {str(e)}")
                task.error_message = str(e)
                if task.retry_count < 1:
                    task.retry_count += 1
                    task.status = TaskStatus.PENDING
                    await session.commit()
                    # worker에 재큐잉 (worker.enqueue 호출)
                else:
                    await self._update_status(session, task, TaskStatus.FAILED)

    async def resume_after_approval(self, task_id: int, phase: str):
        """승인 후 호출. 해당 단계부터 process_task 재개."""
        async with self.session_factory() as session:
            task = await session.get(Task, task_id)
            if phase == "plan" and task.status == TaskStatus.IMPLEMENTING:
                # Approved -> IMPLEMENTING 상태로 변경됨 (API에서)
                pass
            elif phase == "merge" and task.status == TaskStatus.MERGING:
                pass
        # worker에 enqueue
```

**주의**: 위 코드는 의사코드에 가까움. 실제 구현 시 status 체크 로직을 좀 더 단순하게 정리할 것. 핵심은:
- PENDING → ... → AWAIT_PLAN_APPROVAL에서 return (워커 해제)
- 승인 후 API가 status를 IMPLEMENTING으로 변경하고 resume
- IMPLEMENTING → ... → AWAIT_MERGE_APPROVAL에서 return
- 승인 후 API가 status를 MERGING으로 변경하고 resume

### 6-2. Worker Pool (`backend/app/services/worker.py`)

```python
class WorkerPool:
    def __init__(self, orchestrator: Orchestrator, max_concurrent: int = 6):
        self.orchestrator = orchestrator
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.repo_locks: dict[int, asyncio.Lock] = {}  # repo_id -> Lock
        self.queue: asyncio.Queue[int] = asyncio.Queue()  # task_id 큐
        self._running = False
        self._workers: list[asyncio.Task] = []

    def get_repo_lock(self, repo_id: int) -> asyncio.Lock:
        if repo_id not in self.repo_locks:
            self.repo_locks[repo_id] = asyncio.Lock()
        return self.repo_locks[repo_id]

    async def enqueue(self, task_id: int):
        await self.queue.put(task_id)

    async def start(self):
        self._running = True
        # 시작 시 비정상 상태 태스크 복구
        # PREPARING_WORKSPACE, PLANNING, IMPLEMENTING, TESTING, MERGING -> PENDING으로 리셋
        # PENDING 태스크들 큐에 추가
        self._workers = [asyncio.create_task(self._worker_loop()) for _ in range(12)]
        # 12개의 루프를 돌리지만 semaphore가 6개로 제한

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()

    async def _worker_loop(self):
        while self._running:
            task_id = await self.queue.get()
            async with self.semaphore:
                # task에서 repo_id 조회
                async with session_factory() as session:
                    task = await session.get(Task, task_id)
                    if not task or task.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                        continue
                    repo_id = task.repo_id

                repo_lock = self.get_repo_lock(repo_id)
                async with repo_lock:
                    try:
                        await self.orchestrator.process_task(task_id)
                    except Exception as e:
                        print(f"Worker error for task {task_id}: {e}")
```

### 6-3. Lifespan 연결 (`backend/app/main.py` 수정)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # 서비스 초기화
    from app.services.git_manager import GitManager
    from app.services.codex_agent import CodexAgent
    from app.services.logger import TaskLogger
    from app.api.websocket import ws_manager
    from app.services.orchestrator import Orchestrator
    from app.services.worker import WorkerPool

    git_mgr = GitManager(settings.WORKSPACES_DIR)
    codex = CodexAgent(settings.CODEX_COMMAND)
    task_logger = TaskLogger(settings.LOGS_DIR)
    task_logger.set_ws_manager(ws_manager)

    orchestrator = Orchestrator(git_mgr, codex, task_logger, ws_manager, async_session)
    worker_pool = WorkerPool(orchestrator)

    # app.state에 저장해서 API에서 접근 가능
    app.state.worker_pool = worker_pool
    app.state.orchestrator = orchestrator
    app.state.task_logger = task_logger

    await worker_pool.start()
    yield
    await worker_pool.stop()
```

### 6-4. API에서 Worker 연결

`tasks.py`의 POST /api/tasks에서:
```python
await request.app.state.worker_pool.enqueue(task.id)
```

approve-plan/approve-merge에서:
```python
if decision == "approved":
    await request.app.state.worker_pool.enqueue(task.id)
```

### 검증

```bash
# 1. 서버 시작
uvicorn app.main:app --reload --port 8000

# 2. 레포 등록
curl -X POST http://localhost:8000/api/repos \
  -H "Content-Type: application/json" \
  -d '{"name":"sample","path":"/home/planee/python/task_manager/repos/sample-project"}'

# 3. 태스크 생성 -> 자동으로 PREPARING_WORKSPACE -> PLANNING -> AWAIT_PLAN_APPROVAL
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"repo_id":1,"title":"Add logging","description":"Add logging module to main.py"}'

# 4. 태스크 상태 확인
curl http://localhost:8000/api/tasks/1
# status가 AWAIT_PLAN_APPROVAL이면 성공

# 5. 계획 승인
curl -X POST http://localhost:8000/api/tasks/1/approve-plan \
  -H "Content-Type: application/json" \
  -d '{"decision":"approved"}'

# 6. 자동으로 IMPLEMENTING -> TESTING -> AWAIT_MERGE_APPROVAL
curl http://localhost:8000/api/tasks/1
```

---

## Phase 7: Frontend 기반

### 7-1. API 클라이언트 (`dashboard/src/lib/api.ts`)

```typescript
const API_BASE = "http://localhost:8000/api";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// Repos
export const getRepos = () => fetchAPI<Repo[]>("/repos");
export const createRepo = (data: RepoCreate) =>
  fetchAPI<Repo>("/repos", { method: "POST", body: JSON.stringify(data) });

// Tasks
export const getTasks = (params?: { status?: string; repo_id?: number }) => {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.repo_id) sp.set("repo_id", String(params.repo_id));
  return fetchAPI<TaskSummary[]>(`/tasks?${sp}`);
};
export const getTask = (id: number) => fetchAPI<Task>(`/tasks/${id}`);
export const createTask = (data: TaskCreate) =>
  fetchAPI<Task>("/tasks", { method: "POST", body: JSON.stringify(data) });
export const approvePlan = (id: number, data: ApprovalReq) =>
  fetchAPI<Approval>(`/tasks/${id}/approve-plan`, { method: "POST", body: JSON.stringify(data) });
export const approveMerge = (id: number, data: ApprovalReq) =>
  fetchAPI<Approval>(`/tasks/${id}/approve-merge`, { method: "POST", body: JSON.stringify(data) });
export const cancelTask = (id: number) =>
  fetchAPI<void>(`/tasks/${id}/cancel`, { method: "POST" });
export const getTaskLogs = (id: number) =>
  fetch(`${API_BASE}/tasks/${id}/logs`).then(r => r.text());
```

### 7-2. 타입 정의 (`dashboard/src/lib/types.ts`)

```typescript
export type TaskStatus =
  | "PENDING" | "PREPARING_WORKSPACE" | "PLANNING"
  | "AWAIT_PLAN_APPROVAL" | "IMPLEMENTING" | "TESTING"
  | "AWAIT_MERGE_APPROVAL" | "MERGING" | "DONE" | "FAILED" | "CANCELLED";

export interface Repo { id: number; name: string; path: string; default_branch: string; created_at: string; }
export interface RepoCreate { name: string; path: string; default_branch?: string; }
export interface Task {
  id: number; repo_id: number; title: string; description: string;
  status: TaskStatus; branch_name: string | null; workspace_path: string | null;
  plan_text: string | null; diff_text: string | null;
  error_message: string | null; retry_count: number;
  created_at: string; updated_at: string;
}
export interface TaskSummary {
  id: number; repo_id: number; title: string; status: TaskStatus;
  created_at: string; updated_at: string;
}
export interface TaskCreate { repo_id: number; title: string; description?: string; }
export interface ApprovalReq { decision: "approved" | "rejected"; comment?: string; }
export interface Approval {
  id: number; task_id: number; phase: string;
  decision: string; comment: string | null; decided_at: string;
}
```

### 7-3. WebSocket 훅 (`dashboard/src/hooks/useWebSocket.ts`)

```typescript
import { useEffect, useRef, useCallback } from "react";

type WSMessage = {
  type: "task_state_changed" | "task_log_line";
  task_id: number;
  data: Record<string, string>;
};

export function useWebSocket(
  taskId?: number,
  onMessage?: (msg: WSMessage) => void
) {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const url = taskId
      ? `ws://localhost:8000/ws?task_id=${taskId}`
      : "ws://localhost:8000/ws";
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data) as WSMessage;
      onMessage?.(msg);
    };

    ws.onclose = () => {
      // 3초 후 재연결 (간단한 구현)
      setTimeout(() => { /* reconnect logic */ }, 3000);
    };

    return () => ws.close();
  }, [taskId]);

  return wsRef;
}
```

### 7-4. SWR 훅 (`dashboard/src/hooks/useTasks.ts`)

```typescript
import useSWR from "swr";
import { getTasks, getTask, getRepos } from "@/lib/api";

export function useTasks(params?: { status?: string; repo_id?: number }) {
  return useSWR(["tasks", params], () => getTasks(params));
}

export function useTask(id: number) {
  return useSWR(["task", id], () => getTask(id));
}

export function useRepos() {
  return useSWR("repos", getRepos);
}
```

### 7-5. 레이아웃 (`dashboard/src/app/layout.tsx`)

```
- 왼쪽 Sidebar: 네비게이션 (Tasks, Repos)
- 오른쪽 main: children 렌더링
- lucide-react 아이콘 사용
```

### 검증

```bash
cd dashboard && npm run dev
# localhost:3000 접속 -> 레이아웃 확인
```

---

## Phase 8: Frontend Task Board + Creation

### 8-1. Task Board (`dashboard/src/app/tasks/page.tsx`)

Kanban 보드 형태로 5개 컬럼:

| 컬럼 | 포함 상태 |
|------|-----------|
| Queued | PENDING, PREPARING_WORKSPACE |
| Working | PLANNING, IMPLEMENTING, TESTING, MERGING |
| Needs Approval | AWAIT_PLAN_APPROVAL, AWAIT_MERGE_APPROVAL |
| Done | DONE |
| Failed | FAILED, CANCELLED |

- `useTasks()` 훅으로 전체 태스크 목록 로드
- `useWebSocket()`으로 상태 변경 시 `mutate()` 호출하여 SWR 갱신
- 각 카드 클릭 시 `/tasks/{id}`로 이동

### 8-2. TaskCard 컴포넌트 (`dashboard/src/components/TaskCard.tsx`)

```
- title, status badge, created_at (relative time)
- StatusBadge: 상태별 색상 (green=done, yellow=approval, blue=working, red=failed)
- Link to /tasks/{id}
```

### 8-3. Task Creation (`dashboard/src/app/tasks/new/page.tsx`)

```
- RepoSelect: useRepos()로 드롭다운
- Title input
- Description textarea
- Submit -> createTask() -> router.push("/tasks")
```

### 8-4. StatusBadge 컴포넌트 (`dashboard/src/components/StatusBadge.tsx`)

```typescript
const STATUS_COLORS: Record<TaskStatus, string> = {
  PENDING: "bg-gray-100 text-gray-700",
  PREPARING_WORKSPACE: "bg-blue-100 text-blue-700",
  PLANNING: "bg-blue-100 text-blue-700",
  AWAIT_PLAN_APPROVAL: "bg-yellow-100 text-yellow-700",
  IMPLEMENTING: "bg-blue-100 text-blue-700",
  TESTING: "bg-blue-100 text-blue-700",
  AWAIT_MERGE_APPROVAL: "bg-yellow-100 text-yellow-700",
  MERGING: "bg-blue-100 text-blue-700",
  DONE: "bg-green-100 text-green-700",
  FAILED: "bg-red-100 text-red-700",
  CANCELLED: "bg-gray-100 text-gray-500",
};
```

### 검증

- 태스크 목록이 칸반 보드에 표시
- 새 태스크 생성 후 보드에 반영
- 실시간으로 상태 변경 시 카드 이동

---

## Phase 9: Frontend Approval + Log Streaming

### 9-1. Task Detail (`dashboard/src/app/tasks/[id]/page.tsx`)

```
구조:
- 상단: title, status badge, repo name, branch name, created_at
- 조건부 렌더링:
  - AWAIT_PLAN_APPROVAL -> PlanApproval 컴포넌트
  - AWAIT_MERGE_APPROVAL -> MergeApproval 컴포넌트
  - plan_text 있으면 -> Plan 섹션 (마크다운 또는 pre)
  - diff_text 있으면 -> DiffViewer 컴포넌트
  - error_message 있으면 -> 에러 표시
- 하단: LogStream 컴포넌트 (항상 표시)
- Cancel 버튼 (DONE/FAILED/CANCELLED 제외)
```

### 9-2. PlanApproval 컴포넌트 (`dashboard/src/components/PlanApproval.tsx`)

```
- plan_text 표시 (pre 태그, 스크롤)
- Comment textarea (선택)
- [Approve] [Reject] 버튼
- approvePlan(taskId, { decision, comment }) 호출
- 성공 시 mutate로 태스크 갱신
```

### 9-3. MergeApproval 컴포넌트 (`dashboard/src/components/MergeApproval.tsx`)

```
- DiffViewer로 diff_text 표시
- Comment textarea (선택)
- [Approve Merge] [Reject] 버튼
- approveMerge(taskId, { decision, comment }) 호출
```

### 9-4. DiffViewer 컴포넌트 (`dashboard/src/components/DiffViewer.tsx`)

```typescript
import ReactDiffViewer from "react-diff-viewer-continued";

// diff_text는 unified diff 형식이므로 파싱 필요
// 간단한 구현: <pre> 태그로 표시
// 고급 구현: unified diff를 old/new로 분리하여 ReactDiffViewer에 전달

// 가장 실용적: unified diff를 그대로 <pre>로 표시하되 색상 처리
// + 라인: green, - 라인: red, @@ 라인: blue
```

### 9-5. LogStream 컴포넌트 (`dashboard/src/components/LogStream.tsx`)

```
- 초기 로드: getTaskLogs(taskId)로 기존 로그 불러오기
- useWebSocket(taskId)로 실시간 로그 추가
- task_log_line 이벤트 수신 시 로그 배열에 append
- auto-scroll to bottom
- 모노스페이스 폰트, dark 배경
- max-height: 500px, overflow-y: scroll
```

### 검증 (E2E 플로우)

```
1. 레포 등록 (이미 되어있으면 skip)
2. 태스크 생성: "Add a calculator module"
3. 보드에서 Working -> Needs Approval로 이동 확인
4. 태스크 클릭 -> Plan 확인 -> Approve
5. Working으로 이동 -> Needs Approval (merge)로 이동 확인
6. Diff 확인 -> Approve Merge
7. Done으로 이동 확인
8. 로그가 실시간으로 스트리밍되는지 확인
```

---

## Phase 10: Polish

### 10-1. 에러 처리 개선

- API 에러 시 프론트에서 toast/alert 표시
- Codex 실행 실패 시 error_message에 상세 기록
- 네트워크 에러 시 자동 재시도 (SWR 기본 옵션)

### 10-2. 취소 기능

- Cancel 버튼 클릭 시 `cancelTask(id)` 호출
- 실행 중인 codex subprocess가 있다면 terminate
- WorkerPool에서 cancellation token 패턴 구현 (선택적)

### 10-3. Repo 관리 페이지 (`dashboard/src/app/repos/page.tsx`)

```
- 레포 목록 테이블 (이름, 경로, default branch, 등록일)
- 레포 등록 폼 (이름, 경로, default branch)
- 경로는 서버 로컬 경로 (예: /home/planee/projects/my-app)
```

### 10-4. 추가 테스트 레포

```bash
cd /home/planee/python/task_manager/repos
# 더 복잡한 프로젝트 생성
mkdir python-web-app && cd python-web-app
git init && git checkout -b main
# Flask app 등 간단한 프로젝트 세팅
```

### 10-5. 시작 스크립트

**파일: `start.sh`**
```bash
#!/bin/bash
echo "Starting AI Dev Automation Dashboard..."

# Backend
cd /home/planee/python/task_manager/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Frontend
cd /home/planee/python/task_manager/dashboard
npm run dev &
FRONTEND_PID=$!

echo "Backend: http://localhost:8000"
echo "Dashboard: http://localhost:3000"
echo "Press Ctrl+C to stop"

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
```

---

## 의존성 요약

### Backend (`backend/pyproject.toml`)

| 패키지 | 용도 |
|--------|------|
| fastapi[standard] | API 프레임워크 |
| sqlalchemy[asyncio] | ORM (async) |
| aiosqlite | SQLite async 드라이버 |
| aiofiles | 비동기 파일 I/O (로깅) |
| pydantic | 데이터 검증 |
| pydantic-settings | 설정 관리 |
| uvicorn[standard] | ASGI 서버 |
| websockets | WebSocket 지원 |
| httpx | HTTP 클라이언트 (테스트) |
| pytest / pytest-asyncio | 테스트 |

### Frontend (`dashboard/package.json`)

| 패키지 | 용도 |
|--------|------|
| next | React 프레임워크 |
| react | UI |
| tailwindcss | 스타일링 |
| swr | 데이터 페칭 + 캐시 |
| react-diff-viewer-continued | Diff 표시 |
| lucide-react | 아이콘 |

### 외부 도구

| 도구 | 용도 |
|------|------|
| codex CLI | AI 코딩 에이전트 (npm i -g @openai/codex) |
| git | 버전 관리 + worktree |

---

## 핵심 설계 포인트 요약

1. **상태 머신이 핵심**: Orchestrator.process_task()가 PENDING → DONE까지 전체 플로우 관리
2. **AWAIT 상태에서 워커 해제**: approval 대기 시 워커를 점유하지 않음
3. **레포당 1개 태스크**: repo_lock으로 동일 레포 병렬 실행 방지
4. **WebSocket 이중 구독**: task_id별 + global (보드용)
5. **Codex는 단순 subprocess**: `codex --quiet --full-auto -p "prompt"` 실행
6. **retry 1회**: 실패 시 1번 재시도 후 FAILED
7. **Git worktree**: 태스크별 독립 작업 공간, 완료 후 정리
