# AI Dev Automation Dashboard

An agentic AI system that autonomously plans, implements, tests, and reviews code changes. You submit a task in natural language; the AI pipeline does the rest.

---

## Quick Start

```bat
# Windows
./start.bat

# macOS / Linux
./start.sh
```

| Service   | URL                       |
|-----------|---------------------------|
| Dashboard | http://localhost:3000     |
| Backend   | http://localhost:8001     |

On first run you will be prompted to log in to Codex (OAuth). The credentials are cached in `runtime/codex/home/auth.json` and reused on subsequent runs.

**Prerequisites**: `uv` (Python package manager) and `npm` (Node.js LTS).

---

## How the System Works

### Architecture at a Glance

```
User (Dashboard)
   │  submits a Task
   ▼
Backend (FastAPI :8001)
   │  orchestrates the pipeline
   ├─► Planner agent    → produces an implementation plan
   ├─► Critic agent     → approves or rejects the plan
   ├─► Executor agent   → writes code into the workspace
   ├─► Tester agent     → runs smoke-checks / static validation
   └─► Reviewer agent   → gates merge readiness
   │
   └─► Git worktree (isolated workspace per task)
```

Each agent is powered by the Codex SDK via a local Node.js sidecar (`runtime/codex/sidecar/server.mjs`).

---

## Using the Dashboard

### Step 1 — Register a Repository

> **URL**: `http://localhost:3000/repos`

A **Repository** is the target Git project where the AI will make changes.

1. Click **Register Repo**.
2. Fill in:
   - **Name** – a short label (e.g. `my-app`).
   - **Path** – the **absolute path** to the local Git repo (e.g. `D:\Projects\my-app`). The directory must already be a Git repository (`git init` or `git clone` first).
3. Click **Register**.

> ⚠️ The path must be a real, existing Git repo on the local filesystem. Do **not** use a workspace subfolder path — use the top-level repo root.

---

### Step 2 — Add a Task

> **URL**: `http://localhost:3000/tasks?repo_id=<id>`

From the Tasks board for a repository, click **+ Add Task**.

| Field | What to Fill |
|-------|-------------|
| **Task input** | Plain-language description of what to build or fix. Be specific: *"Add power-up items. When a block is broken, drop one of: multi-ball (3 balls), paddle enlarge, slow-ball. Enlarge and slow-ball last 10 paddle hits."* |
| **Workspace** | Choose **Existing workspace** to reuse a previous branch, **or** choose **Create new workspace** to start a fresh Git branch. |

Click **Create Task**. The AI intake agent may ask a follow-up clarifying question — answer it and click **Update Draft**, then submit.

> **Tip for AI agents reading this**: Always pick *Existing workspace* when adding features to code that already lives in a named workspace. Only use *Create new workspace* for brand-new features that have no prior branch.

---

### Step 3 — Monitor Progress

The task board shows columns:

| Column | Meaning |
|--------|---------|
| **Queued** | Task is waiting to be picked up |
| **Working** | Agent pipeline is running (Plan → Critique → Implement → Test → Review) |
| **Needs Approval** | Pipeline finished; awaiting human merge approval |
| **Needs Attention** | Agent found a problem and needs a follow-up instruction |
| **Cancelled** | Manually stopped |
| **Done** | Merged and complete |

Click any task card to open **Task Details** with:
- **Execution Status** – live log stream
- **Step History** – click individual steps (PLAN, CRITIQUE, IMPLEMENT, TEST, REVIEW) to view their logs and artifacts

---

### Step 4 — Handling "Needs Attention"

When the Reviewer or Tester blocks the task, it moves to **Needs Attention** with a detailed error. Common causes:

