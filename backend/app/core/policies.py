from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime

from app.models import Task, TaskStatus


def slugify(text: str) -> str:
    original = text.strip()
    normalized = unicodedata.normalize("NFKD", original)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower().strip()
    ascii_text = re.sub(r"[^\w\s-]", "", ascii_text)
    ascii_text = re.sub(r"[\s_]+", "-", ascii_text).strip("-")
    if ascii_text:
        return ascii_text[:50]
    if not original:
        return ""
    digest = hashlib.sha1(original.encode("utf-8")).hexdigest()[:10]
    return f"task-{digest}"


def should_mark_needs_attention(task: Task) -> bool:
    if task.status != TaskStatus.FAILED:
        return False
    message = (task.error_message or "").strip()
    return message.startswith("Plan rejected:") or message.startswith("Merge rejected:")


def append_follow_up_instructions(description: str, comment: str) -> str:
    cleaned_comment = comment.strip()
    if not cleaned_comment:
        return description

    block = f"Follow-up instructions:\n{cleaned_comment}"
    cleaned_description = description.strip()
    if not cleaned_description:
        return block
    return f"{cleaned_description}\n\n{block}"


async def is_task_ready(session, task: Task) -> bool:
    if task.status != TaskStatus.PENDING:
        return True

    now = datetime.now()
    if task.scheduled_for and task.scheduled_for > now:
        return False

    if task.blocked_by_task_id:
        dependency = await session.get(Task, task.blocked_by_task_id)
        if not dependency:
            return False
        return dependency.status == TaskStatus.DONE

    return True
