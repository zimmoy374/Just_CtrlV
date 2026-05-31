from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from ..memory_kernel.proposals import create_memory_proposal
from ..models import TaskSession
from .events import append_task_event
from .state_machine import (
    ACTIVE_TASK_SESSION_STATUSES,
    ensure_task_mutable,
    transition_task_session,
    validate_task_status,
)
from .state import get_or_create_task_state


def get_task_session(session: Session, task_id: str) -> TaskSession | None:
    return session.get(TaskSession, task_id)


def list_task_sessions(session: Session, *, status: str = "active") -> list[TaskSession]:
    statement = select(TaskSession)
    if status == "active":
        statement = statement.where(TaskSession.status.in_(ACTIVE_TASK_SESSION_STATUSES))
    elif status != "all":
        statement = statement.where(TaskSession.status == validate_task_status(status))
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
    return transition_task_session(session, task, "paused", reason="任务已暂停")


def archive_task_session(session: Session, task: TaskSession) -> TaskSession:
    return transition_task_session(session, task, "archived", reason="任务已归档")


def close_task_session(session: Session, task: TaskSession) -> TaskSession:
    ensure_task_mutable(task)
    transition_task_session(session, task, "closed", reason="用户确认任务结束")
    _create_close_memory_proposal(session, task)
    session.flush()
    return task


def set_task_session_status(session: Session, task: TaskSession, status: str) -> TaskSession:
    return transition_task_session(session, task, status)


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
