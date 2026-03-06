# Repository Guidelines

## Project Structure & Module Organization
This repository has two main apps:

- `backend/`: FastAPI service. Core code lives in `backend/app/`, with API routers in `backend/app/api/` and service logic in `backend/app/services/`.
- `backend/tests/`: pytest suite for backend behavior, currently centered on Git/worktree flows.
- `dashboard/`: Next.js App Router frontend. Routes live in `dashboard/src/app/`, reusable UI in `dashboard/src/components/`, and client helpers in `dashboard/src/lib/` and `dashboard/src/hooks/`.
- Runtime directories such as `logs/`, `repos/`, `workspaces/`, and `database/` are kept at the repo root.

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
Do not commit real repository data, logs, or local database files. Keep local settings aligned with `http://localhost:3000` to match the backend CORS configuration during development.
