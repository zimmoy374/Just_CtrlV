from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_
from sqlmodel import Session, select

from ..database import get_session
from ..knowledge_core.source_items import validate_choice
from ..memory_core.decisions import record_memory_decision, record_provenance_event
from ..memory_core.protocol import MEMORY_TARGET_STORES
from ..memory_kernel.proposals import (
    MEMORY_PROPOSAL_TYPES,
    accept_memory_proposal,
    create_memory_proposal,
    dismiss_memory_proposal,
    get_memory_proposal,
    list_memory_proposals,
)
from ..models import (
    Entity,
    KnowledgeItem,
    KnowledgePage,
    KnowledgePageItemLink,
    MemoryConflict,
    MemoryDecision,
    MemoryFact,
    MemoryProposal,
    ProvenanceEvent,
    SourceItem,
    utc_now,
)
from ..presenters import memory_proposal_to_response
from ..schemas import MemoryProposalResponse


router = APIRouter(prefix="/api/review", tags=["review-workbench"])


class ReviewDecision(BaseModel):
    ref: str
    decision_type: str = Field(alias="decisionType")
    target_ref: str = Field(alias="targetRef")
    actor: str
    reason: str
    policy: str
    evidence_refs: list[str] = Field(alias="evidenceRefs")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class ReviewProvenance(BaseModel):
    ref: str
    type: str
    from_ref: Optional[str] = Field(default=None, alias="fromRef")
    to_ref: Optional[str] = Field(default=None, alias="toRef")
    actor: str
    reason: str
    evidence_refs: list[str] = Field(alias="evidenceRefs")
    payload: dict
    occurred_at: datetime = Field(alias="occurredAt")

    model_config = ConfigDict(populate_by_name=True)


class ReviewMemoryRecord(BaseModel):
    ref: str
    id: str
    title: str
    summary: str
    status: str
    target_store: str = Field(alias="targetStore")
    scope: str
    visibility: str
    privacy_labels: list[str] = Field(alias="privacyLabels")
    evidence_refs: list[str] = Field(alias="evidenceRefs")
    decision_ref: Optional[str] = Field(default=None, alias="decisionRef")
    source_ref: Optional[str] = Field(default=None, alias="sourceRef")
    task_session_id: Optional[str] = Field(default=None, alias="taskSessionId")
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")
    decision_history: list[ReviewDecision] = Field(default_factory=list, alias="decisionHistory")
    provenance_history: list[ReviewProvenance] = Field(default_factory=list, alias="provenanceHistory")
    metadata: dict = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)


class ReviewProfileFact(BaseModel):
    ref: str
    id: str
    title: str
    subject: str
    predicate: str
    object_value: str = Field(alias="objectValue")
    status: str
    scope: str
    confidence: Optional[float] = None
    valid_at: datetime = Field(alias="validAt")
    invalid_at: Optional[datetime] = Field(default=None, alias="invalidAt")
    superseded_by: Optional[str] = Field(default=None, alias="supersededBy")
    evidence_refs: list[str] = Field(alias="evidenceRefs")
    decision_ref: Optional[str] = Field(default=None, alias="decisionRef")
    conflict_refs: list[str] = Field(default_factory=list, alias="conflictRefs")
    decision_history: list[ReviewDecision] = Field(default_factory=list, alias="decisionHistory")
    provenance_history: list[ReviewProvenance] = Field(default_factory=list, alias="provenanceHistory")

    model_config = ConfigDict(populate_by_name=True)


class ReviewConflict(BaseModel):
    ref: str
    id: str
    type: str
    status: str
    reason: str
    resolution: str
    scope: str
    fact_refs: list[str] = Field(alias="factRefs")
    relation_refs: list[str] = Field(alias="relationRefs")
    decision_ref: Optional[str] = Field(default=None, alias="decisionRef")
    created_at: datetime = Field(alias="createdAt")
    resolved_at: Optional[datetime] = Field(default=None, alias="resolvedAt")
    decision_history: list[ReviewDecision] = Field(default_factory=list, alias="decisionHistory")
    provenance_history: list[ReviewProvenance] = Field(default_factory=list, alias="provenanceHistory")

    model_config = ConfigDict(populate_by_name=True)


