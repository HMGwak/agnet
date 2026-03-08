from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from app.schemas import RepoProfileDraft

PROFILE_START_MARKER = "<!-- REPO_PROFILE_START -->"
PROFILE_END_MARKER = "<!-- REPO_PROFILE_END -->"
PROFILE_HEADING = "## Repo Profile"

REPO_PROFILE_FIELD_LABELS = {
    "language": "주 사용 언어",
    "package_manager": "런타임/패키지 매니저",
    "dev_commands": "개발 명령어",
    "test_commands": "테스트 명령어",
    "deploy_considerations": "배포 고려 사항",
}


def read_repo_profile(repo_path: Path) -> RepoProfileDraft | None:
    agents_path = repo_path / "AGENTS.md"
    if not agents_path.exists():
        return None

    content = agents_path.read_text(encoding="utf-8")
    profile_block = _extract_profile_block(content)
    if profile_block is None:
        return None

    try:
        payload = tomllib.loads(profile_block)
    except tomllib.TOMLDecodeError:
        return None
    return RepoProfileDraft.model_validate(payload)


def write_repo_profile(repo_path: Path, profile: RepoProfileDraft) -> None:
    profile = RepoProfileDraft.model_validate(profile)
    agents_path = repo_path / "AGENTS.md"
    existing = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    block = render_repo_profile_block(profile)

    if PROFILE_START_MARKER in existing and PROFILE_END_MARKER in existing:
        updated = re.sub(
            rf"{re.escape(PROFILE_START_MARKER)}.*?{re.escape(PROFILE_END_MARKER)}",
            block,
            existing,
            count=1,
            flags=re.DOTALL,
        )
    elif existing.strip():
        updated = f"{block}\n\n{existing.lstrip()}"
    else:
        updated = (
            f"{block}\n\n"
            "## Repo Instructions\n"
            "- Add repository-specific operating guidance below this line.\n"
        )

    agents_path.write_text(updated.rstrip() + "\n", encoding="utf-8")


def merge_repo_profile(
    existing: RepoProfileDraft | None,
    updates: RepoProfileDraft | None,
) -> RepoProfileDraft | None:
    if existing is None and updates is None:
        return None

    merged = RepoProfileDraft.model_validate(
        existing.model_dump(mode="json") if existing is not None else {}
    )
    if updates is None:
        return merged

    for field_name in RepoProfileDraft.model_fields:
        value = getattr(updates, field_name)
        if isinstance(value, str):
            if value.strip():
                setattr(merged, field_name, value.strip())
            continue
        if isinstance(value, list) and value:
            setattr(merged, field_name, value)

    return merged


def missing_repo_profile_fields(profile: RepoProfileDraft | None) -> list[str]:
    if profile is None:
        return list(REPO_PROFILE_FIELD_LABELS)
    return profile.missing_required_fields()


def build_repo_profile_questions(missing_fields: list[str]) -> list[str]:
    questions = [
        f"Repo Profile의 '{REPO_PROFILE_FIELD_LABELS[field]}' 항목을 채워 주세요."
        for field in missing_fields
        if field in REPO_PROFILE_FIELD_LABELS
    ]
    if questions:
        questions[0] = (
            "이 저장소는 작업 초안을 만들기 전에 AGENTS.md 의 Repo Profile을 먼저 채워야 합니다. "
            + questions[0]
        )
    return questions


def render_repo_profile_block(profile: RepoProfileDraft) -> str:
    toml_lines = [
        f'language = {_render_string(profile.language)}',
        f"frameworks = {_render_list(profile.frameworks)}",
        f'package_manager = {_render_string(profile.package_manager)}',
        f"dev_commands = {_render_list(profile.dev_commands)}",
        f"test_commands = {_render_list(profile.test_commands)}",
        f"build_commands = {_render_list(profile.build_commands)}",
        f"lint_commands = {_render_list(profile.lint_commands)}",
        f'deploy_considerations = {_render_string(profile.deploy_considerations)}',
        f'main_branch_protection = {_render_string(profile.main_branch_protection)}',
        f'deployment_sensitivity = {_render_string(profile.deployment_sensitivity)}',
        f"environment_notes = {_render_list(profile.environment_notes)}",
        f"safety_rules = {_render_list(profile.safety_rules)}",
    ]
    return (
        f"{PROFILE_START_MARKER}\n"
        f"{PROFILE_HEADING}\n"
        "```toml\n"
        + "\n".join(toml_lines)
        + "\n```\n"
        f"{PROFILE_END_MARKER}"
    )


def _extract_profile_block(content: str) -> str | None:
    marker_pattern = re.compile(
        rf"{re.escape(PROFILE_START_MARKER)}.*?```toml\s*(.*?)```.*?{re.escape(PROFILE_END_MARKER)}",
        re.DOTALL,
    )
    match = marker_pattern.search(content)
    if match:
        return match.group(1).strip()

    heading_pattern = re.compile(
        rf"^{re.escape(PROFILE_HEADING)}\s*```toml\s*(.*?)```",
        re.DOTALL | re.MULTILINE,
    )
    match = heading_pattern.search(content)
    if match:
        return match.group(1).strip()
    return None


def _render_string(value: str) -> str:
    return json.dumps(value)


def _render_list(values: list[str]) -> str:
    rendered = ", ".join(json.dumps(value) for value in values)
    return f"[{rendered}]"
