import asyncio
import os
import shlex
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path


class CodexAgent:
    def __init__(self, codex_command: str = "codex"):
        self.codex_command = codex_command
        self._processes: dict[int, asyncio.subprocess.Process] = {}  # task_id -> proc

    def _resolve_command(self) -> list[str]:
        parts = shlex.split(self.codex_command, posix=os.name != "nt")
        if not parts:
            raise RuntimeError("CODEX_COMMAND is empty")

        executable = parts[0]
        resolved = None
        suffix = Path(executable).suffix.lower()

        if os.name == "nt" and not suffix:
            for ext in (".cmd", ".exe", ".bat", ".ps1"):
                resolved = shutil.which(executable + ext)
                if resolved:
                    break

        if not resolved:
            resolved = shutil.which(executable) or executable

        if Path(resolved).suffix.lower() == ".ps1":
            return [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                resolved,
                *parts[1:],
            ]

        return [resolved, *parts[1:]]

    async def cancel(self, task_id: int):
        proc = self._processes.pop(task_id, None)
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()

    async def run_codex(
        self,
        prompt: str,
        cwd: Path,
        log_callback: Callable[[str], Awaitable[None]] | None = None,
        task_id: int | None = None,
    ) -> tuple[int, str]:
        command = self._resolve_command()
        proc = await asyncio.create_subprocess_exec(
            *command, "--quiet", "--full-auto", "-p", prompt,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        if task_id is not None:
            self._processes[task_id] = proc

        lines: list[str] = []
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode(errors="replace").rstrip("\n")
            lines.append(line)
            if log_callback:
                await log_callback(line)

        await proc.wait()
        self._processes.pop(task_id, None)
        return proc.returncode or 0, "\n".join(lines)

    async def generate_plan(
        self, workspace_path: Path, task_description: str, **kw
    ) -> tuple[int, str]:
        prompt = (
            "Analyze this repository and create a detailed implementation plan "
            "for the following task.\n"
            "Do NOT modify any files. Output ONLY a numbered step-by-step plan.\n\n"
            f"Task: {task_description}"
        )
        return await self.run_codex(prompt, cwd=workspace_path, **kw)

    async def implement_plan(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        **kw,
    ) -> tuple[int, str]:
        prompt = (
            "Implement the following plan in this repository.\n"
            "Make all necessary code changes and commit them.\n\n"
            f"Original task: {task_description}\n\n"
            f"Plan:\n{plan_text}"
        )
        return await self.run_codex(prompt, cwd=workspace_path, **kw)

    async def run_tests(self, workspace_path: Path, **kw) -> tuple[int, str]:
        prompt = (
            "Run the project's test suite. If any tests fail, fix the issues "
            "and re-run until they pass. Commit any fixes."
        )
        return await self.run_codex(prompt, cwd=workspace_path, **kw)