class ReviewSource(BaseModel):
    ref: str
    id: str
    title: str
    kind: str
    source: str
    status: str
    visibility: str
    privacy_labels: list[str] = Field(alias="privacyLabels")
    task_session_id: Optional[str] = Field(default=None, alias="taskSessionId")
    content_chars: int = Field(alias="contentChars")
    excerpt: str
    updated_at: datetime = Field(alias="updatedAt")
    decision_history: list[ReviewDecision] = Field(default_factory=list, alias="decisionHistory")
    provenance_history: list[ReviewProvenance] = Field(default_factory=list, alias="provenanceHistory")

    model_config = ConfigDict(populate_by_name=True)


class ReviewWorkbenchResponse(BaseModel):
    proposals: list[MemoryProposalResponse]
    profile_facts: list[ReviewProfileFact] = Field(alias="profileFacts")
    conflicts: list[ReviewConflict]
    rules: list[ReviewMemoryRecord]
    procedures: list[ReviewMemoryRecord]
    pages: list[ReviewMemoryRecord]
    sources: list[ReviewSource]
    counts: dict[str, int]

    model_config = ConfigDict(populate_by_name=True)


class ReviewProposalPatch(BaseModel):
    type: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    target_store: Optional[str] = Field(default=None, alias="targetStore")
    structured_payload: Optional[dict] = Field(default=None, alias="structuredPayload")
    scope: Optional[str] = None
    evidence_refs: Optional[list[str]] = Field(default=None, alias="evidenceRefs")
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    review_note: Optional[str] = Field(default=None, alias="reviewNote")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SupersedeFactPayload(BaseModel):
    object_value: str = Field(alias="objectValue", min_length=1)
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    review_note: str = Field(default="", alias="reviewNote")
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class InvalidateFactPayload(BaseModel):
    reason: str = Field(default="Invalidated from Review Workbench")

    model_config = ConfigDict(extra="forbid")


class ResolveConflictPayload(BaseModel):
    resolution: str = Field(min_length=1)
    winning_fact_id: Optional[str] = Field(default=None, alias="winningFactId")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SourcePolicyPatch(BaseModel):
    visibility: Optional[str] = None
    privacy_labels: Optional[list[str]] = Field(default=None, alias="privacyLabels")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class SourcePurgePayload(BaseModel):
    reason: str = Field(default="Purged from Review Workbench")

    model_config = ConfigDict(extra="forbid")


@router.get("/workbench", response_model=ReviewWorkbenchResponse)
def get_review_workbench_api(
    proposal_status: str = Query(default="all", alias="proposalStatus"),
    limit: int = Query(default=80, ge=1, le=200),
    session: Session = Depends(get_session),
) -> ReviewWorkbenchResponse:
    proposals = list_memory_proposals(session, status=proposal_status)
    facts = _profile_facts(session, limit=limit)
    conflicts = _conflicts(session, limit=limit)
    rules = _knowledge_records(session, target_store="rule_preference", limit=limit)
    procedures = _knowledge_records(session, target_store="procedure_lesson", limit=limit)
    pages = _page_records(session, limit=limit)
    sources = _source_records(session, limit=limit)
    return ReviewWorkbenchResponse(
        proposals=[memory_proposal_to_response(proposal) for proposal in proposals],
        profileFacts=facts,
        conflicts=conflicts,
        rules=rules,
        procedures=procedures,
        pages=pages,
        sources=sources,
        counts={
            "proposals": len(proposals),
            "pendingProposals": sum(1 for proposal in proposals if proposal.status == "pending"),
            "profileFacts": len(facts),
            "openConflicts": sum(1 for conflict in conflicts if conflict.status == "open"),
            "rules": len(rules),
            "procedures": len(procedures),
            "pages": len(pages),
            "sources": len(sources),
        },
    )


