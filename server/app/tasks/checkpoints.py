from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from ..models import TaskCheckpoint, TaskEvent, TaskSession, TaskState
from .events import append_task_event
from .state import task_state_snapshot


def list_task_checkpoints(session: Session, task_session_id: str) -> list[TaskCheckpoint]:
    return list(
        session.exec(
            select(TaskCheckpoint).where(TaskCheckpoint.task_session_id == task_session_id).order_by(TaskCheckpoint.created_at),
        ).all(),
    )


def create_task_checkpoint(
    session: Session,
    task: TaskSession,
    *,
    title: str,
    summary: str,
) -> TaskCheckpoint:
    clean_title = title.strip()
    clean_summary = summary.strip()
    if not clean_title:
        raise ValueError("TaskCheckpoint title 不能为空")

    events = session.exec(
        select(TaskEvent).where(TaskEvent.task_session_id == task.id).order_by(TaskEvent.created_at),
    ).all()
    state = session.get(TaskState, task.id)
    checkpoint = TaskCheckpoint(
        id=str(uuid4()),
        task_session_id=task.id,
        title=clean_title,
        summary=clean_summary,
        state_snapshot_json=task_state_snapshot(state),
        event_from_id=events[0].id if events else None,
        event_to_id=events[-1].id if events else None,
    )
    session.add(checkpoint)
    session.flush()
    append_task_event(
        session,
        task,
        event_type="checkpoint_created",
        summary=f"创建检查点：{checkpoint.title}",
        payload={"checkpointId": checkpoint.id},
    )
    return checkpoint
