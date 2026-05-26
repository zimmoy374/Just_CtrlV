from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from ..knowledge_core.source_items import validate_choice
from ..memory_kernel.proposals import create_memory_proposal
from ..models import TaskSession, utc_now
from .events import append_task_event
from .state import get_or_create_task_state


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


def get_task_session(session: Session, task_id: str) -> TaskSession | None:
    return session.get(TaskSession, task_id)


def list_task_sessions(session: Session, *, status: str = "active") -> list[TaskSession]:
    statement = select(TaskSession)
    if status == "active":
        statement = statement.where(TaskSession.status.in_(ACTIVE_TASK_SESSION_STATUSES))
    elif status != "all":
        validate_choice(status, TASK_SESSION_STATUSES, "taskSessionStatus")
        statement = statement.where(TaskSession.status == status)
    return list(session.exec(statement.order_by(TaskSession.updated_at.desc())).all())


def create_task_session(
    session: Session,
    *,
    title: str,
    user_goal: str,
    active_agent: str = "",
) -> TaskSession:
    clean_title = title.strip()
    clean_goal = user_goal.strip()
    if not clean_title:
        raise ValueError("TaskSession title 不能为空")
    if not clean_goal:
        raise ValueError("TaskSession userGoal 不能为空")

    task = TaskSession(
        id=str(uuid4()),
        title=clean_title,
        user_goal=clean_goal,
        active_agent=active_agent.strip(),
        status="open",
    )
    session.add(task)
    session.flush()
    get_or_create_task_state(session, task.id, current_goal=clean_goal)
    append_task_event(
        session,
        task,
        event_type="user_goal",
        summary=clean_goal,
        payload={"title": clean_title, "activeAgent": task.active_agent},
    )
    return task


def pause_task_session(session: Session, task: TaskSession) -> TaskSession:
    _ensure_not_terminal(task)
    task.status = "paused"
    task.updated_at = utc_now()
    session.add(task)
    append_task_event(session, task, event_type="agent_observation", summary="任务已暂停")
    session.flush()
    return task


def archive_task_session(session: Session, task: TaskSession) -> TaskSession:
    task.status = "archived"
    task.updated_at = utc_now()
    session.add(task)
    session.flush()
    return task


def close_task_session(session: Session, task: TaskSession) -> TaskSession:
    _ensure_not_terminal(task)
    task.status = "closed"
    now = utc_now()
    task.closed_at = now
    task.updated_at = now
    session.add(task)
    append_task_event(session, task, event_type="task_closed", summary="用户确认任务结束")
    _create_close_memory_proposal(session, task)
    session.flush()
    return task


def set_task_session_status(session: Session, task: TaskSession, status: str) -> TaskSession:
    validate_choice(status, TASK_SESSION_STATUSES, "taskSessionStatus")
    task.status = status
    task.updated_at = utc_now()
    session.add(task)
    session.flush()
    return task


def _create_close_memory_proposal(session: Session, task: TaskSession) -> None:
    state = get_or_create_task_state(session, task.id, current_goal=task.user_goal)
    lines = [
        f"任务：{task.title}",
        f"目标：{state.current_goal or task.user_goal}",
    ]
    if state.done_json:
        lines.append(f"已完成：{'；'.join(state.done_json)}")
    if state.decisions_json:
        lines.append(f"关键决策：{'；'.join(state.decisions_json)}")
    if state.risks_json:
        lines.append(f"风险/踩坑：{'；'.join(state.risks_json)}")
    if state.constraints_json:
        lines.append(f"约束/偏好：{'；'.join(state.constraints_json)}")
    body = "\n".join(lines)
    create_memory_proposal(
        session,
        proposal_type="workflow_pattern",
        title=f"{task.title} 任务经验",
        body=body,
        evidence_refs=[f"task:{task.id}"],
        task_session_id=task.id,
    )


def _ensure_not_terminal(task: TaskSession) -> None:
    if task.status in {"closed", "archived", "expired"}:
        raise ValueError("终态任务不能执行该操作")
