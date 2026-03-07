from pathlib import Path

import pytest

from app.core.project_policy import (
    ProjectPolicyError,
    classify_main_workspace_request,
    load_project_policy,
)
from app.core.prompt_library import PromptLibrary, PromptLibraryError


def test_load_project_policy_reads_required_rules(tmp_path):
    path = tmp_path / "codex-policy.toml"
    path.write_text(
        """
[quality]
plan_required = true
critique_required = true
critique_max_rounds = 2
test_fix_loops = 2
review_required = true
merge_human_approval = true
allow_user_override = false
allow_repo_override = false

[main]
main_allow_feature_work = false
main_allow_hotfix = true
main_allow_plan_review = true
auto_fork_feature_workspace_from_main = true
hotfix_keywords = ["fix", "bug"]
plan_review_keywords = ["plan", "review"]
""".strip(),
        encoding="utf-8",
    )

    policy = load_project_policy(path)

    assert policy.critique_max_rounds == 2
    assert policy.test_fix_loops == 2
    assert policy.main_allow_feature_work is False


def test_load_project_policy_fails_when_file_missing(tmp_path):
    with pytest.raises(ProjectPolicyError, match="Missing codex policy file"):
        load_project_policy(tmp_path / "missing.toml")


def test_prompt_library_fails_when_required_template_missing(tmp_path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    for name in ("plan", "critique", "implement", "test"):
        (prompts_dir / f"{name}.md").write_text("hello", encoding="utf-8")

    with pytest.raises(PromptLibraryError, match="Missing prompt template"):
        PromptLibrary.load_from_directory(prompts_dir)


def test_main_classification_is_deterministic():
    policy = load_project_policy(Path(__file__).resolve().parents[2] / "codex-policy.toml")

    assert classify_main_workspace_request(policy, "Fix regression", "") == "hotfix"
    assert classify_main_workspace_request(policy, "Review task board", "") == "plan_review"
    assert classify_main_workspace_request(policy, "Build Tetris", "") == "feature"
