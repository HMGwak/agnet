from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any


class LearningRegistry:
    def __init__(
        self,
        *,
        reflections_dir: Path,
        registry_file: Path,
        generated_skills_dir: Path,
    ):
        self.reflections_dir = reflections_dir
        self.registry_file = registry_file
        self.generated_skills_dir = generated_skills_dir

    def save_reflection(
        self,
        *,
        task_id: int,
        task_title: str,
        reflection: dict[str, Any],
    ) -> dict[str, str | None]:
        timestamp = datetime.now(UTC).isoformat()
        self.reflections_dir.mkdir(parents=True, exist_ok=True)
        reflection_path = self.reflections_dir / f"task-{task_id}.json"
        payload = {
            "task_id": task_id,
            "task_title": task_title,
            "saved_at": timestamp,
            "reflection": reflection,
        }
        reflection_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        skill_path: Path | None = None
        if reflection.get("classification") == "skill_candidate":
            skill_path = self._write_skill(task_id=task_id, reflection=reflection)

        self._upsert_registry_entry(
            {
                "task_id": task_id,
                "task_title": task_title,
                "saved_at": timestamp,
                "classification": str(reflection.get("classification") or ""),
                "technique_name": str(reflection.get("technique_name") or ""),
                "reflection_path": str(reflection_path),
                "skill_name": self._skill_name(reflection),
                "skill_path": str(skill_path) if skill_path else None,
            }
        )
        return {
            "reflection_path": str(reflection_path),
            "skill_path": str(skill_path) if skill_path else None,
        }

    def _write_skill(self, *, task_id: int, reflection: dict[str, Any]) -> Path:
        skill = reflection.get("skill")
        if not isinstance(skill, dict):
            raise ValueError("Skill candidate reflection is missing skill payload")

        skill_name = self._skill_name(reflection)
        description = str(skill.get("description") or "").strip()
        use_when = self._normalize_lines(skill.get("use_when"))
        do_not_use_when = self._normalize_lines(skill.get("do_not_use_when"))
        steps = self._normalize_lines(skill.get("steps"))
        use_when_lines = [f"- {line}" for line in use_when] or ["- Use when the same technique applies."]
        do_not_use_when_lines = [f"- {line}" for line in do_not_use_when] or [
            "- Do not use for one-off or unrelated tasks."
        ]
        step_lines = [f"{index}. {line}" for index, line in enumerate(steps, start=1)] or [
            "1. Follow the technique described by the source task."
        ]

        slug = self._slugify(skill_name or f"task-{task_id}-skill")
        skill_dir = self.generated_skills_dir / f"{slug}-task-{task_id}"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        lines = [
            "---",
            f"name: {skill_name or f'task-{task_id}-skill'}",
            f"description: {description or 'Generated reusable technique from a completed task'}",
            "---",
            "",
            "# Purpose",
            "",
            str(reflection.get("summary") or "").strip(),
            "",
            "## Use_When",
            "",
            *use_when_lines,
            "",
            "## Do_Not_Use_When",
            "",
            *do_not_use_when_lines,
            "",
            "## Steps",
            "",
            *step_lines,
            "",
            "## Source",
            "",
            f"- Generated from task #{task_id}",
            f"- Technique: {str(reflection.get('technique_name') or '').strip()}",
        ]
        skill_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return skill_path

    def _upsert_registry_entry(self, entry: dict[str, Any]) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, Any]] = []
        if self.registry_file.exists():
            try:
                raw = json.loads(self.registry_file.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    entries = [item for item in raw if isinstance(item, dict)]
            except json.JSONDecodeError:
                entries = []

        entries = [item for item in entries if item.get("task_id") != entry["task_id"]]
        entries.append(entry)
        entries.sort(key=lambda item: int(item.get("task_id", 0)))
        self.registry_file.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _skill_name(self, reflection: dict[str, Any]) -> str | None:
        skill = reflection.get("skill")
        if isinstance(skill, dict):
            name = str(skill.get("name") or "").strip()
            if name:
                return name
        return None

    def _normalize_lines(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "generated-skill"
