from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    PROJECT_DATA_DIR: Path = Path("")
    DATABASE_URL: str = ""
    REPOS_DIR: Path = Path("")
    WORKSPACES_DIR: Path = Path("")
    LOGS_DIR: Path = Path("")
    SESSION_ID: str = ""
    SESSION_LOGS_DIR: Path = Path("")
    MAX_CONCURRENT_TASKS: int = 6
    CODEX_MODEL: str = "gpt-5.4"
    CODEX_SANDBOX_MODE: str = "workspace-write"
    CODEX_WINDOWS_UNSANDBOXED_WORKAROUND: bool = True
    CODEX_APPROVAL_POLICY: str = "never"
    CODEX_RUN_TIMEOUT_S: int = 300
    CODEX_SIDECAR_HOST: str = "127.0.0.1"
    CODEX_SIDECAR_PORT: int = 8765
    CODEX_SIDECAR_DIR: Path = Path("")
    CODEX_HOME_DIR: Path = Path("")
    CODEX_POLICY_FILE: Path = Path("")
    CODEX_PROMPTS_DIR: Path = Path("")
    CODEX_CONTRACT_DIR: Path = Path("")
    CODEX_GENERATED_DIR: Path = Path("")

    def model_post_init(self, __context):
        runtime_codex_dir = self.BASE_DIR / "runtime" / "codex"
        if self.PROJECT_DATA_DIR == Path(""):
            self.PROJECT_DATA_DIR = self.BASE_DIR / "project"
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"sqlite+aiosqlite:///{self.PROJECT_DATA_DIR / 'database' / 'dev.db'}"
            )
        if self.REPOS_DIR == Path(""):
            self.REPOS_DIR = self.PROJECT_DATA_DIR / "repos"
        if self.WORKSPACES_DIR == Path(""):
            self.WORKSPACES_DIR = self.PROJECT_DATA_DIR / "workspaces"
        if self.LOGS_DIR == Path(""):
            self.LOGS_DIR = self.PROJECT_DATA_DIR / "logs"
        if self.SESSION_LOGS_DIR == Path(""):
            self.SESSION_LOGS_DIR = self.LOGS_DIR
        if not self.SESSION_ID:
            self.SESSION_ID = self.SESSION_LOGS_DIR.name
        if self.CODEX_SIDECAR_DIR == Path(""):
            self.CODEX_SIDECAR_DIR = runtime_codex_dir / "sidecar"
        if self.CODEX_HOME_DIR == Path(""):
            self.CODEX_HOME_DIR = runtime_codex_dir / "home"
        if self.CODEX_POLICY_FILE == Path(""):
            self.CODEX_POLICY_FILE = runtime_codex_dir / "policy.toml"
        if self.CODEX_PROMPTS_DIR == Path(""):
            self.CODEX_PROMPTS_DIR = runtime_codex_dir / "prompts"
        if self.CODEX_CONTRACT_DIR == Path(""):
            self.CODEX_CONTRACT_DIR = runtime_codex_dir / "contract"
        if self.CODEX_GENERATED_DIR == Path(""):
            self.CODEX_GENERATED_DIR = runtime_codex_dir / "generated"

    @property
    def CODEX_SIDECAR_ENTRYPOINT(self) -> Path:
        return self.CODEX_SIDECAR_DIR / "server.mjs"

    @property
    def CODEX_AUTH_FILE(self) -> Path:
        return self.CODEX_HOME_DIR / "auth.json"

    @property
    def CODEX_HOME_CONFIG_FILE(self) -> Path:
        return self.CODEX_HOME_DIR / "config.toml"

    @property
    def CODEX_CONTRACT_CONFIG_FILE(self) -> Path:
        return self.CODEX_CONTRACT_DIR / "config.toml"

    @property
    def TASK_LOGS_DIR(self) -> Path:
        return self.SESSION_LOGS_DIR / "tasks"

    @property
    def LOGS_LATEST_MARKER(self) -> Path:
        return self.LOGS_DIR / "latest"

    @property
    def SESSION_METADATA_FILE(self) -> Path:
        return self.SESSION_LOGS_DIR / "session.json"


settings = Settings()
