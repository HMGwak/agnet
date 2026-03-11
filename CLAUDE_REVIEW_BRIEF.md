# Claude Review Brief

This document summarizes the current uncommitted architecture changes for external review.

## Goal

The runtime previously behaved like a fixed stage runner. The new direction is:

- `User` holds absolute authority over task intent.
- `Orchestrator` acts as the delegated manager for that intent.
- specialist agents execute bounded roles beneath the orchestrator.

The target outcome is lower human intervention with stronger automatic routing, recovery, and completion judgment.

## High-Level Architecture

Current intended hierarchy:

1. `User`
2. `Orchestrator`
3. `Explorer`, `Planner`, `Critic`, `Executor`, `Tester`, `Reviewer`, `Recovery Planner`, `Verifier`

Role boundaries:

- `Orchestrator` does not code. It decides what happens next.
- `Explorer` is read-only and fast. It finds code paths and impact areas.
- `Planner` defines approach and success criteria.
- `Critic` challenges the plan before execution.
- `Executor` implements changes.
- `Tester` validates behavior and supports bounded repair loops.
- `Reviewer` checks correctness, regression, and risk.
- `Recovery Planner` is only used when the normal path stalls or heads in the wrong direction.
- `Verifier` is the final completion gate.

## Workflow Shape

The workflow is no longer just:

- `plan -> critique -> implement -> test -> review`

It is now:

1. `explore`
2. `plan`
3. `critique`
4. `implement`
5. `test`
6. `review`
7. `verify`

The orchestrator can choose one of five outcomes after a blocked step:

- `CONTINUE`
- `REPAIR`
- `REPLAN`
- `ESCALATE`
- `FINISH`

Practical meaning:

- `REPAIR` reruns implementation with a focused repair request.
- `REPLAN` invokes the recovery planner and re-enters critique before execution.
- `ESCALATE` stops automation and surfaces the task for human attention.
- `FINISH` is only valid when completion is actually verified.

## Model Routing

The contract now fixes models per role instead of relying only on a single project default.

Strategic roles:

- `orchestrator`: `gpt-5.4`
- `planner`: `gpt-5.4`
- `critic`: `gpt-5.4`
- `reviewer`: `gpt-5.4`
- `verifier`: `gpt-5.4`
- `recovery_planner`: `gpt-5.4`

Execution roles:

- `executor`: `gpt-5-codex`
- `tester`: `gpt-5-codex`

Discovery role:

- `explorer`: `gpt-5.3-codex-spark`

Intake:

- `intake`: `gpt-5.4`

Intended reasoning split:

- high-trust routing and judgment stay on `gpt-5.4`
- code production and local validation stay on `gpt-5-codex`
- cheap read-only exploration goes to `gpt-5.3-codex-spark`

## Main Files Changed

Core orchestration:

- [backend/app/core/workflow.py](/D:/Python/agent/backend/app/core/workflow.py)
- [backend/app/core/task_orchestrator.py](/D:/Python/agent/backend/app/core/task_orchestrator.py)

Runner and contracts:

- [backend/app/adapters/codex_runner.py](/D:/Python/agent/backend/app/adapters/codex_runner.py)
- [backend/app/core/contracts.py](/D:/Python/agent/backend/app/core/contracts.py)

Contract generation and prompts:

- [backend/app/core/codex_contract.py](/D:/Python/agent/backend/app/core/codex_contract.py)
- [backend/app/core/prompt_library.py](/D:/Python/agent/backend/app/core/prompt_library.py)
- [runtime/codex/contract/codex-contract.toml](/D:/Python/agent/runtime/codex/contract/codex-contract.toml)

Runtime boot:

- [backend/app/bootstrap/runtime.py](/D:/Python/agent/backend/app/bootstrap/runtime.py)

Tests:

- [backend/tests/test_workflow_engine.py](/D:/Python/agent/backend/tests/test_workflow_engine.py)
- [backend/tests/test_codex_contract.py](/D:/Python/agent/backend/tests/test_codex_contract.py)
- [backend/tests/test_runtime.py](/D:/Python/agent/backend/tests/test_runtime.py)

Managed generated files were also updated under:

- [runtime/codex/contract](/D:/Python/agent/runtime/codex/contract)
- [runtime/codex/prompts](/D:/Python/agent/runtime/codex/prompts)

## Design Notes For Review

Areas worth close review:

- whether the new orchestrator decisions are strict enough to prevent circular retries
- whether `REPAIR` vs `REPLAN` boundaries are well chosen
- whether `Verifier` should remain separate from `Reviewer` or be merged
- whether the recovery path should persist richer failure history before replan
- whether `explorer` on `gpt-5.3-codex-spark` is safe enough for all discovery tasks
- whether top-level workflow complexity has grown too much inside a single engine class

## Current Verification

Validation completed after these changes:

- `python tools/codex_contract.py apply`
- `python tools/codex_contract.py verify`
- `cd backend && ./.venv/Scripts/python.exe -m pytest`

Result:

- contract verification passed
- backend test suite passed: `83 passed`

## Suggested Review Questions For Claude

1. Is the `TaskOrchestrator` abstraction appropriately separated from `SymphonyWorkflowEngine`, or is more decomposition needed?
2. Are the new completion gates coherent, especially the split between `review` and `verify`?
3. Does the recovery path actually break bad loops, or can it still recycle the same failure under a different label?
4. Is the per-role model mapping sensible for cost, latency, and reliability?
5. Are there hidden regressions in prompt contract expansion or runtime boot order?
