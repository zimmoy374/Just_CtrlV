from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from ..models import Entity, MemoryConflict, MemoryDecision, MemoryFact, MemoryProposal, MemoryRelation, utc_now
from .decisions import record_memory_decision, record_provenance_event


def validate_profile_graph_proposal(session: Session, proposal: MemoryProposal) -> None:
    if not proposal.evidence_refs:
        raise ValueError("Profile graph memory 必须包含 evidence refs")
    if not proposal.structured_payload_json:
        raise ValueError("Profile graph proposal 必须包含 structured payload")

    payload = proposal.structured_payload_json or {}
    if proposal.type == "entity_relation":
        _entity_payload(payload, "from")
        _entity_payload(payload, "to")
        if not str(payload.get("relationType") or payload.get("predicate") or "").strip():
            raise ValueError("entity_relation 必须包含 relationType")
        return

    if proposal.type == "fact_supersession":
        supersedes_ref = _clean_ref(payload.get("supersedesFactRef") or payload.get("supersedes"))
        if not _fact_from_ref(session, supersedes_ref):
            raise ValueError("fact_supersession 必须包含有效的 supersedesFactRef")
        new_fact = payload.get("newFact")
        if not isinstance(new_fact, dict):
            raise ValueError("fact_supersession 必须包含 newFact")
        _validate_fact_payload(new_fact)
        return

    if proposal.type == "profile_fact":
        _validate_fact_payload(payload)
        return

    raise ValueError(f"profile_temporal_graph 不支持 proposal type：{proposal.type}")


def accept_profile_graph_proposal(
    session: Session,
    proposal: MemoryProposal,
    *,
    target_store: str,
    routed_decision: MemoryDecision,
) -> MemoryProposal:
    if proposal.type == "entity_relation":
        relation = _create_relation_from_proposal(session, proposal)
        target_ref = f"relation:{relation.id}"
        accepted_decision = _record_acceptance(
            session,
            proposal=proposal,
            target_store=target_store,
            target_ref=target_ref,
            routed_decision=routed_decision,
            event_type="accepted_proposal_created_relation",
        )
        relation.decision_ref = f"decision:{accepted_decision.id}"
        session.add(relation)
        _finish_proposal(proposal, target_store=target_store, decision_ref=relation.decision_ref)
        session.flush()
        return proposal

    fact_payload = _fact_payload(proposal)
    supersedes_ref = _clean_ref(
        fact_payload.get("supersedesFactRef")
        or proposal.structured_payload_json.get("supersedesFactRef")
        or proposal.structured_payload_json.get("supersedes")
    )
    superseded_fact = _fact_from_ref(session, supersedes_ref) if supersedes_ref else None
    if proposal.type == "fact_supersession" and not superseded_fact:
        raise ValueError("fact_supersession 必须包含有效的 supersedesFactRef")

    fact = _create_fact_from_payload(session, proposal, fact_payload, status="active")
    target_ref = f"fact:{fact.id}"

    conflict = None
    if superseded_fact:
        _supersede_fact(session, old_fact=superseded_fact, new_fact=fact, proposal=proposal)
    else:
        conflicting_facts = _find_conflicting_facts(session, fact)
        if conflicting_facts:
            fact.status = "conflicted"
            conflict = _open_fact_conflict(session, proposal=proposal, new_fact=fact, conflicting_facts=conflicting_facts)

    accepted_decision = _record_acceptance(
        session,
        proposal=proposal,
        target_store=target_store,
        target_ref=target_ref,
        routed_decision=routed_decision,
        event_type="accepted_proposal_created_fact",
        extra_payload={"conflictRef": f"conflict:{conflict.id}" if conflict else None},
    )
    fact.decision_ref = f"decision:{accepted_decision.id}"
    session.add(fact)
    if conflict:
        conflict.decision_ref = conflict.decision_ref or fact.decision_ref
        session.add(conflict)

    _finish_proposal(proposal, target_store=target_store, decision_ref=fact.decision_ref)
    session.flush()
    return proposal


def _fact_payload(proposal: MemoryProposal) -> dict[str, Any]:
    payload = proposal.structured_payload_json or {}
    if proposal.type == "fact_supersession" and isinstance(payload.get("newFact"), dict):
        merged = {**payload["newFact"]}
        for key in ["supersedesFactRef", "supersedes"]:
            if key in payload and key not in merged:
                merged[key] = payload[key]
        return merged
    return payload


