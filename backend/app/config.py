from pathlib import Path

from pydantic_settings import BaseSettings


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
            self.DATABASE_URL = (
                f"sqlite+aiosqlite:///{self.BASE_DIR / 'database' / 'dev.db'}"
            )
        if self.REPOS_DIR == Path(""):
            self.REPOS_DIR = self.BASE_DIR / "repos"
        if self.WORKSPACES_DIR == Path(""):
            self.WORKSPACES_DIR = self.BASE_DIR / "workspaces"
        if self.LOGS_DIR == Path(""):
            self.LOGS_DIR = self.BASE_DIR / "logs"


settings = Settings()