@router.patch("/proposals/{proposal_id}", response_model=MemoryProposalResponse)
def update_review_proposal_api(
    proposal_id: str,
    payload: ReviewProposalPatch,
    session: Session = Depends(get_session),
) -> MemoryProposalResponse:
    proposal = _require_proposal(session, proposal_id)
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="只能编辑 pending memory proposal")

    if payload.type is not None:
        validate_choice(payload.type, MEMORY_PROPOSAL_TYPES, "memoryProposalType")
        proposal.type = payload.type
    if payload.target_store is not None:
        validate_choice(payload.target_store, MEMORY_TARGET_STORES, "memoryTargetStore")
        proposal.target_store = payload.target_store
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="MemoryProposal title 不能为空")
        proposal.title = title
    if payload.body is not None:
        proposal.body = payload.body.strip()
    if payload.structured_payload is not None:
        proposal.structured_payload_json = payload.structured_payload
    if payload.scope is not None:
        proposal.scope = payload.scope.strip() or "workspace"
    if payload.evidence_refs is not None:
        proposal.evidence_refs = _dedupe_strings(payload.evidence_refs)
    if payload.confidence is not None:
        proposal.confidence = payload.confidence
    if payload.review_note is not None:
        proposal.review_note = payload.review_note.strip()

    decision = record_memory_decision(
        session,
        decision_type="proposal_review_updated",
        target_ref=f"proposal:{proposal.id}",
        reason=proposal.review_note or "Updated proposal in Review Workbench",
        evidence_refs=proposal.evidence_refs or [],
        confidence=proposal.confidence,
        scope=proposal.scope,
        metadata={"proposalType": proposal.type, "targetStore": proposal.target_store},
        actor="user",
        policy="review_workbench",
    )
    proposal.decision_ref = f"decision:{decision.id}"
    session.add(proposal)
    record_provenance_event(
        session,
        event_type="proposal_review_updated",
        from_ref=f"proposal:{proposal.id}",
        to_ref=proposal.decision_ref,
        reason=proposal.review_note or "Updated proposal in Review Workbench",
        evidence_refs=proposal.evidence_refs or [],
        payload={"targetStore": proposal.target_store, "proposalType": proposal.type},
        actor="user",
    )
    session.commit()
    session.refresh(proposal)
    return memory_proposal_to_response(proposal)


@router.post("/proposals/{proposal_id}/accept", response_model=MemoryProposalResponse)
def accept_review_proposal_api(proposal_id: str, session: Session = Depends(get_session)) -> MemoryProposalResponse:
    proposal = _require_proposal(session, proposal_id)
    try:
        accept_memory_proposal(session, proposal)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(proposal)
    return memory_proposal_to_response(proposal)


@router.post("/proposals/{proposal_id}/dismiss", response_model=MemoryProposalResponse)
def dismiss_review_proposal_api(proposal_id: str, session: Session = Depends(get_session)) -> MemoryProposalResponse:
    proposal = _require_proposal(session, proposal_id)
    try:
        dismiss_memory_proposal(session, proposal)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(proposal)
    return memory_proposal_to_response(proposal)


