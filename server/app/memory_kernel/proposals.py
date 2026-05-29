from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from ..knowledge_core.source_items import validate_choice
from ..memory_core.decisions import record_memory_decision, record_provenance_event
from ..memory_core.protocol import DEFAULT_PROPOSAL_TARGET_STORES, MEMORY_TARGET_STORES
from ..memory_core.router import create_default_memory_router
from ..models import MemoryProposal, utc_now


MEMORY_PROPOSAL_TYPES = {
    "lesson",
    "pitfall",
    "user_preference",
    "project_rule",
    "workflow_pattern",
    "technical_decision",
    "environment_fact",
    "page_update",
}
MEMORY_PROPOSAL_STATUSES = {"pending", "accepted", "dismissed"}


def list_memory_proposals(session: Session, *, status: str = "pending") -> list[MemoryProposal]:
    statement = select(MemoryProposal).order_by(MemoryProposal.created_at)
    if status != "all":
        validate_choice(status, MEMORY_PROPOSAL_STATUSES, "memoryProposalStatus")
        statement = statement.where(MemoryProposal.status == status)
    return list(session.exec(statement).all())


def get_memory_proposal(session: Session, proposal_id: str) -> MemoryProposal | None:
    return session.get(MemoryProposal, proposal_id)


def create_memory_proposal(
    session: Session,
    *,
    proposal_type: str,
    title: str,
    body: str,
    target_store: str | None = None,
    structured_payload: dict | None = None,
    scope: str = "workspace",
    confidence: float | None = None,
    review_note: str = "",
    evidence_refs: list[str] | None = None,
    task_session_id: str | None = None,
    status: str = "pending",
) -> MemoryProposal:
    validate_choice(proposal_type, MEMORY_PROPOSAL_TYPES, "memoryProposalType")
    validate_choice(status, MEMORY_PROPOSAL_STATUSES, "memoryProposalStatus")
    resolved_target_store = target_store or DEFAULT_PROPOSAL_TARGET_STORES[proposal_type]
    validate_choice(resolved_target_store, MEMORY_TARGET_STORES, "memoryTargetStore")
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("MemoryProposal title 不能为空")
    clean_evidence_refs = [ref for ref in dict.fromkeys(evidence_refs or []) if ref]

    proposal = MemoryProposal(
        id=str(uuid4()),
        task_session_id=task_session_id,
        target_store=resolved_target_store,
        type=proposal_type,
        title=clean_title,
        body=body.strip(),
        structured_payload_json=structured_payload or {},
        scope=scope.strip() or "workspace",
        evidence_refs=clean_evidence_refs,
        confidence=confidence,
        review_note=review_note.strip(),
        status=status,
    )
    session.add(proposal)
    session.flush()
    decision = record_memory_decision(
        session,
        decision_type="proposal_created",
        target_ref=f"proposal:{proposal.id}",
        reason=f"Created proposal for {resolved_target_store}",
        evidence_refs=clean_evidence_refs,
        confidence=confidence,
        scope=proposal.scope,
        metadata={"proposalType": proposal.type, "targetStore": resolved_target_store},
        actor="system",
        policy="proposal_review_required",
    )
    proposal.decision_ref = f"decision:{decision.id}"
    record_provenance_event(
        session,
        event_type="proposal_created",
        from_ref=None,
        to_ref=f"proposal:{proposal.id}",
        reason=f"Created proposal for {resolved_target_store}",
        evidence_refs=clean_evidence_refs,
        payload={"decisionRef": proposal.decision_ref, "proposalType": proposal.type, "targetStore": resolved_target_store},
    )
    if task_session_id:
        record_provenance_event(
            session,
            event_type="proposal_for_task",
            from_ref=f"proposal:{proposal.id}",
            to_ref=f"task:{task_session_id}",
            reason="Proposal created from task context",
            evidence_refs=clean_evidence_refs,
            payload={"decisionRef": proposal.decision_ref, "targetStore": resolved_target_store},
        )
    session.add(proposal)
    session.flush()
    return proposal


def accept_memory_proposal(session: Session, proposal: MemoryProposal) -> MemoryProposal:
    return create_default_memory_router().accept_proposal(session, proposal)


def dismiss_memory_proposal(session: Session, proposal: MemoryProposal) -> MemoryProposal:
    if proposal.status != "pending":
        raise ValueError("只有 pending 的记忆候选可以忽略")
    decision = record_memory_decision(
        session,
        decision_type="proposal_dismissed",
        target_ref=f"proposal:{proposal.id}",
        reason=proposal.review_note or "Dismissed by review gate",
        evidence_refs=proposal.evidence_refs or [],
        confidence=proposal.confidence,
        scope=proposal.scope,
        metadata={"proposalType": proposal.type, "targetStore": proposal.target_store},
    )
    proposal.decision_ref = f"decision:{decision.id}"
    proposal.status = "dismissed"
    proposal.resolved_at = utc_now()
    session.add(proposal)
    record_provenance_event(
        session,
        event_type="proposal_dismissed",
        from_ref=f"proposal:{proposal.id}",
        to_ref=proposal.decision_ref,
        reason=proposal.review_note or "Dismissed by review gate",
        evidence_refs=proposal.evidence_refs or [],
        payload={"targetStore": proposal.target_store},
    )
    session.flush()
    return proposal
