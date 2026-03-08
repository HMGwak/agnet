from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import tomllib


class CodexProjectConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodexProjectConfig:
    project_dir: Path
    config_path: Path
    base_config: dict
    agent_files: dict[str, Path]
    rule_files: tuple[Path, ...] = ()

    @classmethod
    def load_from_file(cls, config_path: Path) -> "CodexProjectConfig":
        if not config_path.exists():
            raise CodexProjectConfigError(f"Missing project Codex config: {config_path}")

        config_dir = config_path.parent
        raw = _load_toml(config_path)
        resolved = _resolve_path_values(raw, config_dir)
        agents = resolved.get("agents")
        if not isinstance(agents, dict) or not agents:
            raise CodexProjectConfigError("Project Codex config must define at least one agent")

        agent_files: dict[str, Path] = {}
        for name, payload in agents.items():
            if not isinstance(payload, dict):
                raise CodexProjectConfigError(f"Agent '{name}' must be a table")
            config_file = payload.get("config_file")
            if not isinstance(config_file, str) or not config_file:
                raise CodexProjectConfigError(f"Agent '{name}' is missing config_file")
            agent_path = Path(config_file)
            if not agent_path.exists():
                raise CodexProjectConfigError(
                    f"Agent '{name}' config file does not exist: {agent_path}"
                )
            agent_files[name] = agent_path

        rules_dir = config_dir / "rules"
        rule_files = tuple(sorted(rules_dir.glob("*.rules"))) if rules_dir.exists() else ()

        return cls(
            project_dir=config_dir,
            config_path=config_path,
            base_config=resolved,
            agent_files=agent_files,
            rule_files=rule_files,
        )

    def build_agent_config(self, agent_name: str) -> dict:
        agent_path = self.agent_files.get(agent_name)
        if agent_path is None:
            raise CodexProjectConfigError(f"Unknown project Codex agent: {agent_name}")

        merged = deepcopy(self.base_config)
        agent_config = _resolve_path_values(_load_toml(agent_path), agent_path.parent)
        _deep_merge(merged, agent_config)
        merged = self._inject_rules_into_instructions(agent_name, merged)
        return merged

    def _inject_rules_into_instructions(self, agent_name: str, config: dict) -> dict:
        instruction_file = config.get("model_instructions_file")
        if not isinstance(instruction_file, str) and not self.rule_files:
            return config

        content_parts: list[str] = []
        rules_text = self._read_rules_text()
        if rules_text:
            content_parts.append(f"Project rules:\n\n{rules_text}")

        if isinstance(instruction_file, str):
            instruction_path = Path(instruction_file)
            if not instruction_path.exists():
                raise CodexProjectConfigError(
                    f"Instruction file does not exist: {instruction_path}"
                )
            content_parts.append(instruction_path.read_text(encoding="utf-8").strip())

        if not content_parts:
            return config

        generated_dir = self.project_dir / ".generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        generated_path = generated_dir / f"{agent_name}.md"
        generated_path.write_text(
            "\n\n".join(part for part in content_parts if part).strip() + "\n",
            encoding="utf-8",
        )
        config["model_instructions_file"] = str(generated_path)
        return config

    def _read_rules_text(self) -> str:
        parts: list[str] = []
        for rule_file in self.rule_files:
            text = rule_file.read_text(encoding="utf-8").strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts)


def _load_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise CodexProjectConfigError(f"Invalid TOML in {path}: {exc}") from exc


def _resolve_path_values(value, base_dir: Path):
    if isinstance(value, dict):
        resolved = {}
        for key, child in value.items():
            if isinstance(child, str) and key.endswith("_file"):
                resolved[key] = str(_resolve_relative_path(child, base_dir))
            else:
                resolved[key] = _resolve_path_values(child, base_dir)
        return resolved
    if isinstance(value, list):
        return [_resolve_path_values(item, base_dir) for item in value]
    return value


def _resolve_relative_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _deep_merge(target: dict, source: dict) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)
