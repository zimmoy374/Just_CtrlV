from __future__ import annotations

from sqlmodel import Session

from ..models import TaskState, utc_now
from .safety import sanitize_task_text


TASK_STATE_LIST_FIELDS = {
    "done",
    "in_progress",
    "next_steps",
    "open_questions",
    "constraints",
    "risks",
    "decisions",
    "files_touched",
}


def get_or_create_task_state(session: Session, task_session_id: str, *, current_goal: str = "") -> TaskState:
    state = session.get(TaskState, task_session_id)
    if state:
        return state
    state = TaskState(task_session_id=task_session_id, current_goal=current_goal)
    session.add(state)
    session.flush()
    return state


def update_task_state(
    session: Session,
    task_session_id: str,
    *,
    current_goal: str | None = None,
    done: list[str] | None = None,
    in_progress: list[str] | None = None,
    next_steps: list[str] | None = None,
    open_questions: list[str] | None = None,
    constraints: list[str] | None = None,
    risks: list[str] | None = None,
    decisions: list[str] | None = None,
    files_touched: list[str] | None = None,
    confidence: float | None = None,
) -> TaskState:
    state = get_or_create_task_state(session, task_session_id)
    if current_goal is not None:
        state.current_goal = current_goal.strip()
    if done is not None:
        state.done_json = _clean_list(done)
    if in_progress is not None:
        state.in_progress_json = _clean_list(in_progress)
    if next_steps is not None:
        state.next_steps_json = _clean_list(next_steps)
    if open_questions is not None:
        state.open_questions_json = _clean_list(open_questions)
    if constraints is not None:
        state.constraints_json = _clean_list(constraints)
    if risks is not None:
        state.risks_json = _clean_list(risks)
    if decisions is not None:
        state.decisions_json = _clean_list(decisions)
    if files_touched is not None:
        state.files_touched_json = _clean_list(files_touched)
    if confidence is not None:
        state.confidence = min(1.0, max(0.0, confidence))
    state.updated_at = utc_now()
    session.add(state)
    session.flush()
    return state


def task_state_snapshot(state: TaskState | None) -> dict:
    if not state:
        return {}
    return {
        "currentGoal": state.current_goal,
        "done": state.done_json or [],
        "inProgress": state.in_progress_json or [],
        "nextSteps": state.next_steps_json or [],
        "openQuestions": state.open_questions_json or [],
        "constraints": state.constraints_json or [],
        "risks": state.risks_json or [],
        "decisions": state.decisions_json or [],
        "filesTouched": state.files_touched_json or [],
        "confidence": state.confidence,
        "updatedAt": state.updated_at.isoformat(),
    }


def _clean_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        clean = sanitize_task_text(str(value), limit=600)
        if clean and clean not in cleaned:
            cleaned.append(clean)
    return cleaned
