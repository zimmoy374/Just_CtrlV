from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ..database import get_session
from ..models import TaskSession, utc_now
from ..presenters import (
    handoff_pack_to_response,
    task_checkpoint_to_response,
    task_detail_to_response,
    task_event_to_response,
    task_session_to_response,
    task_state_to_response,
)
from ..schemas import (
    TaskCheckpointCreate,
    TaskCheckpointResponse,
    TaskDetailResponse,
    TaskEventCreate,
    TaskEventResponse,
    HandoffPackResponse,
    TaskSessionCreate,
    TaskSessionResponse,
    TaskStatePatch,
    TaskStateResponse,
)
from ..tasks.checkpoints import create_task_checkpoint, list_task_checkpoints
from ..tasks.events import append_task_event, list_task_events
from ..tasks.handoff import create_handoff_pack, preview_handoff_pack
from ..tasks.sessions import (
    archive_task_session,
    close_task_session,
    create_task_session,
    get_task_session,
    list_task_sessions,
    pause_task_session,
)
from ..tasks.state import get_or_create_task_state, update_task_state


router = APIRouter()


@router.post("/api/tasks", response_model=TaskDetailResponse)
def create_task_api(payload: TaskSessionCreate, session: Session = Depends(get_session)) -> TaskDetailResponse:
    try:
        task = create_task_session(
            session,
            title=payload.title,
            user_goal=payload.user_goal,
            active_agent=payload.active_agent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    task = _require_task(session, task.id)
    return _task_detail(session, task)


@router.get("/api/tasks", response_model=list[TaskSessionResponse])
def list_tasks_api(status: str = "active", session: Session = Depends(get_session)) -> list[TaskSessionResponse]:
    try:
        tasks = list_task_sessions(session, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [task_session_to_response(task) for task in tasks]


@router.get("/api/tasks/{task_id}", response_model=TaskDetailResponse)
def get_task_api(task_id: str, session: Session = Depends(get_session)) -> TaskDetailResponse:
    return _task_detail(session, _require_task(session, task_id))


@router.patch("/api/tasks/{task_id}/state", response_model=TaskStateResponse)
def patch_task_state_api(
    task_id: str,
    payload: TaskStatePatch,
    session: Session = Depends(get_session),
) -> TaskStateResponse:
    _require_task(session, task_id)
    state = update_task_state(
        session,
        task_id,
        current_goal=payload.current_goal,
        done=payload.done,
        in_progress=payload.in_progress,
        next_steps=payload.next_steps,
        open_questions=payload.open_questions,
        constraints=payload.constraints,
        risks=payload.risks,
        decisions=payload.decisions,
        files_touched=payload.files_touched,
        confidence=payload.confidence,
    )
    session.commit()
    session.refresh(state)
    return task_state_to_response(state)


@router.post("/api/tasks/{task_id}/events", response_model=TaskEventResponse)
def append_task_event_api(
    task_id: str,
    payload: TaskEventCreate,
    session: Session = Depends(get_session),
) -> TaskEventResponse:
    task = _require_task(session, task_id)
    try:
        event = append_task_event(
            session,
            task,
            event_type=payload.type,
            summary=payload.summary,
            payload=payload.payload,
            source=payload.source,
            source_ref=payload.source_ref,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    session.refresh(event)
    return task_event_to_response(event)


@router.post("/api/tasks/{task_id}/checkpoints", response_model=TaskCheckpointResponse)
def create_task_checkpoint_api(
    task_id: str,
    payload: TaskCheckpointCreate,
    session: Session = Depends(get_session),
) -> TaskCheckpointResponse:
    task = _require_task(session, task_id)
    try:
        checkpoint = create_task_checkpoint(session, task, title=payload.title, summary=payload.summary)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    session.refresh(checkpoint)
    return task_checkpoint_to_response(checkpoint)


@router.get("/api/tasks/{task_id}/handoff", response_model=HandoffPackResponse)
def get_task_handoff_api(
    task_id: str,
    format: str = Query(default="markdown"),
    include_closed: bool = Query(default=False, alias="includeClosed"),
    session: Session = Depends(get_session),
) -> HandoffPackResponse:
    task = _require_task(session, task_id)
    try:
        pack, content, budget = preview_handoff_pack(
            session,
            task,
            handoff_format=format,
            include_closed=include_closed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return HandoffPackResponse(
        id=None,
        taskSessionId=task.id,
        format=format,
        content=content,
        pack=pack,
        budget=budget,
        createdAt=utc_now(),
    )


@router.post("/api/tasks/{task_id}/handoff", response_model=HandoffPackResponse)
def create_task_handoff_api(
    task_id: str,
    format: str = Query(default="markdown"),
    include_closed: bool = Query(default=False, alias="includeClosed"),
    session: Session = Depends(get_session),
) -> HandoffPackResponse:
    task = _require_task(session, task_id)
    try:
        handoff, pack = create_handoff_pack(
            session,
            task,
            handoff_format=format,
            include_closed=include_closed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(handoff)
    return handoff_pack_to_response(handoff, pack)


@router.post("/api/tasks/{task_id}/pause", response_model=TaskDetailResponse)
def pause_task_api(task_id: str, session: Session = Depends(get_session)) -> TaskDetailResponse:
    task = _require_task(session, task_id)
    try:
        pause_task_session(session, task)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    task = _require_task(session, task_id)
    return _task_detail(session, task)


@router.post("/api/tasks/{task_id}/close", response_model=TaskDetailResponse)
def close_task_api(task_id: str, session: Session = Depends(get_session)) -> TaskDetailResponse:
    task = _require_task(session, task_id)
    try:
        close_task_session(session, task)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    task = _require_task(session, task_id)
    return _task_detail(session, task)


@router.post("/api/tasks/{task_id}/archive", response_model=TaskDetailResponse)
def archive_task_api(task_id: str, session: Session = Depends(get_session)) -> TaskDetailResponse:
    task = _require_task(session, task_id)
    archive_task_session(session, task)
    session.commit()
    task = _require_task(session, task_id)
    return _task_detail(session, task)


def _require_task(session: Session, task_id: str) -> TaskSession:
    task = get_task_session(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


def _task_detail(session: Session, task: TaskSession) -> TaskDetailResponse:
    state = get_or_create_task_state(session, task.id, current_goal=task.user_goal)
    events = list_task_events(session, task.id)
    checkpoints = list_task_checkpoints(session, task.id)
    return task_detail_to_response(task, state, events, checkpoints)