@router.post("/profile-facts/{fact_id}/supersede", response_model=MemoryProposalResponse)
def supersede_profile_fact_api(
    fact_id: str,
    payload: SupersedeFactPayload,
    session: Session = Depends(get_session),
) -> MemoryProposalResponse:
    fact = _require_fact(session, fact_id)
    entities = _entities(session)
    subject = entities.get(fact.subject_entity_id)
    evidence_refs = _dedupe_strings(payload.evidence_refs or fact.evidence_refs or [])
    proposal = create_memory_proposal(
        session,
        proposal_type="fact_supersession",
        title=f"Supersede {fact.predicate}",
        body=f"{_entity_label(subject)} {fact.predicate} {payload.object_value}".strip(),
        target_store="profile_temporal_graph",
        structured_payload={
            "supersedesFactRef": f"fact:{fact.id}",
            "newFact": {
                "subject": {"type": subject.type if subject else "user", "name": _entity_label(subject) or "User"},
                "predicate": fact.predicate,
                "objectValue": payload.object_value.strip(),
            },
        },
        scope=fact.scope,
        confidence=payload.confidence if payload.confidence is not None else fact.confidence,
        review_note=payload.review_note or f"Supersede fact:{fact.id} from Review Workbench",
        evidence_refs=evidence_refs,
    )
    record_provenance_event(
        session,
        event_type="fact_supersession_proposed",
        from_ref=f"fact:{fact.id}",
        to_ref=f"proposal:{proposal.id}",
        reason=proposal.review_note,
        evidence_refs=evidence_refs,
        payload={"oldFactRef": f"fact:{fact.id}"},
        actor="user",
    )
    session.commit()
    session.refresh(proposal)
    return memory_proposal_to_response(proposal)


@router.post("/profile-facts/{fact_id}/invalidate", response_model=ReviewProfileFact)
def invalidate_profile_fact_api(
    fact_id: str,
    payload: InvalidateFactPayload,
    session: Session = Depends(get_session),
) -> ReviewProfileFact:
    fact = _require_fact(session, fact_id)
    now = utc_now()
    fact.status = "invalidated"
    fact.invalid_at = now
    fact.updated_at = now
    decision = record_memory_decision(
        session,
        decision_type="fact_invalidated",
        target_ref=f"fact:{fact.id}",
        reason=payload.reason.strip() or "Invalidated from Review Workbench",
        evidence_refs=fact.evidence_refs or [],
        confidence=fact.confidence,
        scope=fact.scope,
        metadata={"factRef": f"fact:{fact.id}"},
        actor="user",
        policy="review_workbench",
    )
    fact.decision_ref = f"decision:{decision.id}"
    session.add(fact)
    record_provenance_event(
        session,
        event_type="fact_invalidated",
        from_ref=f"fact:{fact.id}",
        to_ref=fact.decision_ref,
        reason=payload.reason.strip() or "Invalidated from Review Workbench",
        evidence_refs=fact.evidence_refs or [],
        payload={"status": fact.status},
        actor="user",
    )
    session.commit()
    session.refresh(fact)
    return _profile_fact_response(session, fact, _entities(session), _conflict_refs_by_fact(session))


