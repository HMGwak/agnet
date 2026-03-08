from pathlib import Path

from app.core.repo_profile import read_repo_profile, write_repo_profile
from app.schemas import RepoProfileDraft


def make_profile() -> RepoProfileDraft:
    return RepoProfileDraft(
        language="Python",
        frameworks=["FastAPI", "pytest"],
        package_manager="uv",
        dev_commands=["uv sync --extra dev", "uv run uvicorn app.main:app --reload"],
        test_commands=["uv run pytest"],
        build_commands=["npm run build"],
        lint_commands=["npm run lint"],
        deploy_considerations="Staging first.",
        main_branch_protection="protected",
        deployment_sensitivity="high",
        environment_notes=["Uses local SQLite"],
        safety_rules=["Do not deploy from feature workspaces"],
    )


def test_write_repo_profile_preserves_existing_guidance(tmp_path):
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text("## Local Notes\n- Keep this section.\n", encoding="utf-8")

    write_repo_profile(tmp_path, make_profile())

    content = agents_path.read_text(encoding="utf-8")
    assert "## Repo Profile" in content
    assert "## Local Notes" in content
    assert content.index("## Repo Profile") < content.index("## Local Notes")


def test_read_repo_profile_parses_only_profile_section(tmp_path):
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text(
        """## Repo Profile
```toml
language = "Python"
frameworks = ["FastAPI"]
package_manager = "uv"
dev_commands = ["uv sync --extra dev"]
test_commands = ["uv run pytest"]
build_commands = []
lint_commands = []
deploy_considerations = "Local only."
main_branch_protection = "protected"
deployment_sensitivity = "medium"
environment_notes = ["Needs .env"]
safety_rules = ["Run tests before merge"]
```

## Freeform Guidance
- This section should not affect parsing.
""",
        encoding="utf-8",
    )

    profile = read_repo_profile(tmp_path)

    assert profile is not None
    assert profile.language == "Python"
    assert profile.dev_commands == ["uv sync --extra dev"]
    assert profile.environment_notes == ["Needs .env"]
