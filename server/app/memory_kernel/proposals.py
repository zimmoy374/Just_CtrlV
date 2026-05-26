from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from ..knowledge_core.lifecycle import commit_knowledge_item
from ..knowledge_core.source_items import upsert_source_item, validate_choice
from ..models import MemoryProposal, utc_now
from ..wiki.pages import upsert_knowledge_page


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
    evidence_refs: list[str] | None = None,
    task_session_id: str | None = None,
    status: str = "pending",
) -> MemoryProposal:
    validate_choice(proposal_type, MEMORY_PROPOSAL_TYPES, "memoryProposalType")
    validate_choice(status, MEMORY_PROPOSAL_STATUSES, "memoryProposalStatus")
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("MemoryProposal title 不能为空")

    proposal = MemoryProposal(
        id=str(uuid4()),
        task_session_id=task_session_id,
        type=proposal_type,
        title=clean_title,
        body=body.strip(),
        evidence_refs=[ref for ref in dict.fromkeys(evidence_refs or []) if ref],
        status=status,
    )
    session.add(proposal)
    session.flush()
    return proposal


def accept_memory_proposal(session: Session, proposal: MemoryProposal) -> MemoryProposal:
    if proposal.status == "accepted":
        return proposal
    if proposal.status != "pending":
        raise ValueError("只有 pending 的记忆候选可以接受")

    if proposal.type == "page_update":
        page = upsert_knowledge_page(
            session,
            title=proposal.title,
            summary=proposal.body,
            body="",
            keywords=[proposal.type],
            status="draft",
        )
        proposal.page_id = page.id
    else:
        source_item = upsert_source_item(
            session,
            source="just_ctrl_v",
            external_id=f"memory-proposal:{proposal.id}",
            kind="agent_selection",
            title=proposal.title,
            content_text=proposal.body,
            metadata={
                "proposalType": proposal.type,
                "taskSessionId": proposal.task_session_id,
                "evidenceRefs": proposal.evidence_refs,
            },
            status="active",
        )
        knowledge_item = commit_knowledge_item(
            session,
            source_item=source_item,
            knowledge_type="fragment",
            title=proposal.title,
            summary=proposal.body[:160],
            content=proposal.body,
            keywords=[proposal.type],
            source_ref=f"proposal:{proposal.id}",
            status="active",
        )
        proposal.source_item_id = source_item.id
        proposal.knowledge_item_id = knowledge_item.id

    proposal.status = "accepted"
    proposal.resolved_at = utc_now()
    session.add(proposal)
    session.flush()
    return proposal


def dismiss_memory_proposal(session: Session, proposal: MemoryProposal) -> MemoryProposal:
    if proposal.status != "pending":
        raise ValueError("只有 pending 的记忆候选可以忽略")
    proposal.status = "dismissed"
    proposal.resolved_at = utc_now()
    session.add(proposal)
    session.flush()
    return proposal
