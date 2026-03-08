from datetime import datetime
from pathlib import Path

import aiofiles


class TaskLogger:
    def __init__(self, session_logs_dir: Path):
        self.session_logs_dir = session_logs_dir
        self.tasks_dir = session_logs_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._ws_manager: "WebSocketManager | None" = None  # noqa: F821

    def set_ws_manager(self, manager):
        self._ws_manager = manager

    def get_log_path(self, task_id: int) -> Path:
        return self.tasks_dir / f"task-{task_id}.log"

    async def log(self, task_id: int, line: str):
        timestamp = datetime.now().isoformat()
        log_line = f"[{timestamp}] {line}\n"
        log_path = self.get_log_path(task_id)
        async with aiofiles.open(log_path, "a") as f:
            await f.write(log_line)
        if self._ws_manager:
            await self._ws_manager.broadcast(task_id, {
                "type": "task_log_line",
                "task_id": task_id,
                "data": {"line": line, "timestamp": timestamp},
            })

    async def read_logs(self, task_id: int) -> str:
        log_path = self.get_log_path(task_id)
        if not log_path.exists():
            return ""
        async with aiofiles.open(log_path, "r") as f:
            return await f.read()