@router.post("/conflicts/{conflict_id}/resolve", response_model=ReviewConflict)
def resolve_conflict_api(
    conflict_id: str,
    payload: ResolveConflictPayload,
    session: Session = Depends(get_session),
) -> ReviewConflict:
    conflict = session.get(MemoryConflict, conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail="MemoryConflict 不存在")
    if payload.winning_fact_id and payload.winning_fact_id not in (conflict.fact_ids or []):
        raise HTTPException(status_code=400, detail="winningFactId 不属于该 conflict")

    conflict.status = "resolved"
    conflict.resolution = payload.resolution.strip()
    conflict.resolved_at = utc_now()
    decision = record_memory_decision(
        session,
        decision_type="conflict_resolved",
        target_ref=f"conflict:{conflict.id}",
        reason=conflict.resolution,
        evidence_refs=[f"fact:{fact_id}" for fact_id in conflict.fact_ids or []],
        scope=conflict.scope,
        metadata={"winningFactRef": f"fact:{payload.winning_fact_id}" if payload.winning_fact_id else None},
        actor="user",
        policy="review_workbench",
    )
    conflict.decision_ref = f"decision:{decision.id}"
    session.add(conflict)
    if payload.winning_fact_id:
        now = utc_now()
        for fact_id in conflict.fact_ids or []:
            if fact_id == payload.winning_fact_id:
                continue
            fact = session.get(MemoryFact, fact_id)
            if not fact or fact.status in {"superseded", "invalidated"}:
                continue
            fact.status = "invalidated"
            fact.invalid_at = now
            fact.updated_at = now
            session.add(fact)
            record_provenance_event(
                session,
                event_type="conflict_resolution_invalidated_fact",
                from_ref=f"conflict:{conflict.id}",
                to_ref=f"fact:{fact.id}",
                reason=conflict.resolution,
                evidence_refs=fact.evidence_refs or [],
                payload={"winningFactRef": f"fact:{payload.winning_fact_id}", "decisionRef": conflict.decision_ref},
                actor="user",
            )
    record_provenance_event(
        session,
        event_type="conflict_resolved",
        from_ref=f"conflict:{conflict.id}",
        to_ref=conflict.decision_ref,
        reason=conflict.resolution,
        evidence_refs=[f"fact:{fact_id}" for fact_id in conflict.fact_ids or []],
        payload={"winningFactRef": f"fact:{payload.winning_fact_id}" if payload.winning_fact_id else None},
        actor="user",
    )
    session.commit()
    session.refresh(conflict)
    return _conflict_response(session, conflict)


@router.patch("/sources/{source_id}/policy", response_model=ReviewSource)
def update_source_policy_api(
    source_id: str,
    payload: SourcePolicyPatch,
    session: Session = Depends(get_session),
) -> ReviewSource:
    source = _require_source(session, source_id)
    metadata = dict(source.metadata_json or {})
    if payload.visibility is not None:
        validate_choice(payload.visibility, {"workspace", "task", "profile", "private"}, "sourceVisibility")
        metadata["visibility"] = payload.visibility
    if payload.privacy_labels is not None:
        metadata["privacyLabels"] = _dedupe_strings(payload.privacy_labels)
    source.metadata_json = metadata
    source.updated_at = utc_now()
    session.add(source)
    decision = record_memory_decision(
        session,
        decision_type="source_policy_updated",
        target_ref=f"source:{source.id}",
        reason="Updated source visibility/privacy labels from Review Workbench",
        evidence_refs=[f"source:{source.id}"],
        scope=metadata.get("scope") or "workspace",
        metadata={"visibility": metadata.get("visibility"), "privacyLabels": metadata.get("privacyLabels") or []},
        actor="user",
        policy="review_workbench",
    )
    record_provenance_event(
        session,
        event_type="source_policy_updated",
        from_ref=f"source:{source.id}",
        to_ref=f"decision:{decision.id}",
        reason="Updated source visibility/privacy labels from Review Workbench",
        evidence_refs=[f"source:{source.id}"],
        payload={"visibility": metadata.get("visibility"), "privacyLabels": metadata.get("privacyLabels") or []},
        actor="user",
    )
    session.commit()
    session.refresh(source)
    return _source_response(session, source)


@router.post("/sources/{source_id}/purge", response_model=ReviewSource)
def purge_source_api(
    source_id: str,
    payload: SourcePurgePayload,
    session: Session = Depends(get_session),
) -> ReviewSource:
    source = _require_source(session, source_id)
    metadata = dict(source.metadata_json or {})
    metadata["purgedAt"] = utc_now().isoformat()
    metadata["purgeReason"] = payload.reason.strip() or "Purged from Review Workbench"
    metadata["visibility"] = "private"
    metadata["privacyLabels"] = _dedupe_strings([*(metadata.get("privacyLabels") or []), "purged"])
    source.content_text = ""
    source.content_html = ""
    source.status = "purged"
    source.metadata_json = metadata
    source.updated_at = utc_now()
    session.add(source)
    decision = record_memory_decision(
        session,
        decision_type="source_purged",
        target_ref=f"source:{source.id}",
        reason=metadata["purgeReason"],
        evidence_refs=[f"source:{source.id}"],
        scope=metadata.get("scope") or "workspace",
        metadata={"visibility": "private", "privacyLabels": metadata["privacyLabels"]},
        actor="user",
        policy="review_workbench",
    )
    record_provenance_event(
        session,
        event_type="source_purged",
        from_ref=f"source:{source.id}",
        to_ref=f"decision:{decision.id}",
        reason=metadata["purgeReason"],
        evidence_refs=[f"source:{source.id}"],
        payload={"status": source.status},
        actor="user",
    )
    session.commit()
    session.refresh(source)
    return _source_response(session, source)


