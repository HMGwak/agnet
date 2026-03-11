from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.codex_contract import (
    MANIFEST_FILE_NAME,
    REQUIRED_AGENTS,
    REQUIRED_PROMPTS,
    CodexContractError,
    apply_contract,
    load_contract,
    render_contract,
    verify_contract,
)
from app.core.codex_project_config import CodexProjectConfig
from app.core.prompt_library import PromptLibrary


CODEX_RUNTIME_DIR = Path("runtime") / "codex"
CONTRACT_DIR = CODEX_RUNTIME_DIR / "contract"
PROMPTS_DIR = CODEX_RUNTIME_DIR / "prompts"
POLICY_PATH = CODEX_RUNTIME_DIR / "policy.toml"
GENERATED_DIR = CODEX_RUNTIME_DIR / "generated"

AGENT_DESCRIPTIONS = {
    "intake": "Intake agent",
    "orchestrator": "Orchestrator agent",
    "explorer": "Explorer agent",
    "planner": "Planner agent",
    "critic": "Critic agent",
    "executor": "Executor agent",
    "tester": "Tester agent",
    "reviewer": "Reviewer agent",
    "recovery_planner": "Recovery planner agent",
    "verifier": "Verifier agent",
}

AGENT_MODELS = {
    "intake": "gpt-5.4",
    "orchestrator": "gpt-5.4",
    "explorer": "gpt-5.3-codex-spark",
    "planner": "gpt-5.4",
    "critic": "gpt-5.4",
    "executor": "gpt-5-codex",
    "tester": "gpt-5-codex",
    "reviewer": "gpt-5.4",
    "recovery_planner": "gpt-5.4",
    "verifier": "gpt-5.4",
}

AGENT_REASONING = {
    "intake": "medium",
    "orchestrator": "high",
    "explorer": "low",
    "planner": "high",
    "critic": "high",
    "executor": "medium",
    "tester": "medium",
    "reviewer": "high",
    "recovery_planner": "xhigh",
    "verifier": "high",
}

AGENT_MULTI_AGENT = {
    "intake": False,
    "orchestrator": False,
    "explorer": False,
    "planner": False,
    "critic": False,
    "executor": True,
    "tester": False,
    "reviewer": False,
    "recovery_planner": False,
    "verifier": False,
}

INSTRUCTION_TEXT = {
    "intake": "Intake instructions.",
    "orchestrator": "Orchestrator instructions.",
    "explorer": "Explorer instructions.",
    "planner": "Planner instructions.",
    "critic": "Critic instructions.",
    "executor": "Executor instructions.",
    "tester": "Tester instructions.",
    "reviewer": "Reviewer instructions.",
    "recovery_planner": "Recovery planner instructions.",
    "verifier": "Verifier instructions.",
}

PROMPT_TEXT = {
    "explore": "Explore prompt for $repo_name in $workspace_name on $branch_name at $working_directory. $task_input",
    "plan": "Plan prompt for $repo_name in $workspace_name on $branch_name from $base_branch at $working_directory with $critique_max_rounds and $test_fix_loops. $task_input",
    "critique": "Critique prompt for $repo_name in $workspace_name on $branch_name at $working_directory. $task_input $plan_text",
    "implement": "Implement prompt for $repo_name in $workspace_name on $branch_name at $working_directory. $task_input $plan_text $repair_request",
    "test": "Test prompt for $repo_name in $workspace_name on $branch_name at $working_directory with $test_fix_loops. $task_input $plan_text",
    "review": "Review prompt for $repo_name in $workspace_name on $branch_name at $working_directory. $task_input $plan_text $test_output $diff_text",
    "orchestrate": "Orchestrate prompt for $repo_name in $workspace_name on $branch_name at $working_directory during $current_phase. $task_input $plan_text $failure_output $test_output $review_output $diff_text",
    "recover": "Recover prompt for $repo_name in $workspace_name on $branch_name at $working_directory. $task_input $plan_text $failure_output",
    "verify": "Verify prompt for $repo_name in $workspace_name on $branch_name at $working_directory. $task_input $plan_text $test_output $review_output $diff_text",
}


