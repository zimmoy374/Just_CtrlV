from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from ..knowledge_core.source_items import upsert_source_item, validate_choice
from ..models import TaskEvent, TaskSession, utc_now
from .safety import sanitize_task_payload, sanitize_task_text


TASK_EVENT_TYPES = {
    "user_goal",
    "user_constraint",
    "agent_observation",
    "agent_action",
    "decision",
    "file_change",
    "test_result",
    "blocker",
    "question",
    "checkpoint_created",
    "handoff_created",
    "close_suggested",
    "task_closed",
    "memory_candidate",
    "task_status_changed",
}


def list_task_events(session: Session, task_session_id: str) -> list[TaskEvent]:
    return list(
        session.exec(
            select(TaskEvent).where(TaskEvent.task_session_id == task_session_id).order_by(TaskEvent.created_at),
        ).all(),
    )


def append_task_event(
    session: Session,
    task: TaskSession,
    *,
    event_type: str,
    summary: str,
    payload: dict | None = None,
    source: str = "second_brain",
    source_ref: str = "",
) -> TaskEvent:
    validate_choice(event_type, TASK_EVENT_TYPES, "taskEventType")
    clean_summary = sanitize_task_text(summary)
    if not clean_summary:
        raise ValueError("TaskEvent summary 不能为空")
    clean_payload = sanitize_task_payload(payload or {})

    event = TaskEvent(
        id=str(uuid4()),
        task_session_id=task.id,
        type=event_type,
        summary=clean_summary,
        payload_json=clean_payload,
        source=source,
        source_ref=source_ref,
    )
    task.last_event_at = event.created_at
    task.updated_at = utc_now()
    session.add(event)
    session.add(task)
    session.flush()
    upsert_source_item(
        session,
        source="second_brain",
        external_id=f"task-event:{event.id}",
        kind="task_event",
        title=f"{task.title} / {event.type}",
        content_text=event.summary,
        metadata={
            "taskSessionId": task.id,
            "eventType": event.type,
            "eventPayload": event.payload_json,
            "eventSource": event.source,
            "eventSourceRef": event.source_ref,
        },
        status="active",
    )
    return event
