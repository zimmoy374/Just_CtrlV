from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlmodel import Session

from ..knowledge_core.source_items import validate_choice
from ..models import HandoffPack, TaskSession, utc_now
from .checkpoints import list_task_checkpoints
from .events import append_task_event, list_task_events
from .state import get_or_create_task_state


HANDOFF_FORMATS = {"markdown", "json"}
STALE_AFTER = timedelta(hours=24)


def build_task_handoff(
    session: Session,
    task: TaskSession,
    *,
    handoff_format: str = "markdown",
    include_closed: bool = False,
) -> dict:
    _ensure_handoff_allowed(task, include_closed=include_closed)
    validate_choice(handoff_format, HANDOFF_FORMATS, "handoffFormat")

    state = get_or_create_task_state(session, task.id, current_goal=task.user_goal)
    checkpoints = list_task_checkpoints(session, task.id)
    events = list_task_events(session, task.id)
    freshness = _task_freshness(task)

    return {
        "taskId": task.id,
        "status": task.status,
        "freshness": freshness,
        "userGoal": task.user_goal,
        "currentGoal": state.current_goal,
        "done": state.done_json or [],
        "inProgress": state.in_progress_json or [],
        "nextSteps": state.next_steps_json or [],
        "openQuestions": state.open_questions_json or [],
        "constraints": state.constraints_json or [],
        "decisions": state.decisions_json or [],
        "risks": state.risks_json or [],
        "filesTouched": state.files_touched_json or [],
        "checkpointRefs": [
            {
                "ref": f"checkpoint:{checkpoint.id}",
                "id": checkpoint.id,
                "title": checkpoint.title,
                "createdAt": _iso(checkpoint.created_at),
            }
            for checkpoint in checkpoints
        ],
        "sourceRefs": [
            {
                "ref": f"task-event:{event.id}",
                "id": event.id,
                "eventType": event.type,
                "source": event.source,
                "sourceRef": event.source_ref,
                "createdAt": _iso(event.created_at),
            }
            for event in events
        ],
    }


def render_handoff_content(payload: dict, *, handoff_format: str) -> str:
    validate_choice(handoff_format, HANDOFF_FORMATS, "handoffFormat")
    if handoff_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return _render_markdown_handoff(payload)


def preview_handoff_pack(
    session: Session,
    task: TaskSession,
    *,
    handoff_format: str = "markdown",
    include_closed: bool = False,
) -> tuple[dict, str, dict]:
    payload = build_task_handoff(
        session,
        task,
        handoff_format=handoff_format,
        include_closed=include_closed,
    )
    content = render_handoff_content(payload, handoff_format=handoff_format)
    budget = _handoff_budget(payload, content)
    return payload, content, budget


def create_handoff_pack(
    session: Session,
    task: TaskSession,
    *,
    handoff_format: str = "markdown",
    include_closed: bool = False,
) -> tuple[HandoffPack, dict]:
    payload, content, budget = preview_handoff_pack(
        session,
        task,
        handoff_format=handoff_format,
        include_closed=include_closed,
    )
    handoff = HandoffPack(
        id=str(uuid4()),
        task_session_id=task.id,
        format=handoff_format,
        content=content,
        budget_json=budget,
    )
    session.add(handoff)
    session.flush()
    append_task_event(
        session,
        task,
        event_type="handoff_created",
        summary=f"创建 {handoff_format} handoff",
        payload={
            "handoffPackId": handoff.id,
            "format": handoff.format,
            "freshness": payload["freshness"],
        },
    )
    return handoff, payload


def _ensure_handoff_allowed(task: TaskSession, *, include_closed: bool) -> None:
    if task.status == "closed" and not include_closed:
        raise ValueError("closed 任务默认不返回 handoff，请显式传入 includeClosed=true")


def _task_freshness(task: TaskSession) -> dict:
    now = utc_now()
    expires_at = _as_utc(task.expires_at)
    reference_at = _as_utc(task.last_event_at or task.updated_at or task.created_at)

    state = "fresh"
    warning = ""
    if task.status == "expired" or (expires_at is not None and expires_at <= now):
        state = "expired"
        warning = "STALE WARNING: This handoff is for an expired task. Re-check current state before continuing."
    elif reference_at is not None and now - reference_at > STALE_AFTER:
        state = "stale"
        warning = "STALE WARNING: This handoff may be stale. Re-check current state before continuing."

    return {
        "state": state,
        "isStale": state in {"stale", "expired"},
        "warning": warning,
        "checkedAt": _iso(now),
        "referenceAt": _iso(reference_at),
        "expiresAt": _iso(expires_at),
    }


def _handoff_budget(payload: dict, content: str) -> dict:
    return {
        "contentChars": len(content),
        "doneCount": len(payload["done"]),
        "inProgressCount": len(payload["inProgress"]),
        "nextStepsCount": len(payload["nextSteps"]),
        "openQuestionsCount": len(payload["openQuestions"]),
        "checkpointRefCount": len(payload["checkpointRefs"]),
        "sourceRefCount": len(payload["sourceRefs"]),
    }


def _render_markdown_handoff(payload: dict) -> str:
    lines: list[str] = []
    warning = payload["freshness"].get("warning") or ""
    if warning:
        lines.extend([f"> {warning}", ""])

    lines.extend(
        [
            "# Task Handoff",
            "",
            f"- Task ID: {payload['taskId']}",
            f"- Status: {payload['status']}",
            f"- Freshness: {payload['freshness']['state']}",
            f"- User Goal: {payload['userGoal']}",
            f"- Current Goal: {payload['currentGoal']}",
            "",
        ],
    )
    _append_list_section(lines, "Done", payload["done"])
    _append_list_section(lines, "In Progress", payload["inProgress"])
    _append_list_section(lines, "Next Steps", payload["nextSteps"])
    _append_list_section(lines, "Open Questions", payload["openQuestions"])
    _append_list_section(lines, "Constraints", payload["constraints"])
    _append_list_section(lines, "Decisions", payload["decisions"])
    _append_list_section(lines, "Risks", payload["risks"])
    _append_list_section(lines, "Files Touched", payload["filesTouched"])
    _append_ref_section(lines, "Checkpoint Refs", payload["checkpointRefs"])
    _append_ref_section(lines, "Source Refs", payload["sourceRefs"])
    return "\n".join(lines).rstrip() + "\n"


def _append_list_section(lines: list[str], title: str, values: list[str]) -> None:
    lines.extend([f"## {title}", ""])
    if values:
        lines.extend(f"- {value}" for value in values)
    else:
        lines.append("- None")
    lines.append("")


def _append_ref_section(lines: list[str], title: str, refs: list[dict]) -> None:
    lines.extend([f"## {title}", ""])
    if refs:
        for ref in refs:
            label = ref.get("title") or ref.get("eventType") or ref["id"]
            lines.append(f"- `{ref['ref']}` {label}")
    else:
        lines.append("- None")
    lines.append("")


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value else None
