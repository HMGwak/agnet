import subprocess

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
async def test_create_worktree(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(temp_repo, "task/1/test-branch", 1, repo_id=11)
    assert ws.exists()
    assert (ws / "README.md").exists()
    assert ws == tmp_path / "workspaces" / "repo-11" / "task-1"


@pytest.mark.asyncio
async def test_create_worktree_existing_branch(temp_repo, tmp_path):
    """Test reusing an existing branch (crash recovery scenario)."""
    # Create branch first
    subprocess.run(
        ["git", "branch", "task/3/existing"], cwd=temp_repo, check=True, capture_output=True
    )
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(temp_repo, "task/3/existing", 3, repo_id=11)
    assert ws.exists()


@pytest.mark.asyncio
async def test_get_diff(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(temp_repo, "task/4/diff-test", 4, repo_id=11)
    (ws / "new_file.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "add file"],
        cwd=ws, check=True, capture_output=True,
    )
    diff = await gm.get_diff(ws)
    assert "new_file.py" in diff


@pytest.mark.asyncio
async def test_merge_to_main(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(temp_repo, "task/2/feature", 2, repo_id=11)
    (ws / "new_file.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@test.com", "commit", "-m", "add file"],
        cwd=ws, check=True, capture_output=True,
    )
    success, msg = await gm.merge_to_main(temp_repo, "task/2/feature")
    assert success


@pytest.mark.asyncio
async def test_cleanup_worktree(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    ws = await gm.create_worktree(temp_repo, "task/5/cleanup", 5, repo_id=11)
    assert ws.exists()
    await gm.cleanup_worktree(temp_repo, ws)
    assert not ws.exists()
    assert not (tmp_path / "workspaces" / "repo-11").exists()


@pytest.mark.asyncio
async def test_create_worktree_cleans_existing_workspace_dir(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    stale_workspace = tmp_path / "workspaces" / "repo-11" / "task-6"
    stale_workspace.mkdir(parents=True)
    (stale_workspace / "stale.txt").write_text("stale")

    ws = await gm.create_worktree(temp_repo, "task/6/recreated", 6, repo_id=11)

    assert ws.exists()
    assert not (ws / "stale.txt").exists()


@pytest.mark.asyncio
async def test_create_worktree_cleans_legacy_flat_workspace_dir(temp_repo, tmp_path):
    gm = GitManager(tmp_path / "workspaces")
    legacy_workspace = tmp_path / "workspaces" / "task-7"
    legacy_workspace.mkdir(parents=True)

    subprocess.run(
        ["git", "worktree", "add", "-b", "task/7/legacy", str(legacy_workspace)],
        cwd=temp_repo,
        check=True,
        capture_output=True,
    )

    ws = await gm.create_worktree(temp_repo, "task/7/legacy", 7, repo_id=11)

    assert ws.exists()
    assert ws == tmp_path / "workspaces" / "repo-11" / "task-7"
    assert not legacy_workspace.exists()


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
