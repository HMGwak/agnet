

# AI Dev Automation Dashboard

## Detailed PRD & System Design (Symphony + Codex)

Author: Generated Design\
Scope: Personal AI Development Automation System\
Target: Local machine orchestration with dashboard visibility

------------------------------------------------------------------------

# 1. Project Goal

Build a **local AI development orchestration system** where a user can:

-   Create development tasks (tickets)
-   Allow AI agents to plan and implement code changes
-   Review the plan and code diff
-   Approve or reject the change
-   Merge directly into the main branch
-   Track logs and execution state from a dashboard

This system eliminates manual work such as:

-   remembering worktrees
-   creating branches
-   merging code
-   managing coding agent sessions

------------------------------------------------------------------------

# 2. Core Concept

Development tasks are executed through a controlled workflow:

Task → Plan → Approval → Implementation → Test → Approval → Merge

Each stage is observable and controllable from a dashboard.

------------------------------------------------------------------------

# 3. Reference Implementations

The architecture is inspired by the following open source systems.

## Symphony

GitHub: https://github.com/openai/symphony

Symphony acts as an **AI orchestration engine** that schedules coding
agents and manages task execution.

Main responsibilities:

-   task orchestration
-   workspace creation
-   agent execution lifecycle
-   logging

------------------------------------------------------------------------

## Codex CLI

GitHub: https://github.com/openai/codex

Codex CLI is used as the **coding agent runtime**.

Capabilities:

-   repository analysis
-   file editing
-   running commands
-   generating commits

The system will use:

codex app-server

to maintain a session with the coding agent.

------------------------------------------------------------------------

# 4. High Level Architecture

Dashboard UI │ ▼ Backend API │ ▼ SQLite Database │ ▼ Task Orchestrator │
▼ Symphony Worker │ ▼ Codex Agent │ ▼ Git Repository

------------------------------------------------------------------------

# 5. System Components

## Dashboard

Purpose:

-   task creation
-   status visualization
-   approval control
-   log viewing

Suggested stack:

-   Next.js
-   React
-   Tailwind

Key views:

-   Task Board
-   Execution Logs
-   Plan Approval
-   Merge Approval

------------------------------------------------------------------------

## Backend API

Responsibilities:

-   task creation
-   orchestration control
-   worker communication
-   approval workflow

Suggested stack:

FastAPI (Python)

Key endpoints:

POST /tasks\
GET /tasks\
GET /tasks/{id}\
POST /tasks/{id}/approve-plan\
POST /tasks/{id}/approve-merge\
POST /tasks/{id}/cancel

------------------------------------------------------------------------

## Database

Local database:

SQLite3

Tables:

repos\
tasks\
runs\
approvals

------------------------------------------------------------------------

# 6. Task Lifecycle

Task states:

PENDING\
PREPARING_WORKSPACE\
PLANNING\
AWAIT_PLAN_APPROVAL\
IMPLEMENTING\
TESTING\
AWAIT_MERGE_APPROVAL\
MERGING\
DONE\
FAILED

------------------------------------------------------------------------

# 7. Workspace Strategy

User selectable workspace modes.

Option A: Git Worktree (Recommended)

git worktree add ../task-123 feature/task-123

Option B: Repository Clone

git clone repo task-123

------------------------------------------------------------------------

# 8. Merge Strategy

PRs are skipped for simplicity.

Workflow:

feature branch → tests pass → approval → merge into main

Commands:

git checkout main\
git merge feature/task-123\
git push origin main

------------------------------------------------------------------------

# 9. Execution Flow

Example:

1.  User creates task
2.  Workspace created
3.  Codex generates plan
4.  Plan approval
5.  Code implementation
6.  Tests run
7.  Merge approval
8.  Merge to main

------------------------------------------------------------------------

# 10. Parallel Execution

Max concurrent agents:

6 workers

Policy:

only one task per repository at a time

------------------------------------------------------------------------

# 11. Logging

Logs stored as:

/logs/task-{id}.log

Dashboard streams logs.

------------------------------------------------------------------------

# 12. Human-in-the-loop Controls

Approval stages:

Plan approval\
Merge approval

------------------------------------------------------------------------

# 13. Failure Handling

retry once → mark FAILED

------------------------------------------------------------------------

# 14. Security Model

Local system accessed via SSH.

Protections:

workspace isolation\
repo permission control\
agent sandboxing

------------------------------------------------------------------------

# 15. Folder Structure

ai-dev-system/

backend/\
dashboard/\
repos/\
workspaces/\
logs/\
database/

------------------------------------------------------------------------

# 16. Future Extensions

Multi-agent system

Planner Agent\
Coding Agent\
Test Agent\
Review Agent

CI integration\
Auto merge\
AI code review

------------------------------------------------------------------------

# 17. Vision

Task → AI Planning → AI Implementation → Validation → Merge

A personal AI development operations platform.