def _profile_facts(session: Session, *, limit: int) -> list[ReviewProfileFact]:
    entities = _entities(session)
    conflict_refs = _conflict_refs_by_fact(session)
    facts = session.exec(select(MemoryFact).order_by(MemoryFact.updated_at.desc()).limit(limit)).all()
    return [_profile_fact_response(session, fact, entities, conflict_refs) for fact in facts]


def _conflicts(session: Session, *, limit: int) -> list[ReviewConflict]:
    conflicts = session.exec(select(MemoryConflict).order_by(MemoryConflict.created_at.desc()).limit(limit)).all()
    return [_conflict_response(session, conflict) for conflict in conflicts]


def _knowledge_records(session: Session, *, target_store: str, limit: int) -> list[ReviewMemoryRecord]:
    items = session.exec(
        select(KnowledgeItem)
        .where(KnowledgeItem.knowledge_type == target_store, KnowledgeItem.status != "archived")
        .order_by(KnowledgeItem.updated_at.desc())
        .limit(limit),
    ).all()
    return [_knowledge_record_response(session, item, target_store=target_store) for item in items]


def _page_records(session: Session, *, limit: int) -> list[ReviewMemoryRecord]:
    pages = session.exec(select(KnowledgePage).where(KnowledgePage.status != "archived").order_by(KnowledgePage.updated_at.desc()).limit(limit)).all()
    links = session.exec(select(KnowledgePageItemLink)).all()
    item_counts: dict[str, int] = {}
    for link in links:
        item_counts[link.page_id] = item_counts.get(link.page_id, 0) + 1
    records: list[ReviewMemoryRecord] = []
    for page in pages:
        proposal = session.exec(select(MemoryProposal).where(MemoryProposal.page_id == page.id)).first()
        ref = f"page:{page.id}"
        records.append(
            ReviewMemoryRecord(
                ref=ref,
                id=page.id,
                title=page.title,
                summary=page.summary or page.body[:180],
                status=page.status,
                targetStore="semantic_knowledge",
                scope=proposal.scope if proposal else "workspace",
                visibility="workspace",
                privacyLabels=[],
                evidenceRefs=proposal.evidence_refs if proposal else [],
                decisionRef=proposal.decision_ref if proposal else None,
                sourceRef=None,
                taskSessionId=proposal.task_session_id if proposal else None,
                updatedAt=page.updated_at,
                decisionHistory=_decision_history(session, _record_refs(ref, proposal)),
                provenanceHistory=_provenance_history(session, _record_refs(ref, proposal)),
                metadata={"keywords": page.keywords or [], "itemCount": item_counts.get(page.id, 0)},
            ),
        )
    return records


def _source_records(session: Session, *, limit: int) -> list[ReviewSource]:
    sources = session.exec(select(SourceItem).order_by(SourceItem.updated_at.desc()).limit(limit)).all()
    return [_source_response(session, source) for source in sources]


