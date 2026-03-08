from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


class ProjectPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectPolicy:
    plan_required: bool
    critique_required: bool
    critique_max_rounds: int
    test_fix_loops: int
    review_required: bool
    merge_human_approval: bool
    allow_user_override: bool
    allow_repo_override: bool
    main_allow_feature_work: bool
    main_allow_hotfix: bool
    main_allow_plan_review: bool
    auto_fork_feature_workspace_from_main: bool
    hotfix_keywords: tuple[str, ...]
    plan_review_keywords: tuple[str, ...]


def load_project_policy(path: Path) -> ProjectPolicy:
    if not path.exists():
        raise ProjectPolicyError(f"Missing codex policy file: {path}")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ProjectPolicyError(f"Invalid codex policy file: {exc}") from exc

    quality = _require_section(data, "quality")
    main = _require_section(data, "main")

    critique_max_rounds = _require_int(quality, "critique_max_rounds")
    test_fix_loops = _require_int(quality, "test_fix_loops")
    if critique_max_rounds < 1:
        raise ProjectPolicyError("quality.critique_max_rounds must be >= 1")
    if test_fix_loops < 1:
        raise ProjectPolicyError("quality.test_fix_loops must be >= 1")

    return ProjectPolicy(
        plan_required=_require_bool(quality, "plan_required"),
        critique_required=_require_bool(quality, "critique_required"),
        critique_max_rounds=critique_max_rounds,
        test_fix_loops=test_fix_loops,
        review_required=_require_bool(quality, "review_required"),
        merge_human_approval=_require_bool(quality, "merge_human_approval"),
        allow_user_override=_require_bool(quality, "allow_user_override"),
        allow_repo_override=_require_bool(quality, "allow_repo_override"),
        main_allow_feature_work=_require_bool(main, "main_allow_feature_work"),
        main_allow_hotfix=_require_bool(main, "main_allow_hotfix"),
        main_allow_plan_review=_require_bool(main, "main_allow_plan_review"),
        auto_fork_feature_workspace_from_main=_require_bool(
            main, "auto_fork_feature_workspace_from_main"
        ),
        hotfix_keywords=_require_keywords(main, "hotfix_keywords"),
        plan_review_keywords=_require_keywords(main, "plan_review_keywords"),
    )


def classify_main_workspace_request(
    policy: ProjectPolicy,
    title: str,
    description: str,
) -> str:
    text = f"{title}\n{description}".lower()
    if _contains_keyword(text, policy.plan_review_keywords):
        return "plan_review"
    if _contains_keyword(text, policy.hotfix_keywords):
        return "hotfix"
    return "feature"


def _contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _require_section(data: dict, name: str) -> dict:
    section = data.get(name)
    if not isinstance(section, dict):
        raise ProjectPolicyError(f"Missing [{name}] section in codex policy")
    return section


def _require_bool(section: dict, key: str) -> bool:
    value = section.get(key)
    if not isinstance(value, bool):
        raise ProjectPolicyError(f"Expected boolean for {key}")
    return value


def _require_int(section: dict, key: str) -> int:
    value = section.get(key)
    if not isinstance(value, int):
        raise ProjectPolicyError(f"Expected integer for {key}")
    return value


def _require_keywords(section: dict, key: str) -> tuple[str, ...]:
    value = section.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ProjectPolicyError(f"Expected non-empty string list for {key}")
    return tuple(item.strip().lower() for item in value if item.strip())
