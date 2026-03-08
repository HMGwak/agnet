from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tomllib


MANIFEST_FILE_NAME = "codex-contract.toml"
CONFIG_RELATIVE_PATH = Path("config.toml")
POLICY_RELATIVE_PATH = Path("..") / "policy.toml"
RULES_RELATIVE_PATH = Path("rules") / "project.rules"
AGENTS_DIR_RELATIVE_PATH = Path("agents")
INSTRUCTIONS_DIR_RELATIVE_PATH = Path("instructions")
PROMPTS_DIR_RELATIVE_PATH = Path("..") / "prompts"
REQUIRED_AGENTS = ("intake", "planner", "critic", "executor", "tester", "reviewer")
REQUIRED_PROMPTS = ("plan", "critique", "implement", "test", "review")
MARKDOWN_HEADER = "<!-- Generated from codex-contract.toml. Do not edit directly. -->"
TEXT_HEADER = "# Generated from codex-contract.toml. Do not edit directly."


class CodexContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class Drift:
    path: Path
    reason: str


@dataclass(frozen=True)
class ContractSpec:
    root_dir: Path
    manifest_path: Path
    project: dict[str, object]
    agents: dict[str, dict[str, object]]
    instructions: dict[str, str]
    rules_text: str
    policy: dict[str, dict[str, object]]
    prompts: dict[str, str]