def _knowledge_record_response(session: Session, item: KnowledgeItem, *, target_store: str) -> ReviewMemoryRecord:
    source = session.get(SourceItem, item.source_item_id) if item.source_item_id else None
    metadata = source.metadata_json or {} if source else {}
    proposal = _proposal_for_item(session, item)
    source_ref = f"source:{source.id}" if source else None
    ref = f"item:{item.id}"
    evidence_refs = _dedupe_strings([*(proposal.evidence_refs if proposal else []), *list(metadata.get("evidenceRefs") or []), source_ref or ""])
    return ReviewMemoryRecord(
        ref=ref,
        id=item.id,
        title=item.title,
        summary=item.summary or item.content[:180],
        status=item.status,
        targetStore=target_store,
        scope=(proposal.scope if proposal else metadata.get("scope")) or "workspace",
        visibility=str(metadata.get("visibility") or "workspace"),
        privacyLabels=[str(label) for label in metadata.get("privacyLabels") or [] if label],
        evidenceRefs=evidence_refs,
        decisionRef=proposal.decision_ref if proposal else None,
        sourceRef=source_ref,
        taskSessionId=proposal.task_session_id if proposal else metadata.get("taskSessionId"),
        updatedAt=item.updated_at,
        decisionHistory=_decision_history(session, _record_refs(ref, proposal, source_ref)),
        provenanceHistory=_provenance_history(session, _record_refs(ref, proposal, source_ref)),
        metadata={"keywords": item.keywords or [], "knowledgeType": item.knowledge_type, "sourceRef": item.source_ref},
    )


def _profile_fact_response(
    session: Session,
    fact: MemoryFact,
    entities: dict[str, Entity],
    conflict_refs_by_fact: dict[str, list[str]],
) -> ReviewProfileFact:
    subject = entities.get(fact.subject_entity_id)
    object_entity = entities.get(fact.object_entity_id or "")
    object_value = _entity_label(object_entity) or fact.object_value
    title = f"{_entity_label(subject)} {fact.predicate} {object_value}".strip()
    ref = f"fact:{fact.id}"
    return ReviewProfileFact(
        ref=ref,
        id=fact.id,
        title=title,
        subject=_entity_label(subject),
        predicate=fact.predicate,
        objectValue=object_value,
        status=fact.status,
        scope=fact.scope,
        confidence=fact.confidence,
        validAt=fact.valid_at,
        invalidAt=fact.invalid_at,
        supersededBy=f"fact:{fact.superseded_by}" if fact.superseded_by else None,
        evidenceRefs=fact.evidence_refs or [],
        decisionRef=fact.decision_ref,
        conflictRefs=conflict_refs_by_fact.get(fact.id, []),
        decisionHistory=_decision_history(session, [ref, *(fact.evidence_refs or [])]),
        provenanceHistory=_provenance_history(session, [ref, *(fact.evidence_refs or [])]),
    )


def _conflict_response(session: Session, conflict: MemoryConflict) -> ReviewConflict:
    ref = f"conflict:{conflict.id}"
    refs = [ref, *[f"fact:{fact_id}" for fact_id in conflict.fact_ids or []]]
    return ReviewConflict(
        ref=ref,
        id=conflict.id,
        type=conflict.conflict_type,
        status=conflict.status,
        reason=conflict.reason,
        resolution=conflict.resolution,
        scope=conflict.scope,
        factRefs=[f"fact:{fact_id}" for fact_id in conflict.fact_ids or []],
        relationRefs=[f"relation:{relation_id}" for relation_id in conflict.relation_ids or []],
        decisionRef=conflict.decision_ref,
        createdAt=conflict.created_at,
        resolvedAt=conflict.resolved_at,
        decisionHistory=_decision_history(session, refs),
        provenanceHistory=_provenance_history(session, refs),
    )


