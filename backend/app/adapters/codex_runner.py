from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.core.codex_project_config import CodexProjectConfig
from app.core.project_policy import ProjectPolicy
from app.core.prompt_library import PromptLibrary


class CodexRunner:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        sandbox_mode: str,
        approval_policy: str,
        run_timeout_s: int,
        prompt_library: PromptLibrary,
        policy: ProjectPolicy,
        project_config: CodexProjectConfig,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.sandbox_mode = sandbox_mode
        self.approval_policy = approval_policy
        self.run_timeout_ms = run_timeout_s * 1000
        self.prompts = prompt_library
        self.policy = policy
        self.project_config = project_config
        self._task_runs: dict[int, str] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def format_task_input(task_title: str, task_description: str) -> str:
        title = task_title.strip()
        description = task_description.strip()

        if not description:
            return title
        if not title or description == title:
            return description
        return f"Title: {title}\nDescription: {description}"

    async def cancel(self, task_id: int):
        async with self._lock:
            run_id = self._task_runs.pop(task_id, None)
        if not run_id:
            return

        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            await client.post(f"/runs/{run_id}/cancel")

    async def run_codex(
        self,
        prompt: str,
        cwd: Path,
        *,
        log_callback=None,
        task_id: int | None = None,
        phase: str = "generic",
        agent_name: str | None = None,
        **_ignored,
    ) -> tuple[int, str]:
        payload = {
            "phase": phase,
            "prompt": prompt,
            "workingDirectory": str(cwd),
            "model": self.model,
            "sandboxMode": self.sandbox_mode,
            "approvalPolicy": self.approval_policy,
            "timeoutMs": self.run_timeout_ms,
        }
        if agent_name:
            payload["config"] = self.project_config.build_agent_config(agent_name)

        run_timeout = httpx.Timeout(connect=30.0, read=None, write=30.0, pool=30.0)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=run_timeout) as client:
            response = await client.post("/runs", json=payload)
            response.raise_for_status()
            body = response.json()
            run_id = body.get("run_id") or body.get("runId")
            if not run_id:
                raise ValueError("Codex sidecar did not return a run id")

            if task_id is not None:
                async with self._lock:
                    self._task_runs[task_id] = run_id

            final_output = ""
            exit_code = 1
            failure_message = ""
            async with client.stream(
                "GET",
                f"/runs/{run_id}/events",
                headers={"accept": "text/event-stream"},
            ) as stream:
                stream.raise_for_status()
                async for line in stream.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        event = json.loads(line[6:])
                    else:
                        event = json.loads(line)
                    event_type = event.get("type")
                    if event_type == "item.completed" and event.get("item", {}).get("type") == "agent_message":
                        text = str(event["item"].get("text", ""))
                        if text and log_callback:
                            await log_callback(text)
                        final_output = text or final_output
                    elif event_type == "turn.failed":
                        failure_message = str(event.get("error", {}).get("message", "Codex run failed"))
                        exit_code = 1
                    elif event_type == "state":
                        status = str(event.get("status", "failed"))
                        if status == "done":
                            exit_code = 0
                        elif status == "cancelled":
                            failure_message = failure_message or "cancelled"
                            exit_code = 1
                        elif status == "failed":
                            exit_code = 1

            if task_id is not None:
                async with self._lock:
                    self._task_runs.pop(task_id, None)

            if exit_code == 0:
                return 0, final_output
            return 1, failure_message or final_output

    async def run_intake(self, prompt: str, cwd: Path, output_schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "prompt": prompt,
            "workingDirectory": str(cwd),
            "model": self.model,
            "sandboxMode": self.sandbox_mode,
            "approvalPolicy": self.approval_policy,
            "timeoutMs": self.run_timeout_ms,
            "outputSchema": output_schema,
            "config": self.project_config.build_agent_config("intake"),
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=120.0) as client:
            response = await client.post("/intake", json=payload)
            response.raise_for_status()
            body = response.json()
        payload = body.get("response") or body.get("draft")
        if not isinstance(body, dict) or not isinstance(payload, dict):
            raise ValueError("Task intake did not return structured JSON")
        return payload

    def _prompt_context(self, workspace_path: Path, **context: Any) -> dict[str, str]:
        base = {
            "working_directory": str(workspace_path),
            "model": self.model,
            "sandbox_mode": self.sandbox_mode,
            "approval_policy": self.approval_policy,
            "critique_max_rounds": str(self.policy.critique_max_rounds),
            "test_fix_loops": str(self.policy.test_fix_loops),
        }
        for key, value in context.items():
            base[key] = "" if value is None else str(value)
        return base

    async def generate_plan(
        self, workspace_path: Path, task_description: str, **kw
    ) -> tuple[int, str]:
        kw.setdefault("agent_name", "planner")
        prompt = self.prompts.render(
            "plan",
            task_input=task_description,
            **self._prompt_context(workspace_path, **kw),
        )
        return await self.run_codex(prompt, cwd=workspace_path, phase="plan", **kw)

    async def critique_plan(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        **kw,
    ) -> tuple[int, str]:
        kw.setdefault("agent_name", "critic")
        prompt = self.prompts.render(
            "critique",
            task_input=task_description,
            plan_text=plan_text,
            **self._prompt_context(workspace_path, **kw),
        )
        return await self.run_codex(prompt, cwd=workspace_path, phase="critique", **kw)

    async def implement_plan(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        **kw,
    ) -> tuple[int, str]:
        kw.setdefault("agent_name", "executor")
        prompt = self.prompts.render(
            "implement",
            task_input=task_description,
            plan_text=plan_text,
            **self._prompt_context(workspace_path, **kw),
        )
        return await self.run_codex(prompt, cwd=workspace_path, phase="implement", **kw)

    async def run_tests(
        self,
        workspace_path: Path,
        *,
        plan_text: str = "",
        task_description: str = "",
        **kw,
    ) -> tuple[int, str]:
        kw.setdefault("agent_name", "tester")
        prompt = self.prompts.render(
            "test",
            task_input=task_description,
            plan_text=plan_text,
            **self._prompt_context(workspace_path, **kw),
        )
        return await self.run_codex(prompt, cwd=workspace_path, phase="test", **kw)

    async def review_result(
        self,
        workspace_path: Path,
        plan_text: str,
        task_description: str,
        test_output: str,
        diff_text: str,
        **kw,
    ) -> tuple[int, str]:
        kw.setdefault("agent_name", "reviewer")
        prompt = self.prompts.render(
            "review",
            task_input=task_description,
            plan_text=plan_text,
            test_output=test_output,
            diff_text=diff_text,
            **self._prompt_context(workspace_path, **kw),
        )
        return await self.run_codex(prompt, cwd=workspace_path, phase="review", **kw)
