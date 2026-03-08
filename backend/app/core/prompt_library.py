from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template


class PromptLibraryError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptLibrary:
    templates: dict[str, Template]

    REQUIRED_TEMPLATES = ("plan", "critique", "implement", "test", "review")

    @classmethod
    def load_from_directory(cls, directory: Path) -> "PromptLibrary":
        if not directory.exists():
            raise PromptLibraryError(f"Missing prompts directory: {directory}")

        templates: dict[str, Template] = {}
        for name in cls.REQUIRED_TEMPLATES:
            path = directory / f"{name}.md"
            if not path.exists():
                raise PromptLibraryError(f"Missing prompt template: {path}")
            templates[name] = Template(path.read_text(encoding="utf-8"))
        return cls(templates=templates)

    def render(self, name: str, **context: object) -> str:
        template = self.templates.get(name)
        if template is None:
            raise PromptLibraryError(f"Unknown prompt template: {name}")

        normalized = {key: "" if value is None else str(value) for key, value in context.items()}
        try:
            return template.substitute(normalized).strip()
        except KeyError as exc:
            raise PromptLibraryError(
                f"Missing prompt variable '{exc.args[0]}' for template '{name}'"
            ) from exc