def load_contract(manifest_path: Path) -> ContractSpec:
    manifest_path = manifest_path.resolve()
    if not manifest_path.exists():
        raise CodexContractError(f"Missing Codex contract manifest: {manifest_path}")

    raw = _load_toml(manifest_path)
    _reject_unknown_keys(
        raw,
        {"project", "agents", "instructions", "rules", "policy", "prompts"},
        "root",
    )
    project_raw = _require_table(raw, "project")
    _reject_unknown_keys(
        project_raw,
        {
            "model",
            "approval_policy",
            "sandbox_mode",
            "model_reasoning_effort",
            "multi_agent",
            "shell_environment_include_only",
        },
        "project",
    )
    project = {
        "model": _require_string(project_raw, "model", "project"),
        "approval_policy": _require_string(project_raw, "approval_policy", "project"),
        "sandbox_mode": _require_string(project_raw, "sandbox_mode", "project"),
        "model_reasoning_effort": _require_string(
            project_raw, "model_reasoning_effort", "project"
        ),
        "multi_agent": _require_bool(project_raw, "multi_agent", "project"),
        "shell_environment_include_only": _require_string_list(
            project_raw, "shell_environment_include_only", "project"
        ),
    }

    agents_raw = _require_table(raw, "agents")
    _validate_exact_keys(agents_raw, REQUIRED_AGENTS, "agents")
    agents: dict[str, dict[str, object]] = {}
    for agent_name in REQUIRED_AGENTS:
        agent_raw = _require_table(agents_raw, agent_name, f"agents.{agent_name}")
        _reject_unknown_keys(
            agent_raw,
            {"description", "model_reasoning_effort", "multi_agent"},
            f"agents.{agent_name}",
        )
        agents[agent_name] = {
            "description": _require_string(
                agent_raw, "description", f"agents.{agent_name}"
            ),
            "model_reasoning_effort": _require_string(
                agent_raw, "model_reasoning_effort", f"agents.{agent_name}"
            ),
            "multi_agent": _require_bool(
                agent_raw, "multi_agent", f"agents.{agent_name}"
            ),
        }

    instructions_raw = _require_table(raw, "instructions")
    _validate_exact_keys(instructions_raw, REQUIRED_AGENTS, "instructions")
    instructions: dict[str, str] = {}
    for agent_name in REQUIRED_AGENTS:
        instruction_raw = _require_table(
            instructions_raw, agent_name, f"instructions.{agent_name}"
        )
        _reject_unknown_keys(instruction_raw, {"text"}, f"instructions.{agent_name}")
        instructions[agent_name] = _normalize_block(
            _require_string(instruction_raw, "text", f"instructions.{agent_name}")
        )

    rules_raw = _require_table(raw, "rules")
    _reject_unknown_keys(rules_raw, {"text"}, "rules")
    rules_text = _normalize_block(_require_string(rules_raw, "text", "rules"))

    policy_raw = _require_table(raw, "policy")
    _reject_unknown_keys(policy_raw, {"quality", "main"}, "policy")
    quality_raw = _require_table(policy_raw, "quality", "policy")
    _reject_unknown_keys(
        quality_raw,
        {
            "plan_required",
            "critique_required",
            "critique_max_rounds",
            "test_fix_loops",
            "review_required",
            "merge_human_approval",
            "allow_user_override",
            "allow_repo_override",
        },
        "policy.quality",
    )
    main_raw = _require_table(policy_raw, "main", "policy")
    _reject_unknown_keys(
        main_raw,
        {
            "main_allow_feature_work",
            "main_allow_hotfix",
            "main_allow_plan_review",
            "auto_fork_feature_workspace_from_main",
            "hotfix_keywords",
            "plan_review_keywords",
        },
        "policy.main",
    )
    policy = {
        "quality": {
            "plan_required": _require_bool(
                quality_raw, "plan_required", "policy.quality"
            ),
            "critique_required": _require_bool(
                quality_raw, "critique_required", "policy.quality"
            ),
            "critique_max_rounds": _require_int(
                quality_raw, "critique_max_rounds", "policy.quality"
            ),
            "test_fix_loops": _require_int(
                quality_raw, "test_fix_loops", "policy.quality"
            ),
            "review_required": _require_bool(
                quality_raw, "review_required", "policy.quality"
            ),
            "merge_human_approval": _require_bool(
                quality_raw, "merge_human_approval", "policy.quality"
            ),
            "allow_user_override": _require_bool(
                quality_raw, "allow_user_override", "policy.quality"
            ),
            "allow_repo_override": _require_bool(
                quality_raw, "allow_repo_override", "policy.quality"
            ),
        },
        "main": {
            "main_allow_feature_work": _require_bool(
                main_raw, "main_allow_feature_work", "policy.main"
            ),
            "main_allow_hotfix": _require_bool(
                main_raw, "main_allow_hotfix", "policy.main"
            ),
            "main_allow_plan_review": _require_bool(
                main_raw, "main_allow_plan_review", "policy.main"
            ),
            "auto_fork_feature_workspace_from_main": _require_bool(
                main_raw, "auto_fork_feature_workspace_from_main", "policy.main"
            ),
            "hotfix_keywords": _require_string_list(
                main_raw, "hotfix_keywords", "policy.main"
            ),
            "plan_review_keywords": _require_string_list(
                main_raw, "plan_review_keywords", "policy.main"
            ),
        },
    }

    prompts_raw = _require_table(raw, "prompts")
    _validate_exact_keys(prompts_raw, REQUIRED_PROMPTS, "prompts")
    prompts: dict[str, str] = {}
    for prompt_name in REQUIRED_PROMPTS:
        prompt_raw = _require_table(prompts_raw, prompt_name, f"prompts.{prompt_name}")
        _reject_unknown_keys(prompt_raw, {"text"}, f"prompts.{prompt_name}")
        prompts[prompt_name] = _normalize_block(
            _require_string(prompt_raw, "text", f"prompts.{prompt_name}")
        )

    return ContractSpec(
        root_dir=manifest_path.parent,
        manifest_path=manifest_path,
        project=project,
        agents=agents,
        instructions=instructions,
        rules_text=rules_text,
        policy=policy,
        prompts=prompts,
    )


def render_contract(spec: ContractSpec) -> dict[Path, str]:
    root_dir = spec.root_dir
    rendered: dict[Path, str] = {
        root_dir / CONFIG_RELATIVE_PATH: _render_project_config(spec),
        root_dir / POLICY_RELATIVE_PATH: _render_policy(spec),
        root_dir / RULES_RELATIVE_PATH: _render_text_file(spec.rules_text),
    }

    for agent_name in REQUIRED_AGENTS:
        rendered[
            root_dir / AGENTS_DIR_RELATIVE_PATH / f"{agent_name}.toml"
        ] = _render_agent_config(spec, agent_name)
        rendered[
            root_dir / INSTRUCTIONS_DIR_RELATIVE_PATH / f"{agent_name}.md"
        ] = _render_markdown_file(spec.instructions[agent_name])

    for prompt_name in REQUIRED_PROMPTS:
        rendered[
            root_dir / PROMPTS_DIR_RELATIVE_PATH / f"{prompt_name}.md"
        ] = _render_markdown_file(spec.prompts[prompt_name])

    return rendered


