import asyncio
import shutil
from pathlib import Path


class GitManager:
    def __init__(self, workspaces_dir: Path):
        self.workspaces_dir = workspaces_dir
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)

    async def _run_git(self, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode or 0, stdout.decode(), stderr.decode()

    async def create_worktree(self, repo_path: Path, branch_name: str, task_id: int) -> Path:
        workspace_path = self.workspaces_dir / f"task-{task_id}"

        # Check if branch already exists
        rc, out, _ = await self._run_git(
            "-C", str(repo_path), "branch", "--list", branch_name
        )
        branch_exists = bool(out.strip())

        if branch_exists:
            rc, out, err = await self._run_git(
                "-C", str(repo_path), "worktree", "add", str(workspace_path), branch_name
            )
        else:
            rc, out, err = await self._run_git(
                "-C", str(repo_path), "worktree", "add", "-b", branch_name, str(workspace_path)
            )

        if rc != 0:
            raise RuntimeError(f"Failed to create worktree: {err}")

        return workspace_path

    async def get_diff(self, workspace_path: Path, base_branch: str = "main") -> str:
        rc, out, err = await self._run_git(
            "-C", str(workspace_path), "diff", f"{base_branch}...HEAD"
        )
        return out

    async def merge_to_main(self, repo_path: Path, branch_name: str) -> tuple[bool, str]:
        rc, _, err = await self._run_git("-C", str(repo_path), "checkout", "main")
        if rc != 0:
            return False, f"Failed to checkout main: {err}"

        rc, out, err = await self._run_git(
            "-C", str(repo_path), "merge", "--no-ff", branch_name, "-m", f"Merge {branch_name}"
        )
        if rc != 0:
            # Abort failed merge
            await self._run_git("-C", str(repo_path), "merge", "--abort")
            return False, f"Merge failed: {err}"

        return True, out

    async def cleanup_worktree(self, repo_path: Path, workspace_path: Path):
        await self._run_git(
            "-C", str(repo_path), "worktree", "remove", str(workspace_path), "--force"
        )
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
