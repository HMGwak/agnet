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


async def init_db():
    async with engine.begin() as conn:
        from app.models import Approval, Repo, Run, Task  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_task_columns)


async def get_db():
    async with async_session() as session:
        yield session
