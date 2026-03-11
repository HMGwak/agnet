from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re

from app.core.contracts import AgentRunner, EventSink, WorkspaceManager
from app.core.task_orchestrator import OrchestratorDecision, TaskOrchestrator
from app.models import Repo, Run, Task, TaskStatus, Workspace


class NeedsAttentionError(RuntimeError):
    pass


class SymphonyWorkflowEngine:
    MAX_ORCHESTRATOR_REPAIR_ATTEMPTS = 1
    MAX_RECOVERY_REPLANS = 1

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
        self.orchestrator = TaskOrchestrator(agent_runner, event_sink)

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
        await self.events.log(task.id, f"상태: {old.value} -> {new_status.value}")

    def _agent_context(self, task, repo, workspace, log_cb) -> dict[str, object]:
        return {
            "task_id": task.id,
            "repo_name": repo.name,
            "workspace_name": workspace.name if workspace else "",
            "branch_name": workspace.branch_name if workspace else task.branch_name or "",
            "base_branch": workspace.base_branch if workspace else repo.default_branch,
            "log_callback": log_cb,
        }

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
                        raise RuntimeError("작업에 연결된 워크스페이스를 찾을 수 없습니다")

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
                        allow_recovery=True,
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
                    await self.events.log(task.id, "메인 브랜치로 병합 중...")
                    success, msg = await self.git.merge_to_main(
                        Path(repo.path),
                        workspace.branch_name if workspace else task.branch_name,
                        workspace.base_branch if workspace else repo.default_branch,
                    )
                    self._record_run(session, task.id, "merge", 0 if success else 1)
                    if not success:
                        raise RuntimeError(f"병합 실패: {msg}")
                    await self._update_status(session, task, TaskStatus.DONE)

            except NeedsAttentionError as exc:
                await self.events.log(task.id, f"조치 필요: {exc}")
                task.error_message = str(exc)
                await session.commit()
                await self._update_status(session, task, TaskStatus.NEEDS_ATTENTION)
            except Exception as exc:
                await self.events.log(task.id, f"오류: {exc}")
                task.error_message = str(exc)
                if task.retry_count < 1:
                    task.retry_count += 1
                    task.status = TaskStatus.PENDING
                    await session.commit()
                    if self.worker_pool:
                        await self.worker_pool.enqueue(task.id)
                else:
                    await self._update_status(session, task, TaskStatus.FAILED)

    async def _run_planning_stage(
        self,
        session,
        task,
        repo,
        workspace,
        task_input: str,
        log_cb,
        *,
        allow_recovery: bool,
    ) -> str:
        workspace_path = Path(task.workspace_path)
        agent_context = self._agent_context(task, repo, workspace, log_cb)

        await self.events.log(task.id, "단계: 탐색")
        exploration_text = await self.orchestrator.explore(
            workspace_path=workspace_path,
            task_id=task.id,
            task_input=task_input,
            repo_name=repo.name,
            workspace_name=workspace.name if workspace else "",
            branch_name=workspace.branch_name if workspace else task.branch_name or "",
            base_branch=workspace.base_branch if workspace else repo.default_branch,
            log_callback=log_cb,
        )
        self._record_run(session, task.id, "explore", 0)

        await self.events.log(task.id, "단계: 계획")
        exit_code, output = await self.codex.generate_plan(
            workspace_path,
            task_input,
            exploration_text=exploration_text,
            **agent_context,
        )
        self._record_run(session, task.id, "plan", exit_code)
        if exit_code != 0:
            raise RuntimeError(f"계획 생성 실패: {output[-500:]}")

        plan_text = output.strip()
        if not plan_text:
            raise RuntimeError("계획 생성 결과가 비어 있습니다")

        approved, reviewed_plan, last_critique = await self._run_plan_critique_loop(
            session,
            task,
            repo,
            workspace,
            task_input,
            plan_text,
            log_cb,
        )
        if approved:
            return reviewed_plan

        decision = await self._decide_failure(
            task=task,
            repo=repo,
            workspace=workspace,
            task_input=task_input,
            plan_text=reviewed_plan,
            exploration_text=exploration_text,
            failure_output=last_critique,
            review_output="",
            test_output="",
            diff_text="",
            phase_name="plan",
            log_cb=log_cb,
        )
        if allow_recovery and decision.action in {"CONTINUE", "REPAIR", "REPLAN"}:
            recovered_plan = await self.orchestrator.recover_plan(
                workspace_path=workspace_path,
                task_id=task.id,
                task_input=task_input,
                plan_text=reviewed_plan,
                exploration_text=exploration_text,
                failure_output=last_critique,
                review_output="",
                test_output="",
                diff_text="",
                log_callback=log_cb,
                repo_name=repo.name,
                workspace_name=workspace.name if workspace else "",
                branch_name=workspace.branch_name if workspace else task.branch_name or "",
                base_branch=workspace.base_branch if workspace else repo.default_branch,
            )
            self._record_run(session, task.id, "recover", 0)
            approved, final_plan, recovery_critique = await self._run_plan_critique_loop(
                session,
                task,
                repo,
                workspace,
                task_input,
                recovered_plan,
                log_cb,
            )
            if approved:
                return final_plan
            raise NeedsAttentionError(
                "복구 계획까지 수행했지만 계획 검토가 수렴하지 않았습니다.\n\n"
                f"{recovery_critique.strip()}"
            )

        raise NeedsAttentionError(
            "설정된 반복 횟수 안에 계획 검토가 수렴하지 않았습니다.\n\n"
            f"{decision.raw_output}\n\n{last_critique.strip()}"
        )

    async def _run_plan_critique_loop(
        self,
        session,
        task,
        repo,
        workspace,
        task_input: str,
        plan_text: str,
        log_cb,
    ) -> tuple[bool, str, str]:
        workspace_path = Path(task.workspace_path)
        critique_rounds = max(1, self.codex.policy.critique_max_rounds)
        if not self.codex.policy.critique_required:
            return True, plan_text, ""

        last_critique = ""
        for round_index in range(1, critique_rounds + 1):
            await self.events.log(
                task.id,
                f"단계: 계획 검토 ({round_index}/{critique_rounds})",
            )
            exit_code, critique_output = await self.codex.critique_plan(
                workspace_path,
                plan_text,
                task_input,
                **self._agent_context(task, repo, workspace, log_cb),
            )
            self._record_run(session, task.id, "critique", exit_code)
            if exit_code != 0:
                raise RuntimeError(f"계획 검토 실패: {critique_output[-500:]}")

            critique = self._parse_plan_critique(critique_output)
            last_critique = critique_output
            plan_text = critique["plan"]
            await self.events.log(
                task.id,
                f"계획 검토 결과: {critique['verdict']}. {critique['summary']}",
            )
            if critique["verdict"] == "APPROVED":
                return True, plan_text, critique_output

        return False, plan_text, last_critique

    async def _run_implementation_pipeline(self, session, task, repo, workspace, task_input: str, log_cb):
        workspace_path = Path(task.workspace_path)
        agent_context = self._agent_context(task, repo, workspace, log_cb)
        repair_attempts_remaining = self.MAX_ORCHESTRATOR_REPAIR_ATTEMPTS
        recovery_replans_remaining = self.MAX_RECOVERY_REPLANS
        repair_request = ""
        exploration_text = ""

        while True:
            await self.events.log(
                task.id,
                "단계: 구현" if not repair_request else "단계: 구현 (오케스트레이터 수정 루프)",
            )
            exit_code, output = await self.codex.implement_plan(
                workspace_path,
                task.plan_text or "",
                task_input,
                repair_request=repair_request,
                **agent_context,
            )
            self._record_run(session, task.id, "implement", exit_code)
            if exit_code != 0:
                raise RuntimeError(f"구현 실패: {output[-500:]}")

            if not await self.git.has_working_tree_changes(workspace_path):
                await self.events.log(
                    task.id,
                    "경고: 워크스페이스에 파일 변경을 만들지 않은 상태로 구현이 완료되었습니다.\n"
                    "실행기는 성공을 반환했지만 작업 트리는 바뀌지 않았습니다. "
                    "테스터가 현재 워크스페이스 상태가 요구사항을 충족하는지 확인합니다."
                )

            if task.status != TaskStatus.TESTING:
                await self._update_status(session, task, TaskStatus.TESTING)
            await self.events.log(
                task.id,
                f"단계: 테스트 (최대 수정 반복 {self.codex.policy.test_fix_loops}회)",
            )
            exit_code, test_output = await self.codex.run_tests(
                workspace_path,
                task_description=task_input,
                plan_text=task.plan_text or "",
                repair_request=repair_request,
                **agent_context,
            )
            self._record_run(session, task.id, "test", exit_code)
            if exit_code != 0:
                raise RuntimeError(f"테스트 실패: {test_output[-500:]}")

            test_result = self._parse_stage_verdict(test_output, allowed={"PASS", "NEEDS_ATTENTION"})
            await self.events.log(
                task.id,
                f"테스트 결과: {test_result['verdict']}. {test_result['summary']}",
            )
            if test_result["verdict"] != "PASS":
                next_step = await self._resolve_failure_strategy(
                    session,
                    task,
                    repo,
                    workspace,
                    task_input,
                    log_cb,
                    phase_name="test",
                    failure_output=test_output,
                    review_output="",
                    test_output=test_output,
                    diff_text=task.diff_text or "",
                    exploration_text=exploration_text,
                    repair_attempts_remaining=repair_attempts_remaining,
                    recovery_replans_remaining=recovery_replans_remaining,
                )
                if next_step["kind"] == "repair":
                    repair_attempts_remaining -= 1
                    repair_request = next_step["repair_request"]
                    await self._update_status(session, task, TaskStatus.IMPLEMENTING)
                    continue
                if next_step["kind"] == "replan":
                    recovery_replans_remaining -= 1
                    task.plan_text = next_step["plan_text"]
                    await session.commit()
                    repair_request = ""
                    await self._update_status(session, task, TaskStatus.IMPLEMENTING)
                    continue
                raise NeedsAttentionError(next_step["message"])

            if not await self.git.commit_workspace_changes(
                workspace_path,
                self._build_task_commit_message(task),
            ):
                await self.events.log(
                    task.id,
                    "안내: 구현은 완료되었지만 테스트 후 병합 가능한 워크스페이스 변경이 남지 않았습니다. "
                    "이 작업에 코드 변경이 필요 없었거나 변경이 필터링되었을 수 있습니다."
                )

            task.diff_text = await self.git.get_diff(
                workspace_path,
                workspace.base_branch if workspace else repo.default_branch,
            )
            await session.commit()

            review_output = ""
            if self.codex.policy.review_required:
                await self.events.log(task.id, "단계: 리뷰")
                exit_code, review_output = await self.codex.review_result(
                    workspace_path,
                    task.plan_text or "",
                    task_input,
                    test_output,
                    task.diff_text or "",
                    repair_request=repair_request,
                    **agent_context,
                )
                self._record_run(session, task.id, "review", exit_code)
                if exit_code != 0:
                    raise RuntimeError(f"리뷰 실패: {review_output[-500:]}")

                review_result = self._parse_stage_verdict(
                    review_output,
                    allowed={"PASS", "NEEDS_ATTENTION"},
                )
                await self.events.log(
                    task.id,
                    f"리뷰 결과: {review_result['verdict']}. {review_result['summary']}",
                )
                if review_result["verdict"] != "PASS":
                    next_step = await self._resolve_failure_strategy(
                        session,
                        task,
                        repo,
                        workspace,
                        task_input,
                        log_cb,
                        phase_name="review",
                        failure_output=review_output,
                        review_output=review_output,
                        test_output=test_output,
                        diff_text=task.diff_text or "",
                        exploration_text=exploration_text,
                        repair_attempts_remaining=repair_attempts_remaining,
                        recovery_replans_remaining=recovery_replans_remaining,
                    )
                    if next_step["kind"] == "repair":
                        repair_attempts_remaining -= 1
                        repair_request = next_step["repair_request"]
                        await self._update_status(session, task, TaskStatus.IMPLEMENTING)
                        continue
                    if next_step["kind"] == "replan":
                        recovery_replans_remaining -= 1
                        task.plan_text = next_step["plan_text"]
                        await session.commit()
                        repair_request = ""
                        await self._update_status(session, task, TaskStatus.IMPLEMENTING)
                        continue
                    raise NeedsAttentionError(next_step["message"])

            await self.events.log(task.id, "단계: 최종 검증")
            exit_code, verify_output = await self.codex.verify_completion(
                workspace_path,
                task_input=task_input,
                plan_text=task.plan_text or "",
                test_output=test_output,
                review_output=review_output,
                diff_text=task.diff_text or "",
                repair_request=repair_request,
                **agent_context,
            )
            self._record_run(session, task.id, "verify", exit_code)
            if exit_code != 0:
                raise RuntimeError(f"최종 검증 실패: {verify_output[-500:]}")

            verify_result = self._parse_stage_verdict(
                verify_output,
                allowed={"PASS", "NEEDS_ATTENTION"},
            )
            await self.events.log(
                task.id,
                f"최종 검증 결과: {verify_result['verdict']}. {verify_result['summary']}",
            )
            if verify_result["verdict"] != "PASS":
                next_step = await self._resolve_failure_strategy(
                    session,
                    task,
                    repo,
                    workspace,
                    task_input,
                    log_cb,
                    phase_name="verify",
                    failure_output=verify_output,
                    review_output=review_output,
                    test_output=test_output,
                    diff_text=task.diff_text or "",
                    exploration_text=exploration_text,
                    repair_attempts_remaining=repair_attempts_remaining,
                    recovery_replans_remaining=recovery_replans_remaining,
                )
                if next_step["kind"] == "finish":
                    await session.commit()
                    await self._update_status(session, task, TaskStatus.AWAIT_MERGE_APPROVAL)
                    return
                if next_step["kind"] == "repair":
                    repair_attempts_remaining -= 1
                    repair_request = next_step["repair_request"]
                    await self._update_status(session, task, TaskStatus.IMPLEMENTING)
                    continue
                if next_step["kind"] == "replan":
                    recovery_replans_remaining -= 1
                    task.plan_text = next_step["plan_text"]
                    await session.commit()
                    repair_request = ""
                    await self._update_status(session, task, TaskStatus.IMPLEMENTING)
                    continue
                raise NeedsAttentionError(next_step["message"])

            await session.commit()
            await self._update_status(session, task, TaskStatus.AWAIT_MERGE_APPROVAL)
            return

    async def _resolve_failure_strategy(
        self,
        session,
        task,
        repo,
        workspace,
        task_input: str,
        log_cb,
        *,
        phase_name: str,
        failure_output: str,
        review_output: str,
        test_output: str,
        diff_text: str,
        exploration_text: str,
        repair_attempts_remaining: int,
        recovery_replans_remaining: int,
    ) -> dict[str, str]:
        decision = await self._decide_failure(
            task=task,
            repo=repo,
            workspace=workspace,
            task_input=task_input,
            plan_text=task.plan_text or "",
            exploration_text=exploration_text,
            failure_output=failure_output,
            review_output=review_output,
            test_output=test_output,
            diff_text=diff_text,
            phase_name=phase_name,
            log_cb=log_cb,
        )
        repair_actions = {"CONTINUE", "REPAIR"}
        if decision.action in repair_actions and repair_attempts_remaining > 0:
            return {
                "kind": "repair",
                "repair_request": self._build_repair_request(decision, failure_output),
            }
        if decision.action == "REPLAN" and recovery_replans_remaining > 0:
            plan_text = await self.orchestrator.recover_plan(
                workspace_path=Path(task.workspace_path),
                task_id=task.id,
                task_input=task_input,
                plan_text=task.plan_text or "",
                exploration_text=exploration_text,
                failure_output=failure_output,
                review_output=review_output,
                test_output=test_output,
                diff_text=diff_text,
                log_callback=log_cb,
                repo_name=repo.name,
                workspace_name=workspace.name if workspace else "",
                branch_name=workspace.branch_name if workspace else task.branch_name or "",
                base_branch=workspace.base_branch if workspace else repo.default_branch,
            )
            self._record_run(session, task.id, "recover", 0)
            approved, final_plan, critique_output = await self._run_plan_critique_loop(
                session,
                task,
                repo,
                workspace,
                task_input,
                plan_text,
                log_cb,
            )
            if approved:
                return {"kind": "replan", "plan_text": final_plan}
            return {
                "kind": "escalate",
                "message": (
                    "복구 계획까지 수행했지만 새 계획이 검토를 통과하지 못했습니다.\n\n"
                    f"{critique_output.strip()}"
                ),
            }
        if decision.action == "FINISH" and phase_name == "verify":
            return {"kind": "finish"}
        return {
            "kind": "escalate",
            "message": (
                f"오케스트레이터가 자동 진행을 중단했습니다.\n\n{decision.raw_output}\n\n"
                f"{failure_output.strip()}"
            ),
        }

    async def _decide_failure(
        self,
        *,
        task,
        repo,
        workspace,
        task_input: str,
        plan_text: str,
        exploration_text: str,
        failure_output: str,
        review_output: str,
        test_output: str,
        diff_text: str,
        phase_name: str,
        log_cb,
    ) -> OrchestratorDecision:
        decision = await self.orchestrator.decide_failure(
            workspace_path=Path(task.workspace_path),
            task_id=task.id,
            phase_name=phase_name,
            task_input=task_input,
            plan_text=plan_text,
            exploration_text=exploration_text,
            failure_output=failure_output,
            review_output=review_output,
            test_output=test_output,
            diff_text=diff_text,
            log_callback=log_cb,
            repo_name=repo.name,
            workspace_name=workspace.name if workspace else "",
            branch_name=workspace.branch_name if workspace else task.branch_name or "",
            base_branch=workspace.base_branch if workspace else repo.default_branch,
        )
        await self.events.log(
            task.id,
            f"오케스트레이터 판단 ({phase_name}): {decision.action}. {decision.summary}",
        )
        return decision

    def _build_repair_request(self, decision: OrchestratorDecision, failure_output: str) -> str:
        parts = [decision.summary.strip(), decision.rationale.strip(), failure_output.strip()]
        return "\n\n".join(part for part in parts if part)[:4000]

    def _parse_plan_critique(self, output: str) -> dict[str, str]:
        parsed = self._parse_stage_verdict(output, allowed={"APPROVED", "REVISE"})
        plan_match = re.search(r"^PLAN:\s*(.*)$", output, re.MULTILINE | re.DOTALL)
        if not plan_match:
            raise RuntimeError("계획 검토 출력에 PLAN 섹션이 없습니다")
        plan_text = plan_match.group(1).strip()
        if not plan_text:
            raise RuntimeError("계획 검토 출력의 PLAN 섹션이 비어 있습니다")
        parsed["plan"] = plan_text
        return parsed

    def _parse_stage_verdict(self, output: str, *, allowed: set[str]) -> dict[str, str]:
        verdict_match = re.search(r"^VERDICT:\s*(.+)$", output, re.MULTILINE)
        summary_match = re.search(r"^SUMMARY:\s*(.+)$", output, re.MULTILINE)
        if not verdict_match:
            raise RuntimeError("단계 출력에 VERDICT가 없습니다")
        verdict = verdict_match.group(1).strip().upper()
        if verdict not in allowed:
            raise RuntimeError(f"예상하지 못한 verdict 값 '{verdict}'입니다")
        summary = summary_match.group(1).strip() if summary_match else ""
        return {"verdict": verdict, "summary": summary}
