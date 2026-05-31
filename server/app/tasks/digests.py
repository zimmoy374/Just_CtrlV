from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from ..models import TaskDigest, TaskEvent, utc_now


DEFAULT_RECENT_EVENT_LIMIT = 5
MAX_DIGEST_ITEMS = 12
MAX_DIGEST_REFS = 50


def build_or_update_task_digest(
    session: Session,
    task_session_id: str,
    *,
    recent_event_limit: int = DEFAULT_RECENT_EVENT_LIMIT,
) -> tuple[TaskDigest | None, list[TaskEvent]]:
    events = list(
        session.exec(
            select(TaskEvent).where(TaskEvent.task_session_id == task_session_id).order_by(TaskEvent.created_at),
        ).all(),
    )
    keep_recent = max(1, recent_event_limit)
    if len(events) <= keep_recent:
        return None, events

    older_events = events[:-keep_recent]
    recent_events = events[-keep_recent:]
    existing = session.get(TaskDigest, task_session_id)
    event_from_id = older_events[0].id
    event_to_id = older_events[-1].id
    if existing and existing.event_from_id == event_from_id and existing.event_to_id == event_to_id and existing.event_count == len(older_events):
        return existing, recent_events

    payload = _digest_events(older_events)
    digest = existing or TaskDigest(task_session_id=task_session_id)
    digest.summary = payload["summary"]
    digest.done_json = payload["done"]
    digest.decisions_json = payload["decisions"]
    digest.open_questions_json = payload["openQuestions"]
    digest.risks_json = payload["risks"]
    digest.files_touched_json = payload["filesTouched"]
    digest.source_refs_json = payload["sourceRefs"]
    digest.event_from_id = event_from_id
    digest.event_to_id = event_to_id
    digest.event_count = len(older_events)
    digest.updated_at = utc_now()
    session.add(digest)
    session.flush()
    return digest, recent_events


def task_digest_payload(digest: TaskDigest | None) -> dict[str, Any] | None:
    if digest is None or digest.event_count <= 0:
        return None
    return {
        "summary": digest.summary,
        "done": digest.done_json or [],
        "decisions": digest.decisions_json or [],
        "openQuestions": digest.open_questions_json or [],
        "risks": digest.risks_json or [],
        "filesTouched": digest.files_touched_json or [],
        "sourceRefs": digest.source_refs_json or [],
        "eventFromId": digest.event_from_id,
        "eventToId": digest.event_to_id,
        "eventCount": digest.event_count,
        "updatedAt": digest.updated_at.isoformat(),
    }


def _digest_events(events: list[TaskEvent]) -> dict[str, Any]:
    done: list[str] = []
    decisions: list[str] = []
    open_questions: list[str] = []
    risks: list[str] = []
    files_touched: list[str] = []
    source_refs: list[str] = []

    for event in events:
        _append_unique(source_refs, f"task-event:{event.id}", MAX_DIGEST_REFS)
        if event.source_ref:
            _append_unique(source_refs, event.source_ref, MAX_DIGEST_REFS)
        payload = event.payload_json or {}
        _collect_files(files_touched, event, payload)
        if event.type in {"agent_action", "file_change", "test_result", "checkpoint_created"}:
            _append_unique(done, event.summary, MAX_DIGEST_ITEMS)
        elif event.type == "decision":
            _append_unique(decisions, event.summary, MAX_DIGEST_ITEMS)
        elif event.type == "question":
            _append_unique(open_questions, event.summary, MAX_DIGEST_ITEMS)
        elif event.type == "blocker":
            _append_unique(risks, event.summary, MAX_DIGEST_ITEMS)
        else:
            _append_payload_lists(payload, done, decisions, open_questions, risks, files_touched)

    summary_items = [event.summary for event in events[:5]]
    suffix = "；".join(summary_items)
    summary = f"已压缩 {len(events)} 条较早过程记录"
    if suffix:
        summary = f"{summary}：{suffix}"
    return {
        "summary": summary[:900],
        "done": done,
        "decisions": decisions,
        "openQuestions": open_questions,
        "risks": risks,
        "filesTouched": files_touched,
        "sourceRefs": source_refs,
    }


def _append_payload_lists(
    payload: dict[str, Any],
    done: list[str],
    decisions: list[str],
    open_questions: list[str],
    risks: list[str],
    files_touched: list[str],
) -> None:
    for key, target in [
        ("done", done),
        ("decisions", decisions),
        ("openQuestions", open_questions),
        ("risks", risks),
        ("filesTouched", files_touched),
    ]:
        for value in _payload_values(payload.get(key)):
            _append_unique(target, value, MAX_DIGEST_ITEMS)


def _collect_files(files_touched: list[str], event: TaskEvent, payload: dict[str, Any]) -> None:
    if event.source_ref and not event.source_ref.startswith(("source:", "task-event:", "checkpoint:", "task:")):
        _append_unique(files_touched, event.source_ref, MAX_DIGEST_ITEMS)
    for key in ["file", "files", "filesTouched", "sourceRef"]:
        for value in _payload_values(payload.get(key)):
            if not value.startswith(("source:", "task-event:", "checkpoint:", "task:")):
                _append_unique(files_touched, value, MAX_DIGEST_ITEMS)


def _payload_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    clean = str(value).strip()
    return [clean] if clean else []


def _append_unique(target: list[str], value: str, limit: int) -> None:
    clean = " ".join(str(value).split())
    if clean and clean not in target and len(target) < limit:
        target.append(clean)
