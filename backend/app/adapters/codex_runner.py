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
        final_output_idle_timeout_s: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.sandbox_mode = sandbox_mode
        self.approval_policy = approval_policy
        self.run_timeout_ms = run_timeout_s * 1000
        self.prompts = prompt_library
        self.policy = policy
        self.project_config = project_config
        self.final_output_idle_timeout_s = final_output_idle_timeout_s
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
        agent_config = self.project_config.build_agent_config(agent_name) if agent_name else None
        payload = {
            "phase": phase,
            "prompt": prompt,
            "workingDirectory": str(cwd),
            "model": (
                str(agent_config.get("model", self.model))
                if agent_config is not None
                else self.model
            ),
            "sandboxMode": self.sandbox_mode,
            "approvalPolicy": self.approval_policy,
            "timeoutMs": self.run_timeout_ms,
        }
        if agent_config is not None:
            payload["config"] = agent_config

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
                line_iter = stream.aiter_lines()
                while True:
                    try:
                        if final_output and self.final_output_idle_timeout_s > 0:
                            line = await asyncio.wait_for(
                                line_iter.__anext__(),
                                timeout=self.final_output_idle_timeout_s,
                            )
                        else:
                            line = await line_iter.__anext__()
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        snapshot = await client.get(f"/runs/{run_id}/events")
                        snapshot.raise_for_status()
                        snapshot_body = snapshot.json()
                        snapshot_status = str(snapshot_body.get("status", "running"))
                        snapshot_output = self._extract_run_output(snapshot_body)
                        if snapshot_status == "done":
                            exit_code = 0
                            final_output = snapshot_output or final_output
                            break
                        if snapshot_status == "failed":
                            exit_code = 1
                            failure_message = snapshot_output or "Codex run failed"
                            break
                        if snapshot_status == "cancelled":
                            exit_code = 1
                            failure_message = snapshot_output or "cancelled"
                            break
                        if final_output:
                            await self._cancel_run(client, run_id)
                            exit_code = 0
                            break
                        continue
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

            if (exit_code == 0 and not final_output) or (exit_code != 0 and not failure_message):
                result_response = await client.get(f"/runs/{run_id}/events")
                result_response.raise_for_status()
                result_body = result_response.json()
                result_text = str(result_body.get("result", "") or "")
                if exit_code == 0 and result_text:
                    final_output = result_text
                elif exit_code != 0 and result_text:
                    failure_message = result_text

            if task_id is not None:
                async with self._lock:
                    self._task_runs.pop(task_id, None)

            if exit_code == 0:
                return 0, final_output
            return 1, failure_message or final_output

    async def _cancel_run(self, client: httpx.AsyncClient, run_id: str) -> None:
        try:
            await client.post(f"/runs/{run_id}/cancel")
        except Exception:
            pass

    def _extract_run_output(self, run_body: dict[str, Any]) -> str:
        result_text = str(run_body.get("result", "") or "")
        if result_text:
            return result_text
        events = run_body.get("events")
        if not isinstance(events, list):
            return ""
        for event in reversed(events):
            if not isinstance(event, dict):
                continue
            if event.get("type") != "item.completed":
                continue
            item = event.get("item")
            if not isinstance(item, dict) or item.get("type") != "agent_message":
                continue
            text = str(item.get("text", "") or "")
            if text:
                return text
        return ""

    async def run_intake(self, prompt: str, cwd: Path, output_schema: dict[str, Any]) -> dict[str, Any]:
        agent_config = self.project_config.build_agent_config("intake")
        payload = {
            "prompt": prompt,
            "workingDirectory": str(cwd),
            "model": str(agent_config.get("model", self.model)),
            "sandboxMode": self.sandbox_mode,
            "approvalPolicy": self.approval_policy,
            "timeoutMs": self.run_timeout_ms,
            "outputSchema": output_schema,
            "config": agent_config,
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

    async def explore_repo(
        self,
        workspace_path: Path,
        task_description: str,
        **kw,
    ) -> tuple[int, str]:
        kw.setdefault("agent_name", "explorer")
        prompt = self.prompts.render(
            "explore",
            task_input=task_description,
            **self._prompt_context(workspace_path, **kw),
        )
        return await self.run_codex(prompt, cwd=workspace_path, phase="explore", **kw)

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

    async def orchestrate_next_action(
        self,
        workspace_path: Path,
        **kw,
    ) -> tuple[int, str]:
        kw.setdefault("agent_name", "orchestrator")
        prompt = self.prompts.render(
            "orchestrate",
            **self._prompt_context(workspace_path, **kw),
        )
        return await self.run_codex(prompt, cwd=workspace_path, phase="orchestrate", **kw)

    async def generate_recovery_plan(
        self,
        workspace_path: Path,
        task_description: str,
        **kw,
    ) -> tuple[int, str]:
        kw.setdefault("agent_name", "recovery_planner")
        prompt = self.prompts.render(
            "recover",
            task_input=task_description,
            **self._prompt_context(workspace_path, **kw),
        )
        return await self.run_codex(prompt, cwd=workspace_path, phase="recover", **kw)

    async def verify_completion(
        self,
        workspace_path: Path,
        **kw,
    ) -> tuple[int, str]:
        kw.setdefault("agent_name", "verifier")
        prompt = self.prompts.render(
            "verify",
            **self._prompt_context(workspace_path, **kw),
        )
        return await self.run_codex(prompt, cwd=workspace_path, phase="verify", **kw)
