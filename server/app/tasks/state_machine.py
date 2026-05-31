from __future__ import annotations

from sqlmodel import Session

from ..knowledge_core.source_items import validate_choice
from ..models import TaskSession, utc_now


TASK_SESSION_STATUSES = {
    "open",
    "paused",
    "handoff_ready",
    "waiting_user",
    "closing_review",
    "closed",
    "archived",
    "expired",
}
ACTIVE_TASK_SESSION_STATUSES = {"open", "paused", "handoff_ready", "waiting_user"}
TERMINAL_TASK_SESSION_STATUSES = {"closed", "archived", "expired"}

TASK_SESSION_TRANSITIONS = {
    "open": {"paused", "handoff_ready", "waiting_user", "closing_review", "closed", "archived", "expired"},
    "paused": {"open", "handoff_ready", "waiting_user", "closed", "archived", "expired"},
    "handoff_ready": {"open", "paused", "waiting_user", "closed", "archived", "expired"},
    "waiting_user": {"open", "paused", "closing_review", "closed", "archived", "expired"},
    "closing_review": {"open", "closed", "archived", "expired"},
    "closed": {"archived"},
    "expired": {"archived"},
    "archived": set(),
}


def validate_task_status(status: str) -> str:
    clean = status.strip()
    validate_choice(clean, TASK_SESSION_STATUSES, "taskSessionStatus")
    return clean


def is_active_task_status(status: str) -> bool:
    return status in ACTIVE_TASK_SESSION_STATUSES


def is_terminal_task_status(status: str) -> bool:
    return status in TERMINAL_TASK_SESSION_STATUSES


def ensure_task_mutable(task: TaskSession) -> None:
    if is_terminal_task_status(task.status):
        raise ValueError("终态任务不能执行该操作")


def transition_task_session(
    session: Session,
    task: TaskSession,
    target_status: str,
    *,
    reason: str = "",
    allow_same: bool = True,
) -> TaskSession:
    clean_status = validate_task_status(target_status)
    current_status = validate_task_status(task.status)
    if clean_status == current_status:
        if allow_same:
            return task
        raise ValueError(f"任务已经是 {clean_status} 状态")
    allowed = TASK_SESSION_TRANSITIONS.get(current_status, set())
    if clean_status not in allowed:
        raise ValueError(f"任务状态不能从 {current_status} 切换到 {clean_status}")

    task.status = clean_status
    now = utc_now()
    task.updated_at = now
    if clean_status == "closed":
        task.closed_at = now
    session.add(task)

    from .events import append_task_event

    append_task_event(
        session,
        task,
        event_type="task_status_changed",
        summary=reason or f"任务状态从 {current_status} 切换到 {clean_status}",
        payload={"fromStatus": current_status, "toStatus": clean_status},
    )
    session.flush()
    return task
