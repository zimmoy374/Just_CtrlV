from __future__ import annotations

from typing import Any, Mapping

from sqlmodel import Session, select

from ..models import (
    Entity,
    HandoffPack,
    KnowledgeItem,
    KnowledgePage,
    MemoryConflict,
    MemoryFact,
    MemoryProposal,
    MemoryRelation,
    SourceItem,
    TaskCheckpoint,
    TaskDigest,
    TaskEvent,
    TaskSession,
    TaskState,
    utc_now,
)
from ..retrieval.engine import RetrievalEngine
from ..indexing.sqlite_fts import rebuild_knowledge_search_index
from .context_helpers import direct_page_matches, merge_pages, page_item_refs, related_pages
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
        candidate_item_ids = [result.knowledge_item.id for result in results]
        slices = [self._result_to_slice(session, result) for result in results]
        pages = merge_pages(
            direct_page_matches(session, text),
            related_pages(session, candidate_item_ids),
        )
        slices.extend(self._page_to_slice(session, page, candidate_item_ids) for page in pages)
        return slices

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
        return {"store": self.name, **rebuild_knowledge_search_index(session)}

    def _result_to_slice(self, session: Session, result) -> MemorySlice:
        knowledge_item = result.knowledge_item
        source_item = session.get(SourceItem, knowledge_item.source_item_id) if knowledge_item.source_item_id else None
        source_metadata = source_item.metadata_json or {} if source_item else {}
        proposal = _proposal_for_knowledge_item(session, knowledge_item)
        source_ref = f"source:{knowledge_item.source_item_id}" if knowledge_item.source_item_id else ""
        evidence_refs = _dedupe_strings(
            [
                *(proposal.evidence_refs if proposal else []),
                *_string_list(source_metadata.get("evidenceRefs")),
                source_ref,
            ],
        )
        scope = (proposal.scope if proposal else source_metadata.get("scope")) or "workspace"
        target_store = source_metadata.get("targetStore") or _target_store_for_knowledge_type(knowledge_item.knowledge_type)
        capability_requirements = _string_list(source_metadata.get("capabilityRequirements"))
        return MemorySlice(
            store=self.name,
            kind="knowledge_item",
            ref=MemoryRef("item", knowledge_item.id),
            title=knowledge_item.title,
            summary=knowledge_item.summary,
            excerpt=result.excerpt,
            score=result.score,
            reason=result.reason,
            scope=scope,
            evidence_refs=evidence_refs,
            citation_ref=f"item:{knowledge_item.id}",
            decision_ref=proposal.decision_ref if proposal else None,
            visibility=str(source_metadata.get("visibility") or "workspace"),
            privacy_labels=_string_list(source_metadata.get("privacyLabels")),
            metadata={
                "matchedFields": result.matched_fields,
                "source": result.source,
                "sourceRef": knowledge_item.source_ref,
                "sourceItemId": knowledge_item.source_item_id,
                "knowledgeType": knowledge_item.knowledge_type,
                "targetStore": target_store,
                "capabilityRequirements": capability_requirements,
                "updatedAt": knowledge_item.updated_at,
            },
        )

    def _page_to_slice(self, session: Session, page: KnowledgePage, candidate_item_ids: list[str]) -> MemorySlice:
        proposal = session.exec(select(MemoryProposal).where(MemoryProposal.page_id == page.id)).first()
        item_refs = page_item_refs(session, page.id, set(candidate_item_ids))
        evidence_refs = _dedupe_strings([*(proposal.evidence_refs if proposal else []), *item_refs])
        return MemorySlice(
            store=self.name,
            kind="knowledge_page",
            ref=MemoryRef("page", page.id),
            title=page.title,
            summary=page.summary,
            excerpt=page.summary or page.body,
            score=90.0,
            reason="Matched knowledge page",
            scope=(proposal.scope if proposal else None) or "workspace",
            evidence_refs=evidence_refs,
            citation_ref=f"page:{page.id}",
            decision_ref=proposal.decision_ref if proposal else None,
            visibility="workspace",
            metadata={
                "status": page.status,
                "keywords": page.keywords or [],
                "itemRefs": item_refs,
                "updatedAt": page.updated_at,
                "targetStore": "semantic_knowledge",
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
        digest = session.get(TaskDigest, task.id)
        if digest and digest.event_count > 0:
            slices.append(self._digest_to_slice(task, digest))

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
        if ref.kind == "task-digest":
            return session.get(TaskDigest, ref.id)
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

    def _digest_to_slice(self, task: TaskSession, digest: TaskDigest) -> MemorySlice:
        fields = {
            "done": digest.done_json or [],
            "decisions": digest.decisions_json or [],
            "openQuestions": digest.open_questions_json or [],
            "risks": digest.risks_json or [],
            "filesTouched": digest.files_touched_json or [],
            "sourceRefs": digest.source_refs_json or [],
            "eventCount": digest.event_count,
            "eventFromId": digest.event_from_id,
            "eventToId": digest.event_to_id,
        }
        excerpt_parts = [digest.summary]
        for label in ["done", "decisions", "openQuestions", "risks", "filesTouched"]:
            values = fields[label]
            if values:
                excerpt_parts.append(f"{label}: {'; '.join(values)}")

        return MemorySlice(
            store=self.name,
            kind="task_digest",
            ref=MemoryRef("task-digest", task.id),
            title=f"{task.title} / 较早过程摘要",
            summary=digest.summary,
            excerpt="\n".join(excerpt_parts),
            score=90.0,
            reason="Compressed older task events",
            scope=f"task:{task.id}",
            valid_at=digest.updated_at,
            evidence_refs=[ref for ref in digest.source_refs_json or [] if ref.startswith("source:")],
            citation_ref=f"task-digest:{task.id}",
            visibility="task",
            staleness=_task_staleness(task),
            metadata=fields,
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


class ProfileTemporalGraphStore:
    name = "profile_temporal_graph"

    def retrieve(self, session: Session, query: MemoryQuery) -> list[MemorySlice]:
        text = query.trimmed_text
        if not text:
            return []
        entities = {entity.id: entity for entity in session.exec(select(Entity)).all()}
        open_conflicts = session.exec(select(MemoryConflict).where(MemoryConflict.status == "open")).all()
        all_facts = session.exec(select(MemoryFact)).all()
        facts_by_id = {fact.id: fact for fact in all_facts}
        now = utc_now()
        conflict_refs_by_fact_id: dict[str, list[str]] = {}
        conflict_relevant_active_fact_ids: set[str] = set()
        for conflict in open_conflicts:
            for fact_id in conflict.fact_ids or []:
                conflict_refs_by_fact_id.setdefault(fact_id, []).append(f"conflict:{conflict.id}")
            conflict_facts = [facts_by_id[fact_id] for fact_id in conflict.fact_ids or [] if fact_id in facts_by_id]
            if any(_profile_fact_matches(fact, entities, text) for fact in conflict_facts):
                for fact in conflict_facts:
                    if fact.status == "active" and (fact.invalid_at is None or fact.invalid_at > now):
                        conflict_relevant_active_fact_ids.add(fact.id)

        slices: list[MemorySlice] = []
        facts = [fact for fact in all_facts if fact.status == "active" and (fact.invalid_at is None or fact.invalid_at > now)]
        for fact in facts:
            if not _profile_fact_matches(fact, entities, text) and fact.id not in conflict_relevant_active_fact_ids:
                continue
            slices.append(_fact_to_slice(fact, entities, conflict_refs_by_fact_id.get(fact.id, [])))

        remaining = max(0, query.limit - len(slices))
        if remaining:
            relations = session.exec(
                select(MemoryRelation).where(
                    MemoryRelation.status == "active",
                    (MemoryRelation.invalid_at.is_(None)) | (MemoryRelation.invalid_at > now),
                ),
            ).all()
            for relation in relations:
                if not _profile_relation_matches(relation, entities, text):
                    continue
                slices.append(_relation_to_slice(relation, entities))
                if len(slices) >= query.limit:
                    break

        return sorted(slices, key=lambda item: item.score, reverse=True)[: max(0, query.limit)]

    def get(self, session: Session, ref: MemoryRef) -> Any | None:
        if ref.kind == "entity":
            return session.get(Entity, ref.id)
        if ref.kind == "fact":
            return session.get(MemoryFact, ref.id)
        if ref.kind == "relation":
            return session.get(MemoryRelation, ref.id)
        if ref.kind == "conflict":
            return session.get(MemoryConflict, ref.id)
        return None

    def export(self, session: Session) -> list[Mapping[str, Any]]:
        return []

    def rebuild_projection(self, session: Session) -> Mapping[str, Any]:
        return {"store": self.name, "status": "noop", "reason": "Profile graph reads directly from durable SQLModel tables."}


def _proposal_for_knowledge_item(session: Session, knowledge_item: KnowledgeItem) -> MemoryProposal | None:
    if knowledge_item.source_ref.startswith("proposal:"):
        proposal_id = knowledge_item.source_ref.removeprefix("proposal:")
        proposal = session.get(MemoryProposal, proposal_id)
        if proposal:
            return proposal
    return session.exec(select(MemoryProposal).where(MemoryProposal.knowledge_item_id == knowledge_item.id)).first()


def _target_store_for_knowledge_type(knowledge_type: str) -> str:
    if knowledge_type == "rule_preference":
        return "rule_preference"
    if knowledge_type == "procedure_lesson":
        return "procedure_lesson"
    return "semantic_knowledge"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _dedupe_strings(values: list[str]) -> list[str]:
    return [item for item in dict.fromkeys(values) if item]


def _profile_fact_matches(fact: MemoryFact, entities: dict[str, Entity], query: str) -> bool:
    values = [
        fact.predicate,
        fact.object_value,
        _entity_label(entities.get(fact.subject_entity_id)),
        _entity_label(entities.get(fact.object_entity_id or "")),
        *_entity_aliases(entities.get(fact.subject_entity_id)),
        *_entity_aliases(entities.get(fact.object_entity_id or "")),
    ]
    return _matches_any(query, values)


def _profile_relation_matches(relation: MemoryRelation, entities: dict[str, Entity], query: str) -> bool:
    values = [
        relation.relation_type,
        _entity_label(entities.get(relation.from_entity_id)),
        _entity_label(entities.get(relation.to_entity_id)),
        *_entity_aliases(entities.get(relation.from_entity_id)),
        *_entity_aliases(entities.get(relation.to_entity_id)),
    ]
    return _matches_any(query, values)


def _fact_to_slice(fact: MemoryFact, entities: dict[str, Entity], conflict_refs: list[str]) -> MemorySlice:
    subject = entities.get(fact.subject_entity_id)
    object_entity = entities.get(fact.object_entity_id or "")
    object_label = _entity_label(object_entity) or fact.object_value
    title = f"{_entity_label(subject)} {fact.predicate} {object_label}".strip()
    return MemorySlice(
        store="profile_temporal_graph",
        kind="profile_fact",
        ref=MemoryRef("fact", fact.id),
        title=title,
        summary=title,
        excerpt=title,
        score=94.0,
        reason="Matched active profile fact",
        scope=fact.scope,
        valid_at=fact.valid_at,
        invalid_at=fact.invalid_at,
        evidence_refs=fact.evidence_refs or [],
        citation_ref=f"fact:{fact.id}",
        decision_ref=fact.decision_ref,
        visibility="workspace",
        privacy_labels=["profile"],
        conflict_refs=conflict_refs,
        metadata={
            "subjectEntityRef": f"entity:{fact.subject_entity_id}",
            "subjectName": _entity_label(subject),
            "predicate": fact.predicate,
            "objectValue": fact.object_value,
            "objectEntityRef": f"entity:{fact.object_entity_id}" if fact.object_entity_id else None,
            "objectName": object_label,
            "confidence": fact.confidence,
            "status": fact.status,
            "sourceProposalRef": f"proposal:{fact.source_proposal_id}" if fact.source_proposal_id else None,
        },
    )


def _relation_to_slice(relation: MemoryRelation, entities: dict[str, Entity]) -> MemorySlice:
    from_entity = entities.get(relation.from_entity_id)
    to_entity = entities.get(relation.to_entity_id)
    title = f"{_entity_label(from_entity)} {relation.relation_type} {_entity_label(to_entity)}".strip()
    return MemorySlice(
        store="profile_temporal_graph",
        kind="profile_relation",
        ref=MemoryRef("relation", relation.id),
        title=title,
        summary=title,
        excerpt=title,
        score=88.0,
        reason="Matched active profile relation",
        scope=relation.scope,
        valid_at=relation.valid_at,
        invalid_at=relation.invalid_at,
        evidence_refs=relation.evidence_refs or [],
        citation_ref=f"relation:{relation.id}",
        decision_ref=relation.decision_ref,
        visibility="workspace",
        privacy_labels=["profile"],
        metadata={
            "fromEntityRef": f"entity:{relation.from_entity_id}",
            "fromName": _entity_label(from_entity),
            "relationType": relation.relation_type,
            "toEntityRef": f"entity:{relation.to_entity_id}",
            "toName": _entity_label(to_entity),
            "confidence": relation.confidence,
            "status": relation.status,
            "sourceProposalRef": f"proposal:{relation.source_proposal_id}" if relation.source_proposal_id else None,
        },
    )


def _matches_any(query: str, values: list[str]) -> bool:
    normalized_query = query.casefold().strip()
    if not normalized_query:
        return False
    return any(normalized_query in str(value or "").casefold() for value in values)


def _entity_label(entity: Entity | None) -> str:
    return entity.name if entity else ""


def _entity_aliases(entity: Entity | None) -> list[str]:
    return entity.aliases or [] if entity else []
