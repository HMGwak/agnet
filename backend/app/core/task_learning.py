from __future__ import annotations

from pathlib import Path
from typing import Any


LEARNING_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "classification": {
            "type": "string",
            "enum": ["note_only", "skill_candidate"],
        },
        "technique_name": {"type": "string"},
        "why_reusable": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
        },
        "skill": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "use_when": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "do_not_use_when": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "name",
                "description",
                "use_when",
                "do_not_use_when",
                "steps",
            ],
        },
    },
    "required": [
        "summary",
        "classification",
        "technique_name",
        "why_reusable",
        "evidence",
        "skill",
    ],
}


class TaskLearningService:
    def __init__(self, agent_runner, event_sink, registry):
        self.codex = agent_runner
        self.events = event_sink
        self.registry = registry

    async def capture_success(
        self,
        *,
        workspace_path: Path,
        task_id: int,
        task_input: str,
        task_title: str,
        plan_text: str,
        exploration_text: str,
        test_output: str,
        review_output: str,
        verify_output: str,
        diff_text: str,
        repo_name: str,
        workspace_name: str,
        branch_name: str,
        base_branch: str,
        log_callback,
    ) -> dict[str, str | None]:
        reflection = await self.codex.reflect_task_learning(
            workspace_path,
            task_id=task_id,
            task_input=task_input,
            plan_text=plan_text,
            exploration_text=exploration_text,
            test_output=test_output,
            review_output=review_output,
            verify_output=verify_output,
            diff_text=diff_text,
            repo_name=repo_name,
            workspace_name=workspace_name,
            branch_name=branch_name,
            base_branch=base_branch,
            log_callback=log_callback,
            output_schema=LEARNING_OUTPUT_SCHEMA,
        )
        result = self.registry.save_reflection(
            task_id=task_id,
            task_title=task_title,
            reflection=reflection,
        )
        await self.events.log(task_id, f"학습 회고 저장: {result['reflection_path']}")
        if result["skill_path"]:
            await self.events.log(task_id, f"생성된 skill draft: {result['skill_path']}")
        else:
            await self.events.log(task_id, "학습 결과는 note_only로 분류되어 skill 생성은 생략했습니다.")
        return result
