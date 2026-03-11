from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class OrchestratorDecision:
    action: str
    summary: str
    rationale: str
    raw_output: str


class TaskOrchestrator:
    def __init__(self, agent_runner, event_sink):
        self.codex = agent_runner
        self.events = event_sink

    async def explore(
        self,
        *,
        workspace_path: Path,
        task_id: int,
        task_input: str,
        repo_name: str,
        workspace_name: str,
        branch_name: str,
        base_branch: str,
        log_callback,
    ) -> str:
        exit_code, output = await self.codex.explore_repo(
            workspace_path,
            task_input,
            task_id=task_id,
            repo_name=repo_name,
            workspace_name=workspace_name,
            branch_name=branch_name,
            base_branch=base_branch,
            log_callback=log_callback,
        )
        if exit_code != 0:
            raise RuntimeError(f"탐색 실패: {output[-500:]}")
        summary = output.strip()
        if summary:
            await self.events.log(task_id, f"탐색 요약:\n{summary}")
        return summary

    async def decide_failure(
        self,
        *,
        workspace_path: Path,
        task_id: int,
        phase_name: str,
        task_input: str,
        plan_text: str,
        exploration_text: str,
        failure_output: str,
        review_output: str,
        test_output: str,
        diff_text: str,
        log_callback,
        repo_name: str,
        workspace_name: str,
        branch_name: str,
        base_branch: str,
    ) -> OrchestratorDecision:
        exit_code, output = await self.codex.orchestrate_next_action(
            workspace_path,
            task_id=task_id,
            current_phase=phase_name,
            task_input=task_input,
            plan_text=plan_text,
            exploration_text=exploration_text,
            failure_output=failure_output,
            review_output=review_output,
            test_output=test_output,
            diff_text=diff_text,
            repo_name=repo_name,
            workspace_name=workspace_name,
            branch_name=branch_name,
            base_branch=base_branch,
            log_callback=log_callback,
        )
        if exit_code != 0:
            raise RuntimeError(f"오케스트레이터 판단 실패: {output[-500:]}")
        return self._parse_decision(output)

    async def recover_plan(
        self,
        *,
        workspace_path: Path,
        task_id: int,
        task_input: str,
        plan_text: str,
        exploration_text: str,
        failure_output: str,
        review_output: str,
        test_output: str,
        diff_text: str,
        log_callback,
        repo_name: str,
        workspace_name: str,
        branch_name: str,
        base_branch: str,
    ) -> str:
        exit_code, output = await self.codex.generate_recovery_plan(
            workspace_path,
            task_input,
            task_id=task_id,
            plan_text=plan_text,
            exploration_text=exploration_text,
            failure_output=failure_output,
            review_output=review_output,
            test_output=test_output,
            diff_text=diff_text,
            repo_name=repo_name,
            workspace_name=workspace_name,
            branch_name=branch_name,
            base_branch=base_branch,
            log_callback=log_callback,
        )
        if exit_code != 0:
            raise RuntimeError(f"복구 계획 생성 실패: {output[-500:]}")
        plan = output.strip()
        if not plan:
            raise RuntimeError("복구 계획 생성 결과가 비어 있습니다")
        await self.events.log(task_id, f"복구 계획 생성 완료:\n{plan}")
        return plan

    def _parse_decision(self, output: str) -> OrchestratorDecision:
        action_match = re.search(r"^ACTION:\s*(.+)$", output, re.MULTILINE)
        summary_match = re.search(r"^SUMMARY:\s*(.+)$", output, re.MULTILINE)
        rationale_match = re.search(r"^RATIONALE:\s*(.*)$", output, re.MULTILINE | re.DOTALL)
        if not action_match:
            raise RuntimeError("오케스트레이터 출력에 ACTION이 없습니다")
        action = action_match.group(1).strip().upper()
        if action not in {"CONTINUE", "REPAIR", "REPLAN", "ESCALATE", "FINISH"}:
            raise RuntimeError(f"예상하지 못한 orchestrator action '{action}'입니다")
        summary = summary_match.group(1).strip() if summary_match else ""
        rationale = rationale_match.group(1).strip() if rationale_match else ""
        return OrchestratorDecision(
            action=action,
            summary=summary,
            rationale=rationale,
            raw_output=output.strip(),
        )