| Error | Fix |
|-------|-----|
| `read-only workspace` | Config issue (see [Windows Sandbox Fix](#windows-sandbox-fix)) |
| Reviewer `NEEDS_ATTENTION: <bug description>` | Describe the fix in **Next Action** and re-queue |
| Tester failure | Describe what passed/failed and re-queue |

To re-queue:
1. Open the task and scroll to **Next Action**.
2. In the text box, describe exactly what to fix (the more specific the better).
3. Click **Send Command & Requeue**.

The pipeline restarts from the beginning (Plan → Critique → Implement → Test → Review).

---

### Step 5 — Approval & Merge

When a task reaches **Needs Approval**, the Reviewer's verdict was `APPROVED`. Click **Approve & Merge** to merge the workspace branch into main.

---

## Pipeline Details

### Agent Roles

| Agent | Role |
|-------|------|
| **intake** | Parses the user's natural language into a structured task draft |
| **planner** | Produces a detailed implementation plan |
| **critic** | Reviews the plan for scope and feasibility |
| **executor** | Writes code; runs in `workspace-write` sandbox mode |
| **tester** | Runs static validation and project-specific checks |
| **reviewer** | Final code review; blocks or approves merge |

### Workspace = Git Worktree

Each task runs in an isolated Git worktree under `project/workspaces/`. Files are written there, staged, and committed. The workspace name is shown in the Task Details panel.

---

## Configuration

### Key Settings (`backend/app/config.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `CODEX_MODEL` | `gpt-5.4` | LLM model for all agents |
| `CODEX_SANDBOX_MODE` | `workspace-write` | Codex sandbox policy |
| `CODEX_WINDOWS_UNSANDBOXED_WORKAROUND` | `True` | **Required on Windows** — upgrades to `danger-full-access` to work around a Codex 0.111.0 bug |
| `CODEX_APPROVAL_POLICY` | `never` | Auto-approve all shell commands |
| `CODEX_RUN_TIMEOUT_S` | `300` | Per-agent timeout in seconds |
| `MAX_CONCURRENT_TASKS` | `6` | Max parallel agent pipelines |

### Windows Sandbox Fix

Codex 0.111.0 on Windows silently downgrades `workspace-write` to read-only, causing the executor to fail with:
```
Warning: Implementation completed without creating any file changes in the workspace.
```

The fix is already applied in `config.py`:
```python
CODEX_WINDOWS_UNSANDBOXED_WORKAROUND: bool = True
```

This enables `danger-full-access` mode on Windows only, which gives the executor full write access while leaving behaviour unchanged on other platforms.

---

## Codex Contract

The agent behaviour is defined in [`runtime/codex/contract/codex-contract.toml`](runtime/codex/contract/codex-contract.toml).

To update agent instructions or model settings:
1. Edit `codex-contract.toml`.
2. Run `python tools/codex_contract.py apply` to regenerate managed files.
3. Run `python tools/codex_contract.py verify` to check for drift.

---

## File Layout

```
agent/
├── backend/               # FastAPI backend
│   └── app/
│       ├── core/          # Workflow, policy, orchestration
│       ├── adapters/      # Git, SQLite, Codex, WebSocket
│       └── bootstrap/     # Runtime startup (config, sidecar)
├── dashboard/             # Next.js frontend
├── runtime/codex/
│   ├── contract/          # Agent instructions & codex-contract.toml
│   ├── home/              # Codex auth cache (auth.json)
│   ├── prompts/           # Prompt templates per phase
│   └── sidecar/           # Node.js Codex SDK wrapper
├── project/               # Local data (gitignored)
│   ├── database/          # dev.db (SQLite)
│   ├── repos/             # Cloned/linked repositories
│   ├── workspaces/        # Git worktrees per task
│   └── logs/              # Session and task logs
└── tools/                 # Helper scripts (codex login, contract)
```

---

## Common Workflows for AI Agents

### ✅ Add a new feature to an existing project

1. Navigate to `http://localhost:3000/tasks?repo_id=<id>`
2. Click **+ Add Task**
3. In the task input, describe the feature precisely
4. Under **Workspace**, select the existing workspace that contains the current code
5. Submit and monitor the **Working** column

### ✅ Fix a bug reported in Needs Attention

1. Open the task (click the card)
2. Read the Reviewer/Tester verdict in Step Logs
3. Scroll to **Next Action**, type a precise fix instruction referencing the file/line
4. Click **Send Command & Requeue**

### ✅ Add features on top of a previous task's work

Same as above — always select the **existing workspace** so the agent sees the code already written in that branch, not the main branch.

### ❌ Do NOT

- Register a workspace path as if it were a repository — use the actual repo root
- Create a new workspace when the target code already lives in an existing workspace
- Leave the Next Action box empty when re-queuing — the agent has no context without it

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Task stuck in "Preparing" | Backend not running | Check `project/logs/<session>/backend.err.log` |
| `read-only workspace` error | Windows sandbox bug | Set `CODEX_WINDOWS_UNSANDBOXED_WORKAROUND = True` in `config.py` and restart |
| Reviewer keeps blocking | Persistent code bug | Open Step 9 logs, read the DETAILS section, provide a targeted fix instruction |
| Dashboard blank / API 404 | Backend crashed | Run `./start.bat` again; check backend logs |
| Codex auth expired | OAuth token stale | Delete `runtime/codex/home/auth.json` and restart (login prompt appears) |
