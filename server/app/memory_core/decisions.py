from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlmodel import Session

from ..models import MemoryDecision, ProvenanceEvent


def record_memory_decision(
    session: Session,
    *,
    decision_type: str,
    target_ref: str,
    reason: str,
    evidence_refs: list[str],
    confidence: float | None = None,
    scope: str = "workspace",
    metadata: dict[str, Any] | None = None,
    actor: str = "user",
    policy: str = "review_gate",
) -> MemoryDecision:
    decision = MemoryDecision(
        id=str(uuid4()),
        decision_type=decision_type,
        target_ref=target_ref,
        actor=actor,
        reason=reason,
        policy=policy,
        evidence_refs=[ref for ref in dict.fromkeys(evidence_refs) if ref],
        confidence=confidence,
        scope=scope or "workspace",
        metadata_json=metadata or {},
    )
    session.add(decision)
    session.flush()
    return decision


def record_provenance_event(
    session: Session,
    *,
    event_type: str,
    from_ref: str | None,
    to_ref: str | None,
    reason: str,
    evidence_refs: list[str],
    payload: dict[str, Any] | None = None,
    actor: str = "system",
) -> ProvenanceEvent:
    event = ProvenanceEvent(
        id=str(uuid4()),
        event_type=event_type,
        from_ref=from_ref,
        to_ref=to_ref,
        actor=actor,
        reason=reason,
        evidence_refs=[ref for ref in dict.fromkeys(evidence_refs) if ref],
        payload_json=payload or {},
    )
    session.add(event)
    session.flush()
    return event