def apply_contract(spec: ContractSpec, root_dir: Path) -> list[Path]:
    root_dir = root_dir.resolve()
    expected_files = _render_contract_for_root(spec, root_dir)
    changed_paths: list[Path] = []
    for path, content in expected_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = content.encode("utf-8")
        if not path.exists() or path.read_bytes() != payload:
            path.write_bytes(payload)
            changed_paths.append(path)

    unexpected_paths = _find_unexpected_managed_files(expected_files, root_dir)
    for unexpected_path in unexpected_paths:
        unexpected_path.unlink()
        changed_paths.append(unexpected_path)

    return sorted(changed_paths)


def verify_contract(spec: ContractSpec, root_dir: Path) -> list[Drift]:
    root_dir = root_dir.resolve()
    expected_files = _render_contract_for_root(spec, root_dir)
    drifts: list[Drift] = []
    for path, content in expected_files.items():
        if not path.exists():
            drifts.append(Drift(path=path, reason="missing managed file"))
            continue
        if path.read_bytes() != content.encode("utf-8"):
            drifts.append(Drift(path=path, reason="content mismatch"))

    for unexpected_path in _find_unexpected_managed_files(expected_files, root_dir):
        drifts.append(Drift(path=unexpected_path, reason="unexpected managed file"))

    return sorted(drifts, key=lambda drift: str(drift.path))


def _render_project_config(spec: ContractSpec) -> str:
    project = spec.project
    lines = [
        TEXT_HEADER,
        "",
        f'model = {_toml_string(project["model"])}',
        f'approval_policy = {_toml_string(project["approval_policy"])}',
        f'sandbox_mode = {_toml_string(project["sandbox_mode"])}',
        f'model_reasoning_effort = {_toml_string(project["model_reasoning_effort"])}',
        "",
        "[features]",
        f'multi_agent = {_toml_bool(project["multi_agent"])}',
        "",
        "[shell_environment_policy]",
        "include_only = [",
        *[
            f"  {_toml_string(value)},"
            for value in project["shell_environment_include_only"]
        ],
        "]",
        "",
    ]

    for agent_name in REQUIRED_AGENTS:
        agent = spec.agents[agent_name]
        lines.extend(
            [
                f"[agents.{agent_name}]",
                f'description = {_toml_string(agent["description"])}',
                f'config_file = {_toml_string(f"./agents/{agent_name}.toml")}',
                "",
            ]
        )

    return _finalize_text(lines)


def _render_agent_config(spec: ContractSpec, agent_name: str) -> str:
    agent = spec.agents[agent_name]
    project = spec.project
    lines = [
        TEXT_HEADER,
        "",
        f'model = {_toml_string(project["model"])}',
        f'approval_policy = {_toml_string(project["approval_policy"])}',
        f'sandbox_mode = {_toml_string(project["sandbox_mode"])}',
        f'model_reasoning_effort = {_toml_string(agent["model_reasoning_effort"])}',
        f'model_instructions_file = {_toml_string(f"../instructions/{agent_name}.md")}',
        "",
        "[features]",
        f'multi_agent = {_toml_bool(agent["multi_agent"])}',
    ]
    return _finalize_text(lines)


def _render_policy(spec: ContractSpec) -> str:
    quality = spec.policy["quality"]
    main = spec.policy["main"]
    lines = [
        TEXT_HEADER,
        "",
        "[quality]",
        f'plan_required = {_toml_bool(quality["plan_required"])}',
        f'critique_required = {_toml_bool(quality["critique_required"])}',
        f'critique_max_rounds = {quality["critique_max_rounds"]}',
        f'test_fix_loops = {quality["test_fix_loops"]}',
        f'review_required = {_toml_bool(quality["review_required"])}',
        f'merge_human_approval = {_toml_bool(quality["merge_human_approval"])}',
        f'allow_user_override = {_toml_bool(quality["allow_user_override"])}',
        f'allow_repo_override = {_toml_bool(quality["allow_repo_override"])}',
        "",
        "[main]",
        f'main_allow_feature_work = {_toml_bool(main["main_allow_feature_work"])}',
        f'main_allow_hotfix = {_toml_bool(main["main_allow_hotfix"])}',
        f'main_allow_plan_review = {_toml_bool(main["main_allow_plan_review"])}',
        f'auto_fork_feature_workspace_from_main = {_toml_bool(main["auto_fork_feature_workspace_from_main"])}',
        "hotfix_keywords = [",
        *[f"  {_toml_string(value)}," for value in main["hotfix_keywords"]],
        "]",
        "plan_review_keywords = [",
        *[f"  {_toml_string(value)}," for value in main["plan_review_keywords"]],
        "]",
    ]
    return _finalize_text(lines)