def _create_fact_from_payload(
    session: Session,
    proposal: MemoryProposal,
    payload: dict[str, Any],
    *,
    status: str,
) -> MemoryFact:
    subject = _upsert_entity(session, _entity_payload(payload, "subject"), source_refs=proposal.evidence_refs)
    object_entity_payload = _entity_payload(payload, "objectEntity", allow_empty=True)
    object_entity = _upsert_entity(session, object_entity_payload, source_refs=proposal.evidence_refs) if object_entity_payload else None
    predicate = str(payload.get("predicate") or payload.get("relation") or "").strip()
    if not predicate:
        raise ValueError("profile_fact 必须包含 predicate")
    object_value = str(payload.get("objectValue") or payload.get("value") or proposal.body or "").strip()
    if not object_value and not object_entity:
        raise ValueError("profile_fact 必须包含 objectValue 或 objectEntity")

    return MemoryFact(
        id=str(uuid4()),
        subject_entity_id=subject.id,
        predicate=predicate,
        object_value=object_value,
        object_entity_id=object_entity.id if object_entity else None,
        confidence=proposal.confidence,
        valid_at=_parse_dt(payload.get("validAt")) or utc_now(),
        evidence_refs=proposal.evidence_refs or [],
        status=status,
        scope=proposal.scope or "workspace",
        source_proposal_id=proposal.id,
    )


def _validate_fact_payload(payload: dict[str, Any]) -> None:
    _entity_payload(payload, "subject")
    object_entity_payload = _entity_payload(payload, "objectEntity", allow_empty=True)
    predicate = str(payload.get("predicate") or payload.get("relation") or "").strip()
    if not predicate:
        raise ValueError("profile_fact 必须包含 predicate")
    object_value = str(payload.get("objectValue") or payload.get("value") or "").strip()
    if not object_value and not object_entity_payload:
        raise ValueError("profile_fact 必须包含 objectValue 或 objectEntity")


def _create_relation_from_proposal(session: Session, proposal: MemoryProposal) -> MemoryRelation:
    payload = proposal.structured_payload_json or {}
    from_entity = _upsert_entity(session, _entity_payload(payload, "from"), source_refs=proposal.evidence_refs)
    to_entity = _upsert_entity(session, _entity_payload(payload, "to"), source_refs=proposal.evidence_refs)
    relation_type = str(payload.get("relationType") or payload.get("predicate") or "").strip()
    if not relation_type:
        raise ValueError("entity_relation 必须包含 relationType")

    return MemoryRelation(
        id=str(uuid4()),
        from_entity_id=from_entity.id,
        relation_type=relation_type,
        to_entity_id=to_entity.id,
        confidence=proposal.confidence,
        valid_at=_parse_dt(payload.get("validAt")) or utc_now(),
        evidence_refs=proposal.evidence_refs or [],
        status="active",
        scope=proposal.scope or "workspace",
        source_proposal_id=proposal.id,
    )


def _entity_payload(payload: dict[str, Any], prefix: str, *, allow_empty: bool = False) -> dict[str, Any]:
    value = payload.get(prefix)
    if isinstance(value, dict):
        entity = dict(value)
    elif isinstance(value, str):
        entity = {"name": value}
    else:
        name_key = f"{prefix}Name"
        type_key = f"{prefix}Type"
        entity = {"name": payload.get(name_key), "type": payload.get(type_key)}
    name = str(entity.get("name") or "").strip()
    if not name:
        if allow_empty:
            return {}
        raise ValueError(f"{prefix} entity 必须包含 name")
    entity["name"] = name
    entity["type"] = str(entity.get("type") or "person").strip() or "person"
    aliases = entity.get("aliases")
    entity["aliases"] = [str(item).strip() for item in aliases if str(item).strip()] if isinstance(aliases, list) else []
    return entity


def _upsert_entity(session: Session, payload: dict[str, Any], *, source_refs: list[str]) -> Entity:
    entity_type = str(payload["type"]).strip()
    name = str(payload["name"]).strip()
    candidates = session.exec(select(Entity).where(Entity.type == entity_type)).all()
    entity = next((item for item in candidates if item.name.casefold() == name.casefold()), None)
    now = utc_now()
    aliases = _merge_strings(payload.get("aliases") or [], entity.aliases if entity else [])
    merged_source_refs = _merge_strings(source_refs, entity.source_refs if entity else [])
    if entity:
        entity.name = entity.name or name
        entity.aliases = aliases
        entity.source_refs = merged_source_refs
        entity.updated_at = now
    else:
        entity = Entity(id=str(uuid4()), type=entity_type, name=name, aliases=aliases, source_refs=merged_source_refs)
    session.add(entity)
    session.flush()
    return entity


def _find_conflicting_facts(session: Session, fact: MemoryFact) -> list[MemoryFact]:
    candidates = session.exec(
        select(MemoryFact).where(
            MemoryFact.subject_entity_id == fact.subject_entity_id,
            MemoryFact.predicate == fact.predicate,
            MemoryFact.scope == fact.scope,
            MemoryFact.status == "active",
            MemoryFact.invalid_at.is_(None),
        ),
    ).all()
    return [candidate for candidate in candidates if _fact_object_key(candidate) != _fact_object_key(fact)]


