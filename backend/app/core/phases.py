from __future__ import annotations

import enum

from app.models import TaskStatus


class WorkflowPhase(str, enum.Enum):
    QUEUED = "QUEUED"
    WORKSPACE = "WORKSPACE"
    PLAN = "PLAN"
    IMPLEMENT = "IMPLEMENT"
    APPROVAL = "APPROVAL"
    MERGE = "MERGE"
    TERMINAL = "TERMINAL"


def phase_for_status(status: TaskStatus) -> WorkflowPhase:
    if status in (TaskStatus.PENDING,):
        return WorkflowPhase.QUEUED
    if status in (TaskStatus.PREPARING_WORKSPACE,):
        return WorkflowPhase.WORKSPACE
    if status in (TaskStatus.PLANNING,):
        return WorkflowPhase.PLAN
    if status in (TaskStatus.IMPLEMENTING, TaskStatus.TESTING):
        return WorkflowPhase.IMPLEMENT
    if status in (TaskStatus.AWAIT_PLAN_APPROVAL, TaskStatus.AWAIT_MERGE_APPROVAL):
        return WorkflowPhase.APPROVAL
    if status in (TaskStatus.MERGING,):
        return WorkflowPhase.MERGE
    return WorkflowPhase.TERMINAL
