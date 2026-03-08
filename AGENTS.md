# Repository Guidelines

## Project Structure & Module Organization
This repository has two main apps:

- `backend/`: FastAPI service. Core code lives in `backend/app/`, with API routers in `backend/app/api/` and service logic in `backend/app/services/`.
- `backend/tests/`: pytest suite for backend behavior, currently centered on Git/worktree flows.
- `dashboard/`: Next.js App Router frontend. Routes live in `dashboard/src/app/`, reusable UI in `dashboard/src/components/`, and client helpers in `dashboard/src/lib/` and `dashboard/src/hooks/`.
- `docs/`: architecture and design references for local implementation decisions.
- `runtime/`: repository-managed tool assets, including the local Codex contract, policy, prompts, and sidecar runtime.
- `project/`: local personal data such as auth caches, database files, repos, workspaces, and logs.
- `tools/`: local helper scripts such as Codex login and contract recovery commands.

## Architecture Principles
Treat `openai/symphony` as a specification reference, not as a code dependency to wrap directly. Keep local code split into:

- `backend/app/core/`: workflow rules, lifecycle policy, and orchestration contracts.
- `backend/app/adapters/` and `backend/app/bootstrap/`: integration with SQLite, Git, Codex, websocket, and app startup.
- `dashboard/` plus startup scripts: wrapper shell over the current public API.

Do not couple UI, startup scripts, or transport routes directly to core internals when adding new features. Prefer preserving public API/UI behavior while moving business rules into core-facing services.

## Build, Test, and Development Commands
- `./start.sh` or `start.bat`: start backend on `:8001` and dashboard on `:3000`.
- `cd backend && uv sync --extra dev`: install backend dependencies, including test tools.
- `cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001`: run the API locally.
- `cd backend && uv run pytest`: run backend tests.
- `cd dashboard && npm install`: install frontend dependencies.
- `cd dashboard && npm run dev`: start the Next.js dev server.
- `cd dashboard && npm run build`: production build check.
- `cd dashboard && npm run lint`: run ESLint for the frontend.

## Coding Style & Naming Conventions
Use 4-space indentation in Python and follow existing FastAPI patterns with explicit imports and async-first service code. Keep backend modules snake_case and favor type hints where the code already uses them.

In the dashboard, use TypeScript, functional React components, and existing Next.js App Router conventions. Components use PascalCase filenames like `TaskCard.tsx`; hooks use `useX` names; shared helpers and types stay under `src/lib/`.

## Testing Guidelines
Backend tests use `pytest` and `pytest-asyncio`. Add new tests under `backend/tests/` with filenames like `test_<feature>.py` and prefer reproducing bugs with a failing test first. No frontend test runner is configured yet, so at minimum run `npm run lint` and `npm run build` for UI changes.

## Commit & Pull Request Guidelines
Match the current history: short, imperative commit subjects such as `Add Windows support...` or phase-based entries like `Phase 7: Frontend foundation with Next.js dashboard`. Keep commits focused and avoid mixing backend and dashboard refactors unless they are part of one change.

Pull requests should include a concise summary, the affected area (`backend`, `dashboard`, or both), validation commands run, and screenshots for visible dashboard changes. Link related issues or task IDs when available.

## Security & Configuration Tips
Do not commit real repository data, logs, local database files, or auth state. Keep local settings aligned with `http://localhost:3000` to match the backend CORS configuration during development.
The app runtime is expected to use the repository-local Codex runtime under `runtime/codex/sidecar/` with app-local Codex state under `project/app-codex-home/`; invoking `codex` directly from a shell is a separate concern and is not the app runtime.
The Codex contract source of truth is [`runtime/codex/contract/codex-contract.toml`](/D:/Python/agent/runtime/codex/contract/codex-contract.toml). Update that manifest, then run `python tools/codex_contract.py apply` to regenerate managed files and `python tools/codex_contract.py verify` to check drift.

## Orchestrator (Team Lead) Defaults
You are the orchestrator: act like a strong team lead with a high-performing sub-agent team.
When multi-agent is enabled, delegate work to specialized sub-agents and merge results into the best outcome.

Default routing:
- `planner`: clarify intent, assumptions, constraints, success criteria, and verification plan.
- `explorer`: read-only codebase discovery (paths, entry points, risks).
- `worker`: implement minimal, surgical changes.
- `reviewer`: correctness/security/test-risk review of the patch.
- `tester`: run tests and summarize results with exact commands.
- `doc_manager`: capture decisions, commands, and changes; propose reusable skills/AGENTS.md additions.

Rule: keep role boundaries strict; if a role is unavailable, continue with the closest role and state the fallback.

## Shell Preference
When running or suggesting shell commands:
- Prefer Bash (POSIX-style) commands/syntax first (Git Bash / WSL style).
- Use PowerShell (`pwsh`) only as a fallback for Windows-specific tasks or when Bash isn't available.

## Multi-Agent Team Default
When multi-agent is enabled, use this team by default.

- `planner`: requirements, assumptions, success criteria, task breakdown, and agent routing.
- `doc_manager`: project memory + docs; capture decisions/commands; recommend reusable `skills` and useful local `AGENTS.md` additions for the orchestrator.
- `worker`: implement code changes and patches.
- `explorer`: read-only codebase exploration and risk discovery (no edits).
- `reviewer`: read-only review for correctness, security, and test risks.
- `tester`: run tests and summarize results.

Execution rule:
- Route tasks to the best-fit role first.
- Keep role boundaries strict unless the user explicitly asks to override.
- If a role is unavailable, report it and continue with the closest role.

1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.
2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
