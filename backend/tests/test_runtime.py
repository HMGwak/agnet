from pathlib import Path

import pytest

from app.bootstrap import runtime as runtime_module
from app.core.codex_project_config import CodexProjectConfigError


def write_policy(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[quality]",
                "plan_required = true",
                "critique_required = true",
                "critique_max_rounds = 2",
                "test_fix_loops = 2",
                "review_required = true",
                "merge_human_approval = true",
                "allow_user_override = false",
                "allow_repo_override = false",
                "",
                "[main]",
                "main_allow_feature_work = false",
                "main_allow_hotfix = true",
                "main_allow_plan_review = true",
                "auto_fork_feature_workspace_from_main = true",
                'hotfix_keywords = ["fix", "bug"]',
                'plan_review_keywords = ["plan", "review"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_prompts(directory: Path) -> None:
    directory.mkdir(parents=True)
    for name in ("plan", "critique", "implement", "test", "review"):
        (directory / f"{name}.md").write_text(f"{name}: $task_input", encoding="utf-8")


def patch_runtime_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    policy_path = tmp_path / "codex-policy.toml"
    prompts_dir = tmp_path / "prompts"
    workspaces_dir = tmp_path / "workspaces"
    write_policy(policy_path)
    write_prompts(prompts_dir)
    workspaces_dir.mkdir()
    for name, value in (
        ("CODEX_POLICY_FILE", policy_path),
        ("CODEX_PROMPTS_DIR", prompts_dir),
        ("WORKSPACES_DIR", workspaces_dir),
    ):
        monkeypatch.setattr(runtime_module.settings, name, value)
    return tmp_path / ".codex"


def test_create_runtime_fails_when_project_codex_config_is_missing(tmp_path, monkeypatch):
    project_dir = patch_runtime_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime_module.settings, "CODEX_PROJECT_DIR", project_dir)

    with pytest.raises(CodexProjectConfigError, match="Missing project Codex config"):
        runtime_module.create_runtime()


def test_create_runtime_fails_when_project_codex_config_is_invalid(tmp_path, monkeypatch):
    project_dir = patch_runtime_settings(monkeypatch, tmp_path)
    project_dir.mkdir()
    (project_dir / "config.toml").write_text("[agents.planner\n", encoding="utf-8")
    monkeypatch.setattr(runtime_module.settings, "CODEX_PROJECT_DIR", project_dir)

    with pytest.raises(CodexProjectConfigError, match="Invalid TOML"):
        runtime_module.create_runtime()
