from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent  # task_manager/
    DATABASE_URL: str = ""
    REPOS_DIR: Path = Path("")
    WORKSPACES_DIR: Path = Path("")
    LOGS_DIR: Path = Path("")
    MAX_CONCURRENT_TASKS: int = 6
    CODEX_MODEL: str = "gpt-5.4"
    CODEX_SANDBOX_MODE: str = "workspace-write"
    CODEX_APPROVAL_POLICY: str = "never"
    CODEX_RUN_TIMEOUT_S: int = 300
    CODEX_SIDECAR_HOST: str = "127.0.0.1"
    CODEX_SIDECAR_PORT: int = 8765
    CODEX_SIDECAR_DIR: Path = Path("")
    CODEX_SDK_DIR: Path = Path("")
    CODEX_SDK_HOME: Path = Path("")
    CODEX_POLICY_FILE: Path = Path("")
    CODEX_PROMPTS_DIR: Path = Path("")
    CODEX_PROJECT_DIR: Path = Path("")

    def model_post_init(self, __context):
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"sqlite+aiosqlite:///{self.BASE_DIR / 'database' / 'dev.db'}"
            )
        if self.REPOS_DIR == Path(""):
            self.REPOS_DIR = self.BASE_DIR / "repos"
        if self.WORKSPACES_DIR == Path(""):
            self.WORKSPACES_DIR = self.BASE_DIR / "workspaces"
        if self.LOGS_DIR == Path(""):
            self.LOGS_DIR = self.BASE_DIR / "logs"
        if self.CODEX_SIDECAR_DIR == Path(""):
            for candidate in (
                self.BASE_DIR / "codex-sidecar",
                self.BASE_DIR / "runtime" / "codex-sidecar",
                self.BASE_DIR / "resources" / "runtime" / "codex-sidecar",
            ):
                if candidate.exists():
                    self.CODEX_SIDECAR_DIR = candidate
                    break
            else:
                self.CODEX_SIDECAR_DIR = self.BASE_DIR / "codex-sidecar"
        if self.CODEX_SDK_DIR == Path(""):
            self.CODEX_SDK_DIR = self.BASE_DIR / ".codex-sdk"
        if self.CODEX_SDK_HOME == Path(""):
            self.CODEX_SDK_HOME = self.CODEX_SDK_DIR / "home"
        if self.CODEX_POLICY_FILE == Path(""):
            for candidate in (
                self.BASE_DIR / "codex-policy.toml",
                self.BASE_DIR / "runtime" / "codex-policy.toml",
                self.BASE_DIR / "resources" / "runtime" / "codex-policy.toml",
            ):
                if candidate.exists():
                    self.CODEX_POLICY_FILE = candidate
                    break
            else:
                self.CODEX_POLICY_FILE = self.BASE_DIR / "codex-policy.toml"
        if self.CODEX_PROMPTS_DIR == Path(""):
            for candidate in (
                self.BASE_DIR / "backend" / "app" / "prompts",
                self.BASE_DIR / "runtime" / "prompts",
                self.BASE_DIR / "resources" / "runtime" / "prompts",
            ):
                if candidate.exists():
                    self.CODEX_PROMPTS_DIR = candidate
                    break
            else:
                self.CODEX_PROMPTS_DIR = self.BASE_DIR / "backend" / "app" / "prompts"
        if self.CODEX_PROJECT_DIR == Path(""):
            for candidate in (
                self.BASE_DIR / ".codex",
                self.BASE_DIR / "runtime" / ".codex",
                self.BASE_DIR / "resources" / "runtime" / ".codex",
            ):
                if candidate.exists():
                    self.CODEX_PROJECT_DIR = candidate
                    break
            else:
                self.CODEX_PROJECT_DIR = self.BASE_DIR / ".codex"

    @property
    def CODEX_SIDECAR_ENTRYPOINT(self) -> Path:
        return self.CODEX_SIDECAR_DIR / "server.mjs"

    @property
    def CODEX_SDK_AUTH_FILE(self) -> Path:
        return self.CODEX_SDK_HOME / "auth.json"

    @property
    def CODEX_SDK_CONFIG_FILE(self) -> Path:
        return self.CODEX_SDK_HOME / "config.toml"

    @property
    def CODEX_PROJECT_CONFIG_FILE(self) -> Path:
        return self.CODEX_PROJECT_DIR / "config.toml"


settings = Settings()
