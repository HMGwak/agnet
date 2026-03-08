from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re

from app.core.contracts import AgentRunner, EventSink, WorkspaceManager
from app.models import Repo, Run, Task, TaskStatus, Workspace


class NeedsAttentionError(RuntimeError):
    pass


class SymphonyWorkflowEngine:
    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        agent_runner: AgentRunner,
        event_sink: EventSink,
        session_factory,
    ):
        self.git = workspace_manager
        self.codex = agent_runner
        self.events = event_sink
        self.session_factory = session_factory
        self.worker_pool = None

    def set_worker_pool(self, pool):
        self.worker_pool = pool

    def _build_task_commit_message(self, task: Task) -> str:
        title = re.sub(r"\s+", " ", task.title or "").strip() or "Update workspace"
        return f"Task #{task.id}: {title}"

    def _record_run(self, session, task_id: int, phase: str, exit_code: int) -> None:
        finished_at = datetime.now(UTC)
        session.add(
            Run(
                task_id=task_id,
                phase=phase,
                started_at=finished_at,
                finished_at=finished_at,
                exit_code=exit_code,
                log_path=str(self.events.get_log_path(task_id)),
            )
        )

    async def _update_status(self, session, task, new_status: TaskStatus):
        old = task.status
        task.status = new_status
        await session.commit()
        await self.events.broadcast_state_change(task.id, old.value, new_status.value)
        await self.events.log(task.id, f"Status: {old.value} -> {new_status.value}")

    async def process_task(self, task_id: int):
        async with self.session_factory() as session:
            task = await session.get(Task, task_id)
            repo = await session.get(Repo, task.repo_id)
            workspace = await session.get(Workspace, task.workspace_id) if task.workspace_id else None

            try:
                task_input = self.codex.format_task_input(task.title, task.description)
                log_cb = lambda line: self.events.log(task.id, line)  # noqa: E731

                if task.status == TaskStatus.PENDING:
                    await self._update_status(session, task, TaskStatus.PREPARING_WORKSPACE)
                    if workspace is None:
                        raise RuntimeError("Workspace not found for task")

                    workspace_path = Path(workspace.workspace_path) if workspace.workspace_path else None
                    if workspace_path is None or not workspace_path.exists():
                        workspace_path = await self.git.create_worktree(
                            Path(repo.path),
                            workspace.branch_name,
                            workspace.id,
                            repo.id,
                            repo.name,
                            workspace.name,
                            workspace.base_branch,
                        )
                        workspace.workspace_path = str(workspace_path)
                    task.workspace_path = str(workspace_path)
                    task.branch_name = workspace.branch_name
                    await session.commit()

                    await self._update_status(session, task, TaskStatus.PLANNING)
                    task.plan_text = await self._run_planning_stage(
                        session,
                        task,
                        repo,
                        workspace,
                        task_input,
                        log_cb,
                    )
                    await session.commit()
                    await self._update_status(session, task, TaskStatus.IMPLEMENTING)

                if task.status == TaskStatus.IMPLEMENTING:
                    await self._run_implementation_pipeline(
                        session,
                        task,
                        repo,
                        workspace,
                        task_input,
                        log_cb,
                    )
                    return

                if task.status == TaskStatus.MERGING:
                    workspace_path = Path(task.workspace_path) if task.workspace_path else None
                    if workspace_path and await self.git.commit_workspace_changes(
                        workspace_path,
                        self._build_task_commit_message(task),
                    ):
                        task.diff_text = await self.git.get_diff(
                            workspace_path,
                            workspace.base_branch if workspace else repo.default_branch,
                        )
                        await session.commit()
                    await self.events.log(task.id, "Merging to main...")
                    success, msg = await self.git.merge_to_main(
                        Path(repo.path),
                        workspace.branch_name if workspace else task.branch_name,
                        workspace.base_branch if workspace else repo.default_branch,
                    )
                    self._record_run(session, task.id, "merge", 0 if success else 1)
                    if not success:
                        raise RuntimeError(f"Merge failed: {msg}")
                    await self._update_status(session, task, TaskStatus.DONE)

            except NeedsAttentionError as exc:
                await self.events.log(task.id, f"NEEDS ATTENTION: {exc}")
                task.error_message = str(exc)
                await session.commit()
                await self._update_status(session, task, TaskStatus.NEEDS_ATTENTION)
            except Exception as exc:
                await self.events.log(task.id, f"ERROR: {exc}")
                task.error_message = str(exc)
                if task.retry_count < 1:
                    task.retry_count += 1
                    task.status = TaskStatus.PENDING
                    await session.commit()
                    if self.worker_pool:
                        await self.worker_pool.enqueue(task.id)
                else:
                    await self._update_status(session, task, TaskStatus.FAILED)

    async def _run_planning_stage(self, session, task, repo, workspace, task_input: str, log_cb):
        workspace_path = Path(task.workspace_path)
        await self.events.log(task.id, "Stage: plan")
        exit_code, output = await self.codex.generate_plan(
            workspace_path,
            task_input,
            agent_name="planner",
            log_callback=log_cb,
            task_id=task.id,
            repo_name=repo.name,
            workspace_name=workspace.name if workspace else "",
            branch_name=workspace.branch_name if workspace else task.branch_name or "",
            base_branch=workspace.base_branch if workspace else repo.default_branch,
        )
        self._record_run(session, task.id, "plan", exit_code)
        if exit_code != 0:
            raise RuntimeError(f"Plan generation failed: {output[-500:]}")

        plan_text = output.strip()
        if not plan_text:
            raise RuntimeError("Plan generation returned an empty plan")

        critique_rounds = max(1, self.codex.policy.critique_max_rounds)
        if not self.codex.policy.critique_required:
            return plan_text

        last_critique = ""
        for round_index in range(1, critique_rounds + 1):
            await self.events.log(
                task.id,
                f"Stage: critique ({round_index}/{critique_rounds})",
            )
            exit_code, critique_output = await self.codex.critique_plan(
                workspace_path,
                plan_text,
                task_input,
                agent_name="critic",
                log_callback=log_cb,
                task_id=task.id,
                repo_name=repo.name,
                workspace_name=workspace.name if workspace else "",
                branch_name=workspace.branch_name if workspace else task.branch_name or "",
                base_branch=workspace.base_branch if workspace else repo.default_branch,
            )
            self._record_run(session, task.id, "critique", exit_code)
            if exit_code != 0:
                raise RuntimeError(f"Plan critique failed: {critique_output[-500:]}")

            critique = self._parse_plan_critique(critique_output)
            last_critique = critique_output
            plan_text = critique["plan"]
            await self.events.log(task.id, f"Critic verdict: {critique['verdict']}. {critique['summary']}")
            if critique["verdict"] == "APPROVED":
                return plan_text

        raise NeedsAttentionError(
            "Plan critique did not converge within the configured rounds.\n\n"
            f"{last_critique.strip()}"
        )

    async def _run_implementation_pipeline(self, session, task, repo, workspace, task_input: str, log_cb):
        workspace_path = Path(task.workspace_path)
        await self.events.log(task.id, "Stage: implement")
        exit_code, output = await self.codex.implement_plan(
            workspace_path,
            task.plan_text or "",
            task_input,
            agent_name="executor",
            log_callback=log_cb,
            task_id=task.id,
            repo_name=repo.name,
            workspace_name=workspace.name if workspace else "",
            branch_name=workspace.branch_name if workspace else task.branch_name or "",
            base_branch=workspace.base_branch if workspace else repo.default_branch,
        )
        self._record_run(session, task.id, "implement", exit_code)
        if exit_code != 0:
            raise RuntimeError(f"Implementation failed: {output[-500:]}")

        if not await self.git.has_working_tree_changes(workspace_path):
            await self.events.log(
                task.id,
                "Warning: Implementation completed without creating any file changes in the workspace.\n"
                "The executor returned success, but the worktree is unchanged. "
                "The tester will evaluate if the workspace state fulfills the requirements."
            )

        await self._update_status(session, task, TaskStatus.TESTING)
        await self.events.log(
            task.id,
            f"Stage: test (max repair loops {self.codex.policy.test_fix_loops})",
        )
        exit_code, test_output = await self.codex.run_tests(
            workspace_path,
            agent_name="tester",
            task_description=task_input,
            plan_text=task.plan_text or "",
            log_callback=log_cb,
            task_id=task.id,
            repo_name=repo.name,
            workspace_name=workspace.name if workspace else "",
            branch_name=workspace.branch_name if workspace else task.branch_name or "",
            base_branch=workspace.base_branch if workspace else repo.default_branch,
        )
        self._record_run(session, task.id, "test", exit_code)
        if exit_code != 0:
            raise RuntimeError(f"Testing failed: {test_output[-500:]}")

        test_result = self._parse_stage_verdict(test_output, allowed={"PASS", "NEEDS_ATTENTION"})
        await self.events.log(task.id, f"Tester verdict: {test_result['verdict']}. {test_result['summary']}")
        if test_result["verdict"] != "PASS":
            raise NeedsAttentionError(
                "Testing could not reach a passing state within the configured repair loop.\n\n"
                f"{test_output.strip()}"
            )

        if not await self.git.commit_workspace_changes(
            workspace_path,
            self._build_task_commit_message(task),
        ):
            await self.events.log(
                task.id,
                "Notice: Implementation completed, but no mergeable workspace changes remained after testing. "
                "This may indicate the task required no code changes or changes were filtered."
            )

        task.diff_text = await self.git.get_diff(
            workspace_path,
            workspace.base_branch if workspace else repo.default_branch,
        )
        await session.commit()

        if self.codex.policy.review_required:
            await self.events.log(task.id, "Stage: review")
            exit_code, review_output = await self.codex.review_result(
                workspace_path,
                task.plan_text or "",
                task_input,
                test_output,
                task.diff_text or "",
                agent_name="reviewer",
                log_callback=log_cb,
                task_id=task.id,
                repo_name=repo.name,
                workspace_name=workspace.name if workspace else "",
                branch_name=workspace.branch_name if workspace else task.branch_name or "",
                base_branch=workspace.base_branch if workspace else repo.default_branch,
            )
            self._record_run(session, task.id, "review", exit_code)
            if exit_code != 0:
                raise RuntimeError(f"Review failed: {review_output[-500:]}")

            review_result = self._parse_stage_verdict(
                review_output,
                allowed={"PASS", "NEEDS_ATTENTION"},
            )
            await self.events.log(
                task.id,
                f"Reviewer verdict: {review_result['verdict']}. {review_result['summary']}",
            )
            if review_result["verdict"] != "PASS":
                raise NeedsAttentionError(
                    "Reviewer blocked merge readiness.\n\n"
                    f"{review_output.strip()}"
                )

        await session.commit()
        await self._update_status(session, task, TaskStatus.AWAIT_MERGE_APPROVAL)

    def _parse_plan_critique(self, output: str) -> dict[str, str]:
        parsed = self._parse_stage_verdict(output, allowed={"APPROVED", "REVISE"})
        plan_match = re.search(r"^PLAN:\s*(.*)$", output, re.MULTILINE | re.DOTALL)
        if not plan_match:
            raise RuntimeError("Plan critique output is missing a PLAN section")
        plan_text = plan_match.group(1).strip()
        if not plan_text:
            raise RuntimeError("Plan critique output returned an empty PLAN section")
        parsed["plan"] = plan_text
        return parsed

    def _parse_stage_verdict(self, output: str, *, allowed: set[str]) -> dict[str, str]:
        verdict_match = re.search(r"^VERDICT:\s*(.+)$", output, re.MULTILINE)
        summary_match = re.search(r"^SUMMARY:\s*(.+)$", output, re.MULTILINE)
        if not verdict_match:
            raise RuntimeError("Stage output is missing VERDICT")
        verdict = verdict_match.group(1).strip().upper()
        if verdict not in allowed:
            raise RuntimeError(f"Unexpected verdict '{verdict}'")
        summary = summary_match.group(1).strip() if summary_match else ""
        return {"verdict": verdict, "summary": summary}
