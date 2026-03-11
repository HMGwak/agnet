from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def _ensure_task_columns(conn):
    columns = {
        row[1]
        for row in conn.exec_driver_sql("PRAGMA table_info(tasks)").fetchall()
    }

    if "scheduled_for" not in columns:
        conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN scheduled_for DATETIME")

    if "blocked_by_task_id" not in columns:
        conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN blocked_by_task_id INTEGER")

    if "workspace_id" not in columns:
        conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN workspace_id INTEGER")

    if "exploration_text" not in columns:
        conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN exploration_text TEXT")


def _ensure_workspaces(conn):
    repo_columns = {
        row[1]
        for row in conn.exec_driver_sql("PRAGMA table_info(repos)").fetchall()
    }
    task_columns = {
        row[1]
        for row in conn.exec_driver_sql("PRAGMA table_info(tasks)").fetchall()
    }
    if "id" not in repo_columns or "workspace_id" not in task_columns:
        return

    repo_rows = conn.exec_driver_sql(
        "SELECT id, default_branch FROM repos ORDER BY id"
    ).fetchall()

    for repo_id, default_branch in repo_rows:
        existing = conn.exec_driver_sql(
            "SELECT id FROM workspaces WHERE repo_id = ? AND kind = ? LIMIT 1",
            (repo_id, "MAIN"),
        ).fetchone()
        if existing is None:
            cursor = conn.exec_driver_sql(
                """
                INSERT INTO workspaces
                (repo_id, name, kind, base_branch, branch_name, workspace_path, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repo_id,
                    "Main",
                    "MAIN",
                    default_branch or "main",
                    f"workspace/main/{repo_id}",
                    None,
                    1,
                ),
            )
            workspace_id = cursor.lastrowid
        else:
            workspace_id = existing[0]

        conn.exec_driver_sql(
            "UPDATE tasks SET workspace_id = ? WHERE repo_id = ? AND workspace_id IS NULL",
            (workspace_id, repo_id),
        )


async def init_db():
    async with engine.begin() as conn:
        from app.models import Approval, Repo, Run, Task, Workspace  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_task_columns)
        await conn.run_sync(_ensure_workspaces)


async def get_db():
    async with async_session() as session:
        yield session