def _supersede_fact(session: Session, *, old_fact: MemoryFact, new_fact: MemoryFact, proposal: MemoryProposal) -> None:
    if old_fact.status != "active":
        raise ValueError("只能 supersede active profile fact")
    now = utc_now()
    old_fact.status = "superseded"
    old_fact.invalid_at = now
    old_fact.superseded_by = new_fact.id
    old_fact.updated_at = now
    session.add(old_fact)
    decision = record_memory_decision(
        session,
        decision_type="fact_superseded",
        target_ref=f"fact:{old_fact.id}",
        reason=proposal.review_note or f"Superseded by fact:{new_fact.id}",
        evidence_refs=proposal.evidence_refs or [],
        confidence=proposal.confidence,
        scope=proposal.scope,
        metadata={"newFactRef": f"fact:{new_fact.id}", "proposalRef": f"proposal:{proposal.id}"},
    )
    record_provenance_event(
        session,
        event_type="fact_superseded",
        from_ref=f"fact:{old_fact.id}",
        to_ref=f"fact:{new_fact.id}",
        reason=proposal.review_note or "Profile fact superseded by reviewed proposal",
        evidence_refs=proposal.evidence_refs or [],
        payload={"decisionRef": f"decision:{decision.id}", "proposalRef": f"proposal:{proposal.id}"},
    )


def _open_fact_conflict(
    session: Session,
    *,
    proposal: MemoryProposal,
    new_fact: MemoryFact,
    conflicting_facts: list[MemoryFact],
) -> MemoryConflict:
    conflict = MemoryConflict(
        id=str(uuid4()),
        conflict_type="fact_conflict",
        fact_ids=[*[fact.id for fact in conflicting_facts], new_fact.id],
        reason=f"Conflicting active values for predicate {new_fact.predicate}",
        status="open",
        scope=new_fact.scope,
    )
    session.add(conflict)
    session.flush()
    decision = record_memory_decision(
        session,
        decision_type="conflict_opened",
        target_ref=f"conflict:{conflict.id}",
        reason=conflict.reason,
        evidence_refs=proposal.evidence_refs or [],
        confidence=proposal.confidence,
        scope=proposal.scope,
        metadata={"factRefs": [f"fact:{fact_id}" for fact_id in conflict.fact_ids], "proposalRef": f"proposal:{proposal.id}"},
    )
    conflict.decision_ref = f"decision:{decision.id}"
    session.add(conflict)
    record_provenance_event(
        session,
        event_type="conflict_opened",
        from_ref=f"fact:{new_fact.id}",
        to_ref=f"conflict:{conflict.id}",
        reason=conflict.reason,
        evidence_refs=proposal.evidence_refs or [],
        payload={"decisionRef": conflict.decision_ref, "factRefs": [f"fact:{fact_id}" for fact_id in conflict.fact_ids]},
    )
    return conflict


def _record_acceptance(
    session: Session,
    *,
    proposal: MemoryProposal,
    target_store: str,
    target_ref: str,
    routed_decision: MemoryDecision,
    event_type: str,
    extra_payload: dict[str, Any] | None = None,
) -> MemoryDecision:
    accepted_decision = record_memory_decision(
        session,
        decision_type="proposal_accepted",
        target_ref=f"proposal:{proposal.id}",
        reason=proposal.review_note or f"Accepted into {target_store}",
        evidence_refs=proposal.evidence_refs or [],
        confidence=proposal.confidence,
        scope=proposal.scope,
        metadata={"targetStore": target_store, "createdRef": target_ref, "routedDecisionRef": f"decision:{routed_decision.id}"},
    )
    payload = {"decisionRef": f"decision:{accepted_decision.id}", "targetStore": target_store}
    payload.update({key: value for key, value in (extra_payload or {}).items() if value})
    record_provenance_event(
        session,
        event_type=event_type,
        from_ref=f"proposal:{proposal.id}",
        to_ref=target_ref,
        reason=proposal.review_note or f"Accepted into {target_store}",
        evidence_refs=proposal.evidence_refs or [],
        payload=payload,
    )
    return accepted_decision


def _finish_proposal(proposal: MemoryProposal, *, target_store: str, decision_ref: str | None) -> None:
    proposal.target_store = target_store
    proposal.decision_ref = decision_ref
    proposal.status = "accepted"
    proposal.resolved_at = utc_now()


def _fact_from_ref(session: Session, ref: str | None) -> MemoryFact | None:
    if not ref or not ref.startswith("fact:"):
        return None
    return session.get(MemoryFact, ref.removeprefix("fact:"))


def _clean_ref(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    return text or None


def _fact_object_key(fact: MemoryFact) -> tuple[str, str]:
    return ((fact.object_value or "").casefold(), fact.object_entity_id or "")


def _merge_strings(first: list[str], second: list[str]) -> list[str]:
    return [item for item in dict.fromkeys([*second, *first]) if item]


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