def _render_text_file(body: str) -> str:
    return _finalize_text([TEXT_HEADER, "", body])


def _render_markdown_file(body: str) -> str:
    return _finalize_text([MARKDOWN_HEADER, "", body])


def _render_contract_for_root(spec: ContractSpec, root_dir: Path) -> dict[Path, str]:
    if root_dir == spec.root_dir:
        return render_contract(spec)

    rendered = render_contract(spec)
    remapped: dict[Path, str] = {}
    for path, content in rendered.items():
        remapped[root_dir / path.relative_to(spec.root_dir)] = content
    return remapped


def _find_unexpected_managed_files(
    expected_files: dict[Path, str], root_dir: Path
) -> list[Path]:
    expected_paths = {path.resolve() for path in expected_files}
    checks = (
        (
            root_dir / AGENTS_DIR_RELATIVE_PATH,
            "*.toml",
        ),
        (
            root_dir / INSTRUCTIONS_DIR_RELATIVE_PATH,
            "*.md",
        ),
        (
            root_dir / PROMPTS_DIR_RELATIVE_PATH,
            "*.md",
        ),
        (
            (root_dir / RULES_RELATIVE_PATH).parent,
            "*.rules",
        ),
    )

    unexpected_paths: list[Path] = []
    for directory, pattern in checks:
        if not directory.exists():
            continue
        for path in directory.glob(pattern):
            resolved = path.resolve()
            if resolved not in expected_paths:
                unexpected_paths.append(resolved)
    return sorted(unexpected_paths)


def _load_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise CodexContractError(f"Invalid TOML in {path}: {exc}") from exc


def _require_table(mapping: dict, key: str, context: str | None = None) -> dict:
    value = mapping.get(key)
    label = context or key
    if not isinstance(value, dict):
        raise CodexContractError(f"Missing table '{label}' in {MANIFEST_FILE_NAME}")
    return value


def _require_string(mapping: dict, key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CodexContractError(f"Missing string '{context}.{key}' in {MANIFEST_FILE_NAME}")
    return value


def _require_bool(mapping: dict, key: str, context: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise CodexContractError(f"Missing bool '{context}.{key}' in {MANIFEST_FILE_NAME}")
    return value


def _require_int(mapping: dict, key: str, context: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int):
        raise CodexContractError(f"Missing int '{context}.{key}' in {MANIFEST_FILE_NAME}")
    return value


def _require_string_list(mapping: dict, key: str, context: str) -> list[str]:
    value = mapping.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise CodexContractError(
            f"Missing string list '{context}.{key}' in {MANIFEST_FILE_NAME}"
        )
    return list(value)


def _validate_exact_keys(mapping: dict, expected: tuple[str, ...], context: str) -> None:
    actual_keys = set(mapping.keys())
    expected_keys = set(expected)
    missing = sorted(expected_keys - actual_keys)
    extra = sorted(actual_keys - expected_keys)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"extra: {', '.join(extra)}")
        raise CodexContractError(f"Invalid keys for '{context}' in {MANIFEST_FILE_NAME}: {'; '.join(details)}")


def _reject_unknown_keys(mapping: dict, allowed: set[str], context: str) -> None:
    unknown = sorted(set(mapping.keys()) - allowed)
    if unknown:
        raise CodexContractError(
            f"Unknown keys for '{context}' in {MANIFEST_FILE_NAME}: {', '.join(unknown)}"
        )


def _normalize_block(value: str) -> str:
    return value.strip("\n")


def _toml_string(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _toml_bool(value: object) -> str:
    return "true" if bool(value) else "false"


def _finalize_text(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"
