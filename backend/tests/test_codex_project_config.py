from pathlib import Path

import pytest

from app.core.codex_project_config import CodexProjectConfig, CodexProjectConfigError


def write_project_config(project_dir: Path) -> Path:
    agent_dir = project_dir / "agents"
    instruction_dir = project_dir / "instructions"
    rules_dir = project_dir / "rules"
    agent_dir.mkdir(parents=True)
    instruction_dir.mkdir()
    rules_dir.mkdir()

    (instruction_dir / "planner.md").write_text("planner", encoding="utf-8")
    (rules_dir / "project.rules").write_text("never push automatically", encoding="utf-8")
    (agent_dir / "planner.toml").write_text(
        "\n".join(
            [
                'model = "gpt-5.4"',
                'model_instructions_file = "../instructions/planner.md"',
                "",
                "[features]",
                "multi_agent = false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    config_path = project_dir / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'model = "gpt-5.4"',
                'approval_policy = "never"',
                'sandbox_mode = "workspace-write"',
                "",
                "[agents.planner]",
                'config_file = "./agents/planner.toml"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def test_load_from_file_resolves_relative_agent_paths(tmp_path):
    config_path = write_project_config(tmp_path / ".codex")

    project_config = CodexProjectConfig.load_from_file(config_path)
    planner_config = project_config.build_agent_config("planner")

    assert project_config.agent_files["planner"].is_absolute()
    assert planner_config["model"] == "gpt-5.4"
    instructions_path = Path(planner_config["model_instructions_file"])
    assert instructions_path.parent.name == ".generated"
    assert instructions_path.name == "planner.md"
    rendered = instructions_path.read_text(encoding="utf-8")
    assert "Project rules:" in rendered
    assert "never push automatically" in rendered
    assert "planner" in rendered
    assert planner_config["features"]["multi_agent"] is False


def test_build_agent_config_raises_for_unknown_agent(tmp_path):
    config_path = write_project_config(tmp_path / ".codex")
    project_config = CodexProjectConfig.load_from_file(config_path)

    with pytest.raises(CodexProjectConfigError, match="Unknown project Codex agent"):
        project_config.build_agent_config("reviewer")