def _literal_block(text: str) -> str:
    return "'''\n" + text.strip("\n") + "\n'''"


def make_manifest_text() -> str:
    lines = [
        "[project]",
        'model = "gpt-5.4"',
        'approval_policy = "never"',
        'sandbox_mode = "workspace-write"',
        'model_reasoning_effort = "medium"',
        "multi_agent = false",
        "shell_environment_include_only = [",
        '  "PATH",',
        '  "SystemDrive",',
        "]",
        "",
    ]

    for agent_name in REQUIRED_AGENTS:
        lines.extend(
            [
                f"[agents.{agent_name}]",
                f'description = {json.dumps(AGENT_DESCRIPTIONS[agent_name])}',
                f'model = {json.dumps(AGENT_MODELS[agent_name])}',
                f'model_reasoning_effort = {json.dumps(AGENT_REASONING[agent_name])}',
                f"multi_agent = {'true' if AGENT_MULTI_AGENT[agent_name] else 'false'}",
                "",
            ]
        )

    for agent_name in REQUIRED_AGENTS:
        lines.extend(
            [
                f"[instructions.{agent_name}]",
                f"text = {_literal_block(INSTRUCTION_TEXT[agent_name])}",
                "",
            ]
        )

    lines.extend(
        [
            "[rules]",
            f"text = {_literal_block('Never push automatically.')}",
            "",
            "[policy.quality]",
            "plan_required = true",
            "critique_required = true",
            "critique_max_rounds = 2",
            "test_fix_loops = 2",
            "review_required = true",
            "merge_human_approval = true",
            "allow_user_override = false",
            "allow_repo_override = false",
            "",
            "[policy.main]",
            "main_allow_feature_work = false",
            "main_allow_hotfix = true",
            "main_allow_plan_review = true",
            "auto_fork_feature_workspace_from_main = true",
            "hotfix_keywords = [",
            '  "fix",',
            '  "bug",',
            "]",
            "plan_review_keywords = [",
            '  "plan",',
            '  "review",',
            "]",
            "",
        ]
    )

    for prompt_name in REQUIRED_PROMPTS:
        lines.extend(
            [
                f"[prompts.{prompt_name}]",
                f"text = {_literal_block(PROMPT_TEXT[prompt_name])}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def write_manifest(root_dir: Path, text: str | None = None) -> Path:
    contract_dir = root_dir / CONTRACT_DIR
    contract_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = contract_dir / MANIFEST_FILE_NAME
    manifest_path.write_text(text or make_manifest_text(), encoding="utf-8")
    return manifest_path


def test_load_contract_rejects_missing_rules_section(tmp_path):
    manifest_text = make_manifest_text().replace("[rules]\ntext = '''\nNever push automatically.\n'''\n\n", "")
    manifest_path = write_manifest(tmp_path, manifest_text)

    with pytest.raises(CodexContractError, match="Missing table 'rules'"):
        load_contract(manifest_path)


def test_render_contract_returns_expected_path_set(tmp_path):
    spec = load_contract(write_manifest(tmp_path))

    rendered = render_contract(spec)

    expected_paths = {
        (tmp_path / CONTRACT_DIR / "config.toml").resolve(),
        (tmp_path / POLICY_PATH).resolve(),
        (tmp_path / CONTRACT_DIR / "rules" / "project.rules").resolve(),
        *((tmp_path / CONTRACT_DIR / "agents" / f"{name}.toml").resolve() for name in REQUIRED_AGENTS),
        *((tmp_path / CONTRACT_DIR / "instructions" / f"{name}.md").resolve() for name in REQUIRED_AGENTS),
        *((tmp_path / PROMPTS_DIR / f"{name}.md").resolve() for name in REQUIRED_PROMPTS),
    }
    assert {path.resolve() for path in rendered} == expected_paths


def test_apply_contract_writes_expected_files_and_prunes_unexpected_files(tmp_path):
    spec = load_contract(write_manifest(tmp_path))

    changed_paths = {path.resolve() for path in apply_contract(spec, spec.root_dir)}

    assert (tmp_path / CONTRACT_DIR / "config.toml").resolve() in changed_paths
    assert (tmp_path / CONTRACT_DIR / "agents" / "planner.toml").resolve() in changed_paths
    assert (tmp_path / PROMPTS_DIR / "plan.md").resolve() in changed_paths
    assert verify_contract(spec, spec.root_dir) == []

    unexpected_agent = tmp_path / CONTRACT_DIR / "agents" / "rogue.toml"
    unexpected_agent.write_text("rogue", encoding="utf-8")
    changed_paths = {path.resolve() for path in apply_contract(spec, spec.root_dir)}
    assert unexpected_agent.resolve() in changed_paths
    assert not unexpected_agent.exists()


def test_verify_contract_reports_missing_modified_and_unexpected_files(tmp_path):
    spec = load_contract(write_manifest(tmp_path))
    apply_contract(spec, spec.root_dir)

    planner_path = tmp_path / CONTRACT_DIR / "agents" / "planner.toml"
    planner_path.write_text("broken\n", encoding="utf-8")
    missing_prompt = tmp_path / PROMPTS_DIR / "plan.md"
    missing_prompt.unlink()
    unexpected_instruction = tmp_path / CONTRACT_DIR / "instructions" / "rogue.md"
    unexpected_instruction.write_text("rogue\n", encoding="utf-8")

    drifts = {
        (drift.path.resolve().relative_to(tmp_path.resolve()).as_posix(), drift.reason)
        for drift in verify_contract(spec, spec.root_dir)
    }

    assert ("runtime/codex/contract/agents/planner.toml", "content mismatch") in drifts
    assert ("runtime/codex/prompts/plan.md", "missing managed file") in drifts
    assert ("runtime/codex/contract/instructions/rogue.md", "unexpected managed file") in drifts


def test_generated_contract_is_runtime_compatible(tmp_path):
    spec = load_contract(write_manifest(tmp_path))
    apply_contract(spec, spec.root_dir)

    generated_dir = tmp_path / GENERATED_DIR
    project_config = CodexProjectConfig.load_from_file(
        tmp_path / CONTRACT_DIR / "config.toml",
        generated_dir=generated_dir,
    )
    planner_config = project_config.build_agent_config("planner")
    assert planner_config["features"]["multi_agent"] is False
    assert planner_config["model"] == "gpt-5.4"
    generated_instruction = Path(planner_config["model_instructions_file"])
    assert generated_instruction.parent == generated_dir.resolve()
    rendered_instruction = generated_instruction.read_text(encoding="utf-8")
    assert "Project rules:" in rendered_instruction
    assert "Never push automatically." in rendered_instruction
    assert "Planner instructions." in rendered_instruction

    prompt_library = PromptLibrary.load_from_directory(tmp_path / PROMPTS_DIR)
    rendered_prompt = prompt_library.render(
        "plan",
        repo_name="repo",
        workspace_name="workspace",
        branch_name="feature/test",
        base_branch="main",
        working_directory="/tmp/workspace",
        critique_max_rounds=2,
        test_fix_loops=2,
        task_input="Do the thing",
        exploration_text="",
    )
    assert rendered_prompt.startswith("<!-- Generated from codex-contract.toml.")
    assert "Do the thing" in rendered_prompt


def test_repo_manifest_matches_checked_in_contract():
    repo_root = Path(__file__).resolve().parents[2]
    spec = load_contract(repo_root / CONTRACT_DIR / MANIFEST_FILE_NAME)

    assert verify_contract(spec, spec.root_dir) == []


def test_checked_in_plan_prompt_requires_korean_user_facing_output():
    repo_root = Path(__file__).resolve().parents[2]
    prompt_path = repo_root / PROMPTS_DIR / "plan.md"
    prompt_text = prompt_path.read_text(encoding="utf-8")

    assert "Write all user-facing content in Korean." in prompt_text
    assert "1. 요구사항 요약" in prompt_text
