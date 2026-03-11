# Task Learning Follow-Ups

Date: 2026-03-11

## Current V1 State

Implemented:

- successful task path triggers a best-effort learning reflection after `verify`
- reflection is classified as `note_only` or `skill_candidate`
- reflections are stored under `project/learnings/reflections/`
- registry entries are stored in `project/learnings/registry.json`
- generated skills are written under `runtime/codex/home/skills/generated/`
- learning runs through the new `doc_manager` agent and `learn` prompt

Explicitly deferred from v1:

- automatic skill activation / ranking / pruning
- human review workflow for generated skills
- UI for browsing reflections or generated skills
- deduplication across multiple tasks that discover the same technique
- richer task-level metadata for querying learning results from the API

## Next Tasks

### 1. Review And Promotion Workflow

- add a clear path to review generated skills before they are treated as trusted
- define statuses such as `draft`, `approved`, `rejected`, `superseded`
- keep generated drafts separate from curated skills

### 2. Skill Discovery In Future Runs

- make planner/orchestrator aware of generated skills
- load only relevant generated skills, not the whole generated directory
- define selection rules so low-quality drafts do not pollute context

### 3. Deduplication And Versioning

- detect when multiple tasks produce the same technique
- merge or version similar generated skills instead of creating duplicates
- record source task ids for all merged skills

### 4. Better Reusability Heuristics

- tighten the distinction between `note_only` and `skill_candidate`
- reject one-off repo hacks more aggressively
- consider adding a confidence field and minimum threshold

### 5. API / UI Surface

- expose reflection summaries and generated skill metadata in task APIs
- add dashboard views for:
  - reflection history
  - generated skill drafts
  - review / approve / reject actions

### 6. Archive Integration

- include reflection and generated skill references in archived task snapshots
- preserve linkage even if the generated skill is later updated or removed

### 7. Failure And Retry Behavior

- add explicit tests for learning-step failure inside workflow success path
- confirm reflection exceptions never block merge readiness
- decide whether repeated learning failures should be surfaced in a registry or health view

### 8. Contract / Agent Cleanup

- update generated runtime docs and any stale generated instructions that still describe the old pipeline
- decide whether `doc_manager` should stay a standalone role or eventually become a more general memory/knowledge role

## Suggested Order

1. review/promotion workflow
2. deduplication + versioning
3. skill discovery in future runs
4. API/UI surface
5. archive integration

## Verification Baseline

Current known-good validation after v1:

- `python tools/codex_contract.py apply`
- `python tools/codex_contract.py verify`
- `cd backend && ./.venv/Scripts/python.exe -m pytest`

Latest backend result:

- `91 passed`
