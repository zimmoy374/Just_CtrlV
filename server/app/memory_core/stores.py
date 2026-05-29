from __future__ import annotations

from typing import Any, Mapping

from sqlmodel import Session, select

from ..models import HandoffPack, KnowledgeItem, KnowledgePage, SourceItem, TaskCheckpoint, TaskEvent, TaskSession, TaskState
from ..retrieval.engine import RetrievalEngine
from .protocol import MemoryQuery, MemoryRef, MemorySlice


class SemanticKnowledgeStore:
    name = "semantic_knowledge"

    def __init__(self, retrieval_engine: RetrievalEngine | None = None) -> None:
        self.retrieval_engine = retrieval_engine or RetrievalEngine()

    def retrieve(self, session: Session, query: MemoryQuery) -> list[MemorySlice]:
        text = query.trimmed_text
        if not text:
            return []
        results = self.retrieval_engine.search(session, text, limit=max(0, query.limit))
        return [self._result_to_slice(result) for result in results]

    def get(self, session: Session, ref: MemoryRef) -> Any | None:
        if ref.kind == "item":
            return session.get(KnowledgeItem, ref.id)
        if ref.kind == "page":
            return session.get(KnowledgePage, ref.id)
        if ref.kind == "source":
            return session.get(SourceItem, ref.id)
        return None

    def export(self, session: Session) -> list[Mapping[str, Any]]:
        return []

    def rebuild_projection(self, session: Session) -> Mapping[str, Any]:
        return {"store": self.name, "status": "noop", "reason": "Semantic search projection is managed by RetrievalEngine."}

    def _result_to_slice(self, result) -> MemorySlice:
        knowledge_item = result.knowledge_item
        evidence_refs = [f"source:{knowledge_item.source_item_id}"] if knowledge_item.source_item_id else []
        return MemorySlice(
            store=self.name,
            kind="knowledge_item",
            ref=MemoryRef("item", knowledge_item.id),
            title=knowledge_item.title,
            summary=knowledge_item.summary,
            excerpt=result.excerpt,
            score=result.score,
            reason=result.reason,
            evidence_refs=evidence_refs,
            citation_ref=f"item:{knowledge_item.id}",
            visibility="workspace",
            metadata={
                "matchedFields": result.matched_fields,
                "source": result.source,
                "sourceRef": knowledge_item.source_ref,
                "knowledgeType": knowledge_item.knowledge_type,
                "updatedAt": knowledge_item.updated_at,
            },
        )


class TaskMemoryStore:
    name = "task_memory"

    def retrieve(self, session: Session, query: MemoryQuery) -> list[MemorySlice]:
        task_session_id = query.task_session_id or _task_id_from_scope(query.scope)
        if not task_session_id:
            return []
        task = session.get(TaskSession, task_session_id)
        if not task:
            return []

        slices: list[MemorySlice] = []
        state = session.get(TaskState, task.id)
        if state:
            slices.append(self._state_to_slice(task, state))

        remaining = max(0, query.limit - len(slices))
        if remaining:
            events = session.exec(
                select(TaskEvent)
                .where(TaskEvent.task_session_id == task.id)
                .order_by(TaskEvent.created_at.desc())
                .limit(remaining),
            ).all()
            slices.extend(self._event_to_slice(task, event) for event in events)

        return slices[: max(0, query.limit)]

    def get(self, session: Session, ref: MemoryRef) -> Any | None:
        if ref.kind == "task":
            return session.get(TaskSession, ref.id)
        if ref.kind == "task-event":
            return session.get(TaskEvent, ref.id)
        if ref.kind == "checkpoint":
            return session.get(TaskCheckpoint, ref.id)
        if ref.kind == "handoff":
            return session.get(HandoffPack, ref.id)
        return None

    def export(self, session: Session) -> list[Mapping[str, Any]]:
        return []

    def rebuild_projection(self, session: Session) -> Mapping[str, Any]:
        return {"store": self.name, "status": "noop", "reason": "Task memory has no Step 1 projection to rebuild."}

    def _state_to_slice(self, task: TaskSession, state: TaskState) -> MemorySlice:
        fields = {
            "done": state.done_json or [],
            "inProgress": state.in_progress_json or [],
            "nextSteps": state.next_steps_json or [],
            "openQuestions": state.open_questions_json or [],
            "constraints": state.constraints_json or [],
            "risks": state.risks_json or [],
            "decisions": state.decisions_json or [],
            "filesTouched": state.files_touched_json or [],
        }
        excerpt_parts = []
        if state.current_goal:
            excerpt_parts.append(f"Current goal: {state.current_goal}")
        for label, values in fields.items():
            if values:
                excerpt_parts.append(f"{label}: {'; '.join(values)}")

        return MemorySlice(
            store=self.name,
            kind="task_state",
            ref=MemoryRef("task", task.id),
            title=task.title,
            summary=state.current_goal or task.user_goal,
            excerpt="\n".join(excerpt_parts),
            score=100.0,
            reason="Task-scoped current state",
            scope=f"task:{task.id}",
            valid_at=state.updated_at,
            citation_ref=f"task:{task.id}",
            visibility="task",
            staleness=_task_staleness(task),
            metadata={
                "status": task.status,
                "confidence": state.confidence,
                **fields,
            },
        )

    def _event_to_slice(self, task: TaskSession, event: TaskEvent) -> MemorySlice:
        evidence_refs = [event.source_ref] if event.source_ref.startswith("source:") else []
        return MemorySlice(
            store=self.name,
            kind="task_event",
            ref=MemoryRef("task-event", event.id),
            title=f"{task.title} / {event.type}",
            summary=event.summary,
            excerpt=event.summary,
            score=70.0,
            reason="Recent task event",
            scope=f"task:{task.id}",
            valid_at=event.created_at,
            evidence_refs=evidence_refs,
            citation_ref=f"task-event:{event.id}",
            visibility="task",
            staleness=_task_staleness(task),
            metadata={
                "taskSessionId": task.id,
                "eventType": event.type,
                "payload": event.payload_json or {},
                "source": event.source,
                "sourceRef": event.source_ref,
            },
        )


def _task_id_from_scope(scope: str | None) -> str | None:
    if not scope:
        return None
    try:
        ref = MemoryRef.parse(scope)
    except ValueError:
        return None
    if ref.kind != "task":
        return None
    return ref.id


def _task_staleness(task: TaskSession) -> str:
    if task.status == "expired":
        return "expired"
    if task.status in {"closed", "archived"}:
        return "closed"
    return "fresh"
