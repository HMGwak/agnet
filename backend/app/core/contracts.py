from __future__ import annotations

from pathlib import Path
from typing import Protocol


class TaskStore(Protocol):
    async def attach_task_metadata(self, db, tasks: list[object]) -> None: ...


class WorkspaceManager(Protocol):
    async def create_worktree(
        self,
        repo_path: Path,
        branch_name: str,
        workspace_id: int,
        repo_id: int | None = None,
        repo_name: str | None = None,
        workspace_name: str | None = None,
        base_branch: str = "main",
    ) -> Path: ...
    async def cleanup_worktree(self, repo_path: Path, workspace_path: Path) -> None: ...
    async def get_diff(self, workspace_path: Path, base_branch: str = "main") -> str: ...
    async def merge_to_main(
        self,
        repo_path: Path,
        branch_name: str,
        base_branch: str = "main",
    ) -> tuple[bool, str]: ...
    async def ensure_repository(self, repo_path: Path, default_branch: str = "main") -> None: ...


class AgentRunner(Protocol):
    def format_task_input(self, task_title: str, task_description: str) -> str: ...
    async def cancel(self, task_id: int) -> None: ...
    async def generate_plan(self, workspace_path: Path, task_description: str, **kw) -> tuple[int, str]: ...
    async def critique_plan(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        **kw,
    ) -> tuple[int, str]: ...
    async def implement_plan(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        **kw,
    ) -> tuple[int, str]: ...
    async def run_tests(self, workspace_path: Path, **kw) -> tuple[int, str]: ...
    async def review_result(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        test_output: str,
        diff_text: str,
        **kw,
    ) -> tuple[int, str]: ...


class EventSink(Protocol):
    def get_log_path(self, task_id: int) -> Path: ...
    async def log(self, task_id: int, line: str) -> None: ...
    async def broadcast_state_change(self, task_id: int, old_status: str, new_status: str) -> None: ...
    async def broadcast_task_deleted(self, task_id: int) -> None: ...


class WorkflowEngine(Protocol):
    async def process_task(self, task_id: int) -> None: ...