def _source_response(session: Session, source: SourceItem) -> ReviewSource:
    metadata = source.metadata_json or {}
    ref = f"source:{source.id}"
    return ReviewSource(
        ref=ref,
        id=source.id,
        title=source.title,
        kind=source.kind,
        source=source.source,
        status=source.status,
        visibility=str(metadata.get("visibility") or "workspace"),
        privacyLabels=[str(label) for label in metadata.get("privacyLabels") or [] if label],
        taskSessionId=metadata.get("taskSessionId"),
        contentChars=len(source.content_text or ""),
        excerpt=(source.content_text or "")[:220],
        updatedAt=source.updated_at,
        decisionHistory=_decision_history(session, [ref]),
        provenanceHistory=_provenance_history(session, [ref]),
    )


def _decision_history(session: Session, refs: list[str]) -> list[ReviewDecision]:
    clean_refs = _dedupe_strings(refs)
    if not clean_refs:
        return []
    decisions = session.exec(
        select(MemoryDecision).where(MemoryDecision.target_ref.in_(clean_refs)).order_by(MemoryDecision.created_at.desc()),
    ).all()
    return [
        ReviewDecision(
            ref=f"decision:{decision.id}",
            decisionType=decision.decision_type,
            targetRef=decision.target_ref,
            actor=decision.actor,
            reason=decision.reason,
            policy=decision.policy,
            evidenceRefs=decision.evidence_refs or [],
            createdAt=decision.created_at,
        )
        for decision in decisions
    ]


def _provenance_history(session: Session, refs: list[str]) -> list[ReviewProvenance]:
    clean_refs = _dedupe_strings(refs)
    if not clean_refs:
        return []
    events = session.exec(
        select(ProvenanceEvent)
        .where(or_(ProvenanceEvent.from_ref.in_(clean_refs), ProvenanceEvent.to_ref.in_(clean_refs)))
        .order_by(ProvenanceEvent.occurred_at.desc()),
    ).all()
    return [
        ReviewProvenance(
            ref=f"provenance:{event.id}",
            type=event.event_type,
            fromRef=event.from_ref,
            toRef=event.to_ref,
            actor=event.actor,
            reason=event.reason,
            evidenceRefs=event.evidence_refs or [],
            payload=event.payload_json or {},
            occurredAt=event.occurred_at,
        )
        for event in events
    ]


def _proposal_for_item(session: Session, item: KnowledgeItem) -> MemoryProposal | None:
    if item.source_ref.startswith("proposal:"):
        proposal = session.get(MemoryProposal, item.source_ref.removeprefix("proposal:"))
        if proposal:
            return proposal
    return session.exec(select(MemoryProposal).where(MemoryProposal.knowledge_item_id == item.id)).first()


def _record_refs(ref: str, proposal: MemoryProposal | None, source_ref: str | None = None) -> list[str]:
    refs = [ref, source_ref or ""]
    if proposal:
        refs.extend([f"proposal:{proposal.id}", proposal.decision_ref or ""])
        refs.extend(proposal.evidence_refs or [])
    return _dedupe_strings(refs)


def _conflict_refs_by_fact(session: Session) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    conflicts = session.exec(select(MemoryConflict)).all()
    for conflict in conflicts:
        for fact_id in conflict.fact_ids or []:
            mapping.setdefault(fact_id, []).append(f"conflict:{conflict.id}")
    return mapping


def _entities(session: Session) -> dict[str, Entity]:
    return {entity.id: entity for entity in session.exec(select(Entity)).all()}


def _entity_label(entity: Entity | None) -> str:
    return entity.name if entity else ""


def _require_proposal(session: Session, proposal_id: str) -> MemoryProposal:
    proposal = get_memory_proposal(session, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="记忆候选不存在")
    return proposal


def _require_fact(session: Session, fact_id: str) -> MemoryFact:
    fact = session.get(MemoryFact, fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="MemoryFact 不存在")
    return fact


def _require_source(session: Session, source_id: str) -> SourceItem:
    source = session.get(SourceItem, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="SourceItem 不存在")
    return source


def _dedupe_strings(values: list[str]) -> list[str]:
    return [str(value).strip() for value in dict.fromkeys(values) if str(value or "").strip()]

