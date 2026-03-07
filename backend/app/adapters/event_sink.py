from __future__ import annotations


class AppEventSink:
    def __init__(self, task_logger, ws_manager):
        self.task_logger = task_logger
        self.ws_manager = ws_manager

    def get_log_path(self, task_id: int):
        return self.task_logger.get_log_path(task_id)

    async def log(self, task_id: int, line: str):
        await self.task_logger.log(task_id, line)

    async def broadcast_state_change(self, task_id: int, old_status: str, new_status: str):
        await self.ws_manager.broadcast_state_change(task_id, old_status, new_status)

    async def broadcast_task_deleted(self, task_id: int):
        await self.ws_manager.broadcast_task_deleted(task_id)
