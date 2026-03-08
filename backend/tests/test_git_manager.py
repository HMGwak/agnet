import subprocess
import stat

import pytest

from app.services.git_manager import GitManager


@pytest.fixture
def temp_repo(tmp_path):
    repo = tmp_path / "test-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.mark.asyncio
async def test_create_worktree_uses_workspace_scoped_path(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(
        temp_repo,
        "workspace/1/main",
        1,
        repo_id=11,
        repo_name="Demo Repo",
        workspace_name="Main",
        base_branch="main",
    )
    assert ws.exists()
    assert (ws / "README.md").exists()
    assert ws == tmp_path / "workspaces" / "repo-11-demo-repo" / "workspace-1-main"


@pytest.mark.asyncio
async def test_create_worktree_existing_branch(temp_repo, tmp_path):
    subprocess.run(
        ["git", "branch", "workspace/3/existing"], cwd=temp_repo, check=True, capture_output=True
    )
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(
        temp_repo,
        "workspace/3/existing",
        3,
        repo_id=11,
        repo_name="Demo Repo",
        workspace_name="Existing",
        base_branch="main",
    )
    assert ws.exists()
    assert ws == tmp_path / "workspaces" / "repo-11-demo-repo" / "workspace-3-existing"


@pytest.mark.asyncio
async def test_create_worktree_uses_ascii_safe_path_for_unicode_workspace_name(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(
        temp_repo,
        "workspace/7/task-a1b2c3d4",
        7,
        repo_id=11,
        repo_name="Demo Repo",
        workspace_name="테트리스 게임 만들기",
        base_branch="main",
    )
    assert ws.exists()
    assert ws.parent == tmp_path / "workspaces" / "repo-11-demo-repo"
    assert ws.name.startswith("workspace-7-task-")
    assert "테트리스" not in ws.name


@pytest.mark.asyncio
async def test_get_diff(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(
        temp_repo,
        "workspace/4/diff-test",
        4,
        repo_id=11,
        repo_name="Demo Repo",
        workspace_name="Diff Test",
        base_branch="main",
    )
    (ws / "new_file.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "add file"],
        cwd=ws, check=True, capture_output=True,
    )
    diff = await gm.get_diff(ws)
    assert "new_file.py" in diff


@pytest.mark.asyncio
async def test_has_working_tree_changes_ignores_windows_placeholder_artifacts(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(
        temp_repo,
        "workspace/9/ignore-artifact",
        9,
        repo_id=11,
        repo_name="Demo Repo",
        workspace_name="Ignore Artifact",
        base_branch="main",
    )
    artifact = ws / "%SystemDrive%" / "ProgramData" / "artifact.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("noise", encoding="utf-8")

    assert await gm.has_working_tree_changes(ws) is False


@pytest.mark.asyncio
async def test_commit_workspace_changes_ignores_windows_placeholder_artifacts(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(
        temp_repo,
        "workspace/10/commit-test",
        10,
        repo_id=11,
        repo_name="Demo Repo",
        workspace_name="Commit Test",
        base_branch="main",
    )
    (ws / "README.md").write_text("# Updated", encoding="utf-8")
    artifact = ws / "%SystemDrive%" / "ProgramData" / "artifact.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("noise", encoding="utf-8")

    committed = await gm.commit_workspace_changes(ws, "Task #10: Update README")

    assert committed is True
    diff = await gm.get_diff(ws)
    assert "README.md" in diff
    assert "%SystemDrive%" not in diff


@pytest.mark.asyncio
async def test_merge_to_main_uses_base_branch(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(
        temp_repo,
        "workspace/2/feature",
        2,
        repo_id=11,
        repo_name="Demo Repo",
        workspace_name="Feature",
        base_branch="main",
    )
    (ws / "new_file.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "add file"],
        cwd=ws, check=True, capture_output=True,
    )
    success, msg = await gm.merge_to_main(temp_repo, "workspace/2/feature", "main")
    assert success


@pytest.mark.asyncio
async def test_cleanup_worktree(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(
        temp_repo,
        "workspace/5/cleanup",
        5,
        repo_id=11,
        repo_name="Demo Repo",
        workspace_name="Cleanup",
        base_branch="main",
    )
    assert ws.exists()
    await gm.cleanup_worktree(temp_repo, ws)
    assert not ws.exists()
    assert not (tmp_path / "workspaces" / "repo-11-demo-repo").exists()


@pytest.mark.asyncio
async def test_create_worktree_cleans_existing_workspace_dir(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    stale_workspace = tmp_path / "workspaces" / "repo-11-demo-repo" / "workspace-6-recreated"
    stale_workspace.mkdir(parents=True)
    (stale_workspace / "stale.txt").write_text("stale")

    ws = await gm.create_worktree(
        temp_repo,
        "workspace/6/recreated",
        6,
        repo_id=11,
        repo_name="Demo Repo",
        workspace_name="Recreated",
        base_branch="main",
    )

    assert ws.exists()
    assert not (ws / "stale.txt").exists()


@pytest.mark.asyncio
async def test_cleanup_worktree_removes_readonly_directory(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    stale_workspace = tmp_path / "workspaces" / "workspace-8"
    readonly_dir = stale_workspace / "backend" / "backend_app" / "api" / "routers"
    readonly_dir.mkdir(parents=True)
    readonly_file = readonly_dir / "sample.py"
    readonly_file.write_text("print('hello')", encoding="utf-8")
    stale_workspace.chmod(stat.S_IREAD)
    (stale_workspace / "backend").chmod(stat.S_IREAD)
    (stale_workspace / "backend" / "backend_app").chmod(stat.S_IREAD)
    (stale_workspace / "backend" / "backend_app" / "api").chmod(stat.S_IREAD)
    readonly_dir.chmod(stat.S_IREAD)
    readonly_file.chmod(stat.S_IREAD)

    await gm.cleanup_worktree(temp_repo, stale_workspace)

    assert not stale_workspace.exists()


@pytest.mark.asyncio
async def test_ensure_repository_initializes_non_git_folder_with_existing_files(tmp_path):
    repo = tmp_path / "plain-folder"
    repo.mkdir()
    (repo / "app.py").write_text("print('hello')", encoding="utf-8")

    gm = GitManager(tmp_path / "workspaces")
    await gm.ensure_repository(repo, "main")

    assert (repo / ".git").exists()
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo, check=True, capture_output=True, text=True
    )
    assert branch.stdout.strip() == "main"

    history = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, check=True, capture_output=True, text=True
    )
    assert "Initial commit" in history.stdout


@pytest.mark.asyncio
async def test_ensure_repository_bootstraps_empty_folder(tmp_path):
    repo = tmp_path / "empty-folder"
    repo.mkdir()

    gm = GitManager(tmp_path / "workspaces")
    await gm.ensure_repository(repo, "main")

    assert (repo / ".git").exists()
    assert (repo / ".gitkeep").exists()

    history = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, check=True, capture_output=True, text=True
    )
    assert "Initial commit" in history.stdout
