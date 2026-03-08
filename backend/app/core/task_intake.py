from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.core.project_policy import ProjectPolicy
from app.core.policies import slugify
from app.schemas import (
    TaskIntakeDraft,
    TaskIntakeRequest,
    TaskIntakeResponse,
)


class TaskIntakeService:
    def __init__(self, store, codex, policy: ProjectPolicy):
        self.store = store
        self.codex = codex
        self.policy = policy

    async def analyze(self, db, body: TaskIntakeRequest) -> TaskIntakeResponse:
        repo = await self.store.get_repo(db, body.repo_id)
        if repo is None:
            raise LookupError("Repo not found")

        workspaces = await self.store.list_workspaces(db, repo.id)
        tasks = await self.store.list_tasks(db, repo_id=repo.id)

        prompt = self._build_prompt(
            repo_name=repo.name,
            repo_path=repo.path,
            default_branch=repo.default_branch,
            workspaces=workspaces,
            tasks=tasks,
            user_request=body.user_request,
            conversation=body.conversation,
            current_draft=body.draft,
        )
        try:
            payload = await self.codex.run_intake(
                prompt,
                cwd=Path(repo.path),
                output_schema=self._response_schema(),
            )
            return TaskIntakeResponse.model_validate(payload)
        except (httpx.HTTPError, OSError, RuntimeError):
            pass

        return self._fallback_response(
            workspaces=workspaces,
            tasks=tasks,
            user_request=body.user_request,
            conversation=body.conversation,
            current_draft=body.draft,
        )

    def _response_schema(self) -> dict:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "draft": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "workspace_mode": {"type": "string", "enum": ["existing", "new", "unspecified"]},
                        "workspace_id": {"type": ["integer", "null"]},
                        "new_workspace_name": {"type": ["string", "null"]},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "blocked_by_task_id": {"type": ["integer", "null"]},
                        "scheduled_for": {"type": ["string", "null"]},
                    },
                    "required": [
                        "workspace_mode",
                        "workspace_id",
                        "new_workspace_name",
                        "title",
                        "description",
                        "blocked_by_task_id",
                        "scheduled_for",
                    ],
                },
                "questions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "needs_confirmation": {"type": "boolean"},
                "notes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["draft", "questions", "needs_confirmation", "notes"],
        }

    def _build_prompt(
        self,
        *,
        repo_name: str,
        repo_path: str,
        default_branch: str,
        workspaces: list,
        tasks: list,
        user_request: str,
        conversation: list,
        current_draft: TaskIntakeDraft | None,
    ) -> str:
        workspace_lines = [
            json.dumps(
                {
                    "id": workspace.id,
                    "name": workspace.name,
                    "kind": getattr(workspace.kind, "value", str(workspace.kind)),
                    "branch_name": workspace.branch_name,
                    "task_count": getattr(workspace, "task_count", 0),
                    "workspace_path": workspace.workspace_path,
                },
                ensure_ascii=False,
            )
            for workspace in workspaces
        ]
        task_lines = [
            json.dumps(
                {
                    "id": task.id,
                    "title": task.title,
                    "status": getattr(task.status, "value", str(task.status)),
                    "workspace_id": task.workspace_id,
                    "workspace_name": getattr(task, "workspace_name", None),
                    "scheduled_for": task.scheduled_for.isoformat() if task.scheduled_for else None,
                },
                ensure_ascii=False,
            )
            for task in tasks[:20]
        ]
        conversation_lines = [
            json.dumps({"role": turn.role, "message": turn.message}, ensure_ascii=False)
            for turn in conversation
        ]
        draft_payload = current_draft.model_dump(mode="json") if current_draft else None

        return (
            "You are an intake assistant for a local AI task board.\n"
            "Read the repository-scoped context and convert the user's request into a task draft.\n"
            "Return JSON only. Do not include markdown fences or any extra text.\n"
            "If key information is missing, ask concise follow-up questions in `questions`.\n"
            "Only use the provided repository context. Do not invent workspace ids or task ids.\n"
            "This project uses a fixed internal quality pipeline: Planner -> Critic -> Executor -> Tester -> Reviewer -> Human Merge Approval.\n"
            "Prefer an existing workspace when the request sounds like continuing existing work.\n"
            "Prefer a new workspace when the request sounds isolated or new.\n"
            "If unsure about workspace choice, set `workspace_mode` to `unspecified` and ask.\n"
            "The main workspace is protected. New feature work requested on main must use a feature workspace.\n"
            "Hotfix, planning, review, and triage work may stay on main.\n"
            "Only set `blocked_by_task_id` when the request explicitly depends on an existing task.\n"
            "Only set `scheduled_for` when the request clearly specifies a time.\n"
            "Use this JSON schema exactly:\n"
            "{\n"
            '  "draft": {\n'
            '    "workspace_mode": "existing" | "new" | "unspecified",\n'
            '    "workspace_id": number | null,\n'
            '    "new_workspace_name": string | null,\n'
            '    "title": string,\n'
            '    "description": string,\n'
            '    "blocked_by_task_id": number | null,\n'
            '    "scheduled_for": string | null\n'
            "  },\n"
            '  "questions": ["question"],\n'
            '  "needs_confirmation": true,\n'
            '  "notes": ["short note"]\n'
            "}\n\n"
            f"Repository name: {repo_name}\n"
            f"Repository path: {repo_path}\n"
            f"Default branch: {default_branch}\n"
            f"Available workspaces ({len(workspaces)}):\n"
            + ("\n".join(workspace_lines) if workspace_lines else "(none)")
            + "\n\n"
            + f"Recent tasks ({min(len(tasks), 20)} shown):\n"
            + ("\n".join(task_lines) if task_lines else "(none)")
            + "\n\n"
            + "Current draft:\n"
            + json.dumps(draft_payload, ensure_ascii=False)
            + "\n\n"
            + "Policy summary:\n"
            + json.dumps(
                {
                    "plan_required": self.policy.plan_required,
                    "critique_required": self.policy.critique_required,
                    "critique_max_rounds": self.policy.critique_max_rounds,
                    "test_fix_loops": self.policy.test_fix_loops,
                    "review_required": self.policy.review_required,
                    "merge_human_approval": self.policy.merge_human_approval,
                    "main_allow_feature_work": self.policy.main_allow_feature_work,
                    "main_allow_hotfix": self.policy.main_allow_hotfix,
                    "main_allow_plan_review": self.policy.main_allow_plan_review,
                },
                ensure_ascii=False,
            )
            + "\n\n"
            + "Conversation so far:\n"
            + ("\n".join(conversation_lines) if conversation_lines else "(none)")
            + "\n\n"
            + "Latest user request:\n"
            + user_request.strip()
        )

    def _parse_response(self, output: str) -> TaskIntakeResponse:
        payload = self._extract_json(output)
        try:
            return TaskIntakeResponse.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Invalid intake response: {exc}") from exc

    def _extract_json(self, output: str) -> dict:
        cleaned = output.strip()
        if not cleaned:
            raise ValueError("Task intake returned an empty response")

        candidates = [cleaned]
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    candidates.append(part[4:].strip())
                elif part.startswith("{"):
                    candidates.append(part)

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(cleaned[start : end + 1])

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

        raise ValueError("Task intake did not return valid JSON")

    def _fallback_response(
        self,
        *,
        workspaces: list,
        tasks: list,
        user_request: str,
        conversation: list,
        current_draft: TaskIntakeDraft | None,
    ) -> TaskIntakeResponse:
        text = " ".join(
            part.strip()
            for part in [current_draft.title if current_draft else "", user_request, *(turn.message for turn in conversation)]
            if part and part.strip()
        ).strip()
        lowered = text.lower()

        prefers_existing = self._has_any(
            lowered,
            "continue",
            "continuing",
            "follow-up",
            "fix",
            "update",
            "resume",
            "이어",
            "수정",
            "계속",
            "후속",
            "재개",
        )
        prefers_new = self._has_any(
            lowered,
            "create",
            "build",
            "make",
            "new",
            "standalone",
            "separate",
            "implement",
            "만들",
            "구현",
            "새",
            "신규",
            "별도",
            "독립",
        )

        main_workspace = next(
            (workspace for workspace in workspaces if getattr(workspace.kind, "value", workspace.kind) == "MAIN"),
            None,
        )
        feature_workspaces = [
            workspace
            for workspace in workspaces
            if getattr(workspace.kind, "value", workspace.kind) == "FEATURE"
        ]
        recent_task = tasks[0] if tasks else None

        if current_draft is not None:
            draft = current_draft.model_copy(deep=True)
        else:
            draft = TaskIntakeDraft()

        title = self._derive_title(user_request or text)
        if title and not draft.title:
            draft.title = title
        if not draft.description:
            draft.description = self._build_description(draft.title or title, user_request or text)

        questions: list[str] = []
        notes = ["Draft generated from the request because the AI response was not structured."]

        if draft.workspace_mode == "unspecified":
            if prefers_existing and feature_workspaces:
                draft.workspace_mode = "existing"
                draft.workspace_id = feature_workspaces[0].id
                notes.append(f"Continuing in workspace '{feature_workspaces[0].name}'.")
            elif prefers_existing and main_workspace:
                draft.workspace_mode = "existing"
                draft.workspace_id = main_workspace.id
                notes.append("Continuing in the main workspace.")
            elif prefers_new:
                draft.workspace_mode = "new"
                draft.workspace_id = None
                draft.new_workspace_name = self._suggest_workspace_name(draft.title or user_request)
                notes.append(f"Suggested a new workspace '{draft.new_workspace_name}'.")
            elif len(feature_workspaces) == 1:
                draft.workspace_mode = "existing"
                draft.workspace_id = feature_workspaces[0].id
                questions.append(
                    f"Should this continue in '{feature_workspaces[0].name}' or use a new workspace?"
                )
            else:
                questions.append("Should this use an existing workspace or create a new one?")

        if draft.workspace_mode == "existing" and draft.workspace_id is None:
            if len(feature_workspaces) == 1:
                draft.workspace_id = feature_workspaces[0].id
            elif main_workspace is not None and not feature_workspaces:
                draft.workspace_id = main_workspace.id
            else:
                questions.append("Which existing workspace should this task use?")

        if draft.workspace_mode == "new" and not draft.new_workspace_name:
            draft.new_workspace_name = self._suggest_workspace_name(draft.title or user_request)

        if draft.blocked_by_task_id is None and recent_task and self._has_any(
            lowered, "after task", "after", "다음", "이후", "끝나고"
        ):
            draft.blocked_by_task_id = recent_task.id
            notes.append(f"Linked dependency to recent task #{recent_task.id}.")

        needs_confirmation = len(questions) == 0
        return TaskIntakeResponse(
            draft=draft,
            questions=questions,
            needs_confirmation=needs_confirmation,
            notes=notes,
        )

    @staticmethod
    def _has_any(text: str, *keywords: str) -> bool:
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _derive_title(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"[.!?]+$", "", cleaned)
        if len(cleaned) <= 80:
            return cleaned
        return cleaned[:77].rstrip() + "..."

    @staticmethod
    def _suggest_workspace_name(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        cleaned = re.sub(r"[^\w\s-]", "", cleaned, flags=re.UNICODE).strip()
        if cleaned:
            return cleaned[:60]
        slug = slugify(text)
        if not slug:
            slug = "new-task"
        return f"Task {slug}"

    @staticmethod
    def _build_description(title: str, request: str) -> str:
        cleaned_request = re.sub(r"\s+", " ", request).strip()
        cleaned_title = re.sub(r"\s+", " ", title).strip() or "Requested task"
        if re.search(r"[가-힣]", cleaned_request or cleaned_title):
            return (
                f"{cleaned_request or cleaned_title}.\n\n"
                f"이 작업은 '{cleaned_title}' 요청을 실제로 사용할 수 있는 결과물로 구현하는 것을 목표로 한다.\n"
                "필요한 코드, 자산, 연결 지점을 함께 정리하고 기존 흐름과 자연스럽게 통합한다."
            )
        return (
            f"{cleaned_request or cleaned_title}.\n\n"
            f"This task should turn '{cleaned_title}' into a usable implementation.\n"
            "Update the necessary code, assets, and integration points so the result fits the existing workflow."
        )
