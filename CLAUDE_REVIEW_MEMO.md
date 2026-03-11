# Claude Review Memo: Orchestrator Architecture + Role-Specific Models (Uncommitted)

Date: 2026-03-11
Repo: `D:\Python\agent`
Status: Changes are currently uncommitted in the working tree.

## Purpose
- Reduce human intervention by adding a user-delegated **Orchestrator** that routes work across specialized agents.
- Prevent “digging deeper” failure loops by introducing a bounded **repair/replan/escalate** strategy and a final **verify** gate.
- Lock role responsibilities and **model selection** per agent to make behavior predictable and debuggable.

## High-Level Architecture
- **User**: absolute authority (goal, constraints, final approval).
- **Orchestrator**: user-delegated manager; does not implement code; decides next action based on outputs.
- **Specialists**: narrow scoped agents (explorer/planner/critic/executor/tester/reviewer/recovery_planner/verifier).

Key design rule:
- `explorer` finds and summarizes; it should not make final design decisions.
- `executor` writes code; it should not change goals/scope.
- `recovery_planner` is invoked only for repeated/stuck failures; it produces an updated plan.
- `verifier` is the only “finish gate” (completion evidence), separate from review.

## Model / Role Mapping (Source of Truth)
Source: `runtime/codex/contract/codex-contract.toml`
- `intake`: `gpt-5.4`
- `orchestrator`: `gpt-5.4`
- `explorer`: `gpt-5.3-codex-spark`
- `planner`: `gpt-5.4`
- `critic`: `gpt-5.4`
- `executor`: `gpt-5-codex`
- `tester`: `gpt-5-codex`
- `reviewer`: `gpt-5.4`
- `recovery_planner`: `gpt-5.4`
- `verifier`: `gpt-5.4`

Note: contract rendering was updated so **agent TOMLs use agent-specific `model`** (not only the project model).

## Workflow Changes (Transitions)
Primary engine remains `SymphonyWorkflowEngine`, but now includes an orchestrator decision layer.

Default pipeline:
1. `explore` (new): repo discovery + risk notes
2. `plan`: plan uses `exploration_text`
3. `critique`: bounded plan critique loop
4. `implement`
5. `test`
6. `review`
7. `verify` (new): final completion gate

On failure (`NEEDS_ATTENTION`):
- Orchestrator produces a decision with:
  - `ACTION: REPAIR | REPLAN | ESCALATE | FINISH`
  - `SUMMARY: ...`
  - `RATIONALE: ...`
- `REPAIR`: re-run `implement` with a `repair_request` derived from failure context.
- `REPLAN`: call `recovery_planner` to generate an updated plan, re-critique, then retry pipeline.
- `ESCALATE`: stop automation and mark as requiring human attention.
- `FINISH`: only accepted when produced via `verify` gate.

Bounded loops (current constants in engine):
- Max orchestrator repair attempts: 1
- Max recovery replans: 1

## New Prompts / Templates
New required templates:
- `explore`, `orchestrate`, `recover`, `verify`
Existing:
- `plan`, `critique`, `implement`, `test`, `review`

Prompt changes:
- `plan` includes `Exploration summary: $exploration_text`
- `implement` includes `Repair request: $repair_request`

## Files Changed (What to Review)
Core behavior:
- `backend/app/core/workflow.py` (major changes; orchestration + new stages)
- `backend/app/core/task_orchestrator.py` (new; parses/encapsulates orchestrator decisions)
- `backend/app/adapters/codex_runner.py` (new runner methods for explore/orchestrate/recover/verify)
- `backend/app/core/contracts.py` (runner protocol expanded)

Contract + prompts:
- `runtime/codex/contract/codex-contract.toml` (agents/models/prompts)
- Generated/managed files under:
  - `runtime/codex/contract/agents/*.toml`
  - `runtime/codex/contract/instructions/*.md`
  - `runtime/codex/prompts/*.md`

Contract toolchain:
- `backend/app/core/codex_contract.py` (render/apply/verify changes; per-agent model support)
- `backend/app/core/prompt_library.py` (required templates list updated)

Bootstrap/runtime:
- `backend/app/bootstrap/runtime.py` (load order adjusted: project config before prompts)

Tests:
- `backend/tests/test_workflow_engine.py` (new success path + orchestrator repair loop test)
- `backend/tests/test_codex_contract.py` (agents/prompts expanded; per-agent model required)
- `backend/tests/test_runtime.py` (test fixtures updated for new required prompts/agents)

## Verification Results (Executed Locally)
- Contract: `python tools/codex_contract.py apply`
- Drift check: `python tools/codex_contract.py verify` (in sync)
- Backend tests: `cd backend && ./.venv/Scripts/python.exe -m pytest` (83 passed)

## Review Focus Areas (Questions for Claude)
- Correctness: Any path where the workflow can “finish” without sufficient evidence?
- Safety: Any chance `explorer`/`orchestrator` can cause side effects or write to repo via tools?
- Loop control: Are repair/replan bounds sufficient and correctly enforced?
- Output parsing: Is `ACTION/SUMMARY/RATIONALE` parsing robust to malformed output?
- Backwards compatibility: Are there runtime callers expecting old prompt set or older agent list?
- Test coverage: Any missing tests for `REPLAN` and `ESCALATE` branches?
