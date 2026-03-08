from pathlib import Path

import pytest

from app.bootstrap import runtime as runtime_module
from app.config import Settings
from app.core.codex_project_config import CodexProjectConfigError


def write_policy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("plan", "critique", "implement", "test", "review"):
        (directory / f"{name}.md").write_text(f"{name}: $task_input", encoding="utf-8")


def patch_runtime_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    runtime_codex_dir = tmp_path / "runtime" / "codex"
    contract_dir = runtime_codex_dir / "contract"
    generated_dir = runtime_codex_dir / "generated"
    policy_path = runtime_codex_dir / "policy.toml"
    prompts_dir = runtime_codex_dir / "prompts"
    project_dir = tmp_path / "project"
    workspaces_dir = project_dir / "workspaces"
    logs_dir = project_dir / "logs"
    session_logs_dir = logs_dir / "260308_120000"
    write_policy(policy_path)
    write_prompts(prompts_dir)
    generated_dir.mkdir(parents=True, exist_ok=True)
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    session_logs_dir.mkdir(parents=True, exist_ok=True)
    for name, value in (
        ("PROJECT_DATA_DIR", project_dir),
        ("CODEX_POLICY_FILE", policy_path),
        ("CODEX_PROMPTS_DIR", prompts_dir),
        ("CODEX_GENERATED_DIR", generated_dir),
        ("WORKSPACES_DIR", workspaces_dir),
        ("LOGS_DIR", logs_dir),
        ("SESSION_ID", "260308_120000"),
        ("SESSION_LOGS_DIR", session_logs_dir),
    ):
        monkeypatch.setattr(runtime_module.settings, name, value)
    return contract_dir


def test_runtime_task_logger_uses_session_logs_dir(tmp_path, monkeypatch):
    contract_dir = patch_runtime_settings(monkeypatch, tmp_path)
    config_dir = contract_dir / "agents"
    instructions_dir = contract_dir / "instructions"
    rules_dir = contract_dir / "rules"
    config_dir.mkdir(parents=True)
    instructions_dir.mkdir(parents=True)
    rules_dir.mkdir(parents=True)
    (rules_dir / "project.rules").write_text("Read-only local inspection commands are allowed.", encoding="utf-8")
    for name in ("planner", "critic", "executor", "tester", "reviewer", "intake"):
        (instructions_dir / f"{name}.md").write_text(f"{name}", encoding="utf-8")
        (config_dir / f"{name}.toml").write_text(
            f'model = "gpt-5.4"\nmodel_instructions_file = "../instructions/{name}.md"\n',
            encoding="utf-8",
        )
    (contract_dir / "config.toml").write_text(
        "\n".join(
            [
                'model = "gpt-5.4"',
                "",
                "[agents.intake]",
                'config_file = "./agents/intake.toml"',
                "",
                "[agents.planner]",
                'config_file = "./agents/planner.toml"',
                "",
                "[agents.critic]",
                'config_file = "./agents/critic.toml"',
                "",
                "[agents.executor]",
                'config_file = "./agents/executor.toml"',
                "",
                "[agents.tester]",
                'config_file = "./agents/tester.toml"',
                "",
                "[agents.reviewer]",
                'config_file = "./agents/reviewer.toml"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_module.settings, "CODEX_CONTRACT_DIR", contract_dir)

    runtime = runtime_module.create_runtime()

    assert runtime.task_logger.get_log_path(7) == runtime_module.settings.SESSION_LOGS_DIR / "tasks" / "task-7.log"


def test_create_runtime_fails_when_project_codex_config_is_missing(tmp_path, monkeypatch):
    contract_dir = patch_runtime_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(runtime_module.settings, "CODEX_CONTRACT_DIR", contract_dir)

    with pytest.raises(CodexProjectConfigError, match="Missing project Codex config"):
        runtime_module.create_runtime()


def test_create_runtime_fails_when_project_codex_config_is_invalid(tmp_path, monkeypatch):
    contract_dir = patch_runtime_settings(monkeypatch, tmp_path)
    contract_dir.mkdir(parents=True, exist_ok=True)
    (contract_dir / "config.toml").write_text("[agents.planner\n", encoding="utf-8")
    monkeypatch.setattr(runtime_module.settings, "CODEX_CONTRACT_DIR", contract_dir)

    with pytest.raises(CodexProjectConfigError, match="Invalid TOML"):
        runtime_module.create_runtime()


def test_effective_codex_sandbox_mode_uses_danger_full_access_on_windows(monkeypatch):
    monkeypatch.setattr(runtime_module.sys, "platform", "win32")

    assert (
        runtime_module.effective_codex_sandbox_mode(
            "workspace-write",
            allow_unsandboxed_windows=True,
        )
        == "danger-full-access"
    )


def test_effective_codex_sandbox_mode_preserves_other_platforms(monkeypatch):
    monkeypatch.setattr(runtime_module.sys, "platform", "linux")

    assert (
        runtime_module.effective_codex_sandbox_mode(
            "workspace-write",
            allow_unsandboxed_windows=False,
        )
        == "workspace-write"
    )
    assert (
        runtime_module.effective_codex_sandbox_mode(
            "danger-full-access",
            allow_unsandboxed_windows=True,
        )
        == "danger-full-access"
    )


def test_settings_default_codex_home_is_repository_local(tmp_path):
    settings = Settings(BASE_DIR=tmp_path)

    assert settings.CODEX_HOME_DIR == tmp_path / "runtime" / "codex" / "home"
