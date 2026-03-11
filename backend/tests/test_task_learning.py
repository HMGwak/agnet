from pathlib import Path

import json
import pytest

from app.adapters.learning_registry import LearningRegistry
from app.core.task_learning import TaskLearningService


class FakeRunner:
    def __init__(self, reflection: dict):
        self.reflection = reflection
        self.calls: list[dict] = []

    async def reflect_task_learning(self, workspace_path: Path, **kw) -> dict:
        self.calls.append({"workspace_path": workspace_path, **kw})
        return self.reflection


class FakeEvents:
    def __init__(self):
        self.logs: list[tuple[int, str]] = []

    async def log(self, task_id: int, line: str) -> None:
        self.logs.append((task_id, line))


@pytest.mark.asyncio
async def test_task_learning_service_saves_note_only_reflection(tmp_path):
    registry = LearningRegistry(
        reflections_dir=tmp_path / "project" / "learnings" / "reflections",
        registry_file=tmp_path / "project" / "learnings" / "registry.json",
        generated_skills_dir=tmp_path / "runtime" / "codex" / "home" / "skills" / "generated",
    )
    runner = FakeRunner(
        {
            "summary": "Useful note, not a reusable skill.",
            "classification": "note_only",
            "technique_name": "One-off repo workaround",
            "why_reusable": "Too specific to this repository.",
            "evidence": ["Adjusted a one-off config file."],
            "skill": None,
        }
    )
    events = FakeEvents()
    service = TaskLearningService(runner, events, registry)

    result = await service.capture_success(
        workspace_path=tmp_path,
        task_id=7,
        task_input="Fix issue",
        task_title="Fix issue",
        plan_text="1. Fix issue",
        exploration_text="repo summary",
        test_output="tests ok",
        review_output="review ok",
        verify_output="verify ok",
        diff_text="diff",
        repo_name="demo",
        workspace_name="Main",
        branch_name="workspace/main/1",
        base_branch="main",
        log_callback=None,
    )

    assert Path(result["reflection_path"]).exists()
    assert result["skill_path"] is None
    registry_payload = json.loads((tmp_path / "project" / "learnings" / "registry.json").read_text(encoding="utf-8"))
    assert registry_payload[0]["classification"] == "note_only"


@pytest.mark.asyncio
async def test_task_learning_service_writes_generated_skill_for_skill_candidate(tmp_path):
    registry = LearningRegistry(
        reflections_dir=tmp_path / "project" / "learnings" / "reflections",
        registry_file=tmp_path / "project" / "learnings" / "registry.json",
        generated_skills_dir=tmp_path / "runtime" / "codex" / "home" / "skills" / "generated",
    )
    runner = FakeRunner(
        {
            "summary": "Reusable Playwright parsing flow.",
            "classification": "skill_candidate",
            "technique_name": "Playwright table parsing",
            "why_reusable": "The selector and normalization pattern repeats across scraping tasks.",
            "evidence": ["Stable row selectors", "Column normalization"],
            "skill": {
                "name": "playwright-table-parsing",
                "description": "Extract DOM table data with stable selectors and normalization.",
                "use_when": ["Parsing HTML tables with Playwright."],
                "do_not_use_when": ["The source is an API response instead of DOM."],
                "steps": ["Find stable row selectors.", "Normalize cell values.", "Validate row count."],
            },
        }
    )
    events = FakeEvents()
    service = TaskLearningService(runner, events, registry)

    result = await service.capture_success(
        workspace_path=tmp_path,
        task_id=9,
        task_input="Parse legislation table",
        task_title="Parse legislation table",
        plan_text="1. Parse the table",
        exploration_text="DOM structure summary",
        test_output="tests ok",
        review_output="review ok",
        verify_output="verify ok",
        diff_text="diff",
        repo_name="demo",
        workspace_name="Main",
        branch_name="workspace/main/1",
        base_branch="main",
        log_callback=None,
    )

    assert Path(result["reflection_path"]).exists()
    assert result["skill_path"] is not None
    skill_path = Path(result["skill_path"])
    assert skill_path.exists()
    assert "playwright-table-parsing" in skill_path.read_text(encoding="utf-8")
