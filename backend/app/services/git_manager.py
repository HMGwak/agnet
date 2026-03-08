import asyncio
import contextlib
import os
import stat
import shutil
from pathlib import Path

from app.core.policies import slugify


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

    async def ensure_repository(self, repo_path: Path, default_branch: str = "main"):
        if (repo_path / ".git").exists():
            return

        rc, _, err = await self._run_git("init", "-b", default_branch, cwd=repo_path)
        if rc != 0:
            raise RuntimeError(f"Failed to initialize git repository: {err.strip()}")

        await self._ensure_identity(repo_path)

        placeholder_path = repo_path / ".gitkeep"
        has_files_to_commit = any(path.name != ".git" for path in repo_path.iterdir())
        if not has_files_to_commit:
            placeholder_path.write_text("", encoding="utf-8")

        rc, _, err = await self._run_git("add", ".", cwd=repo_path)
        if rc != 0:
            raise RuntimeError(f"Failed to stage initial repository files: {err.strip()}")

        rc, out, err = await self._run_git("status", "--porcelain", cwd=repo_path)
        if rc != 0:
            raise RuntimeError(f"Failed to inspect repository status: {err.strip()}")

        if out.strip():
            rc, _, err = await self._run_git(
                "commit", "-m", "Initial commit", cwd=repo_path
            )
            if rc != 0:
                raise RuntimeError(f"Failed to create initial commit: {err.strip()}")

    async def _ensure_identity(self, repo_path: Path):
        rc, out, _ = await self._run_git("config", "user.name", cwd=repo_path)
        if rc != 0 or not out.strip():
            rc, _, err = await self._run_git(
                "config", "user.name", "AI Dev Automation", cwd=repo_path
            )
            if rc != 0:
                raise RuntimeError(f"Failed to configure git user.name: {err.strip()}")

        rc, out, _ = await self._run_git("config", "user.email", cwd=repo_path)
        if rc != 0 or not out.strip():
            rc, _, err = await self._run_git(
                "config", "user.email", "ai-dev-automation@example.invalid", cwd=repo_path
            )
            if rc != 0:
                raise RuntimeError(f"Failed to configure git user.email: {err.strip()}")

    def _handle_remove_readonly(self, func, path, exc_info):
        with contextlib.suppress(FileNotFoundError):
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            func(path)

    def _remove_tree_force(self, workspace_path: Path) -> None:
        if not workspace_path.exists():
            return
        shutil.rmtree(workspace_path, onerror=self._handle_remove_readonly)

    def _slug(self, text: str, max_length: int = 40) -> str:
        return slugify(text)[:max_length]

    def _segment(self, prefix: str, identifier: int, label: str | None = None) -> str:
        slug = self._slug(label or "")
        if slug:
            return f"{prefix}-{identifier}-{slug}"
        return f"{prefix}-{identifier}"

    def _workspace_path(
        self,
        workspace_id: int,
        repo_id: int | None = None,
        repo_name: str | None = None,
        workspace_name: str | None = None,
    ) -> Path:
        workspace_dir = self._segment("workspace", workspace_id, workspace_name)
        if repo_id is None:
            return self.workspaces_dir / workspace_dir
        repo_dir = self._segment("repo", repo_id, repo_name)
        return self.workspaces_dir / repo_dir / workspace_dir

    async def create_worktree(
        self,
        repo_path: Path,
        branch_name: str,
        workspace_id: int,
        repo_id: int | None = None,
        repo_name: str | None = None,
        workspace_name: str | None = None,
        base_branch: str = "main",
    ) -> Path:
        workspace_path = self._workspace_path(workspace_id, repo_id, repo_name, workspace_name)

        workspace_path.parent.mkdir(parents=True, exist_ok=True)

        if workspace_path.exists():
            await self.cleanup_worktree(repo_path, workspace_path)

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
                "-C",
                str(repo_path),
                "worktree",
                "add",
                "-b",
                branch_name,
                str(workspace_path),
                base_branch,
            )

        if rc != 0:
            raise RuntimeError(f"Failed to create worktree: {err}")

        return workspace_path

    async def get_diff(self, workspace_path: Path, base_branch: str = "main") -> str:
        rc, out, err = await self._run_git(
            "-C", str(workspace_path), "diff", f"{base_branch}...HEAD"
        )
        return out

    async def has_working_tree_changes(self, workspace_path: Path) -> bool:
        rc, out, err = await self._run_git(
            "-C",
            str(workspace_path),
            "status",
            "--short",
            "--untracked-files=all",
        )
        if rc != 0:
            raise RuntimeError(f"Failed to inspect worktree changes: {err.strip()}")
        return bool(out.strip())

    async def merge_to_main(
        self,
        repo_path: Path,
        branch_name: str,
        base_branch: str = "main",
    ) -> tuple[bool, str]:
        rc, _, err = await self._run_git("-C", str(repo_path), "checkout", base_branch)
        if rc != 0:
            return False, f"Failed to checkout {base_branch}: {err}"

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
        await self._run_git("-C", str(repo_path), "worktree", "prune")
        if workspace_path.exists():
            with contextlib.suppress(FileNotFoundError):
                self._remove_tree_force(workspace_path)
        with contextlib.suppress(OSError):
            workspace_path.parent.rmdir()
