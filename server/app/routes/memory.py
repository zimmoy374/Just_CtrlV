from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..database import get_session
from ..memory_kernel.proposals import (
    accept_memory_proposal,
    dismiss_memory_proposal,
    get_memory_proposal,
    list_memory_proposals,
)
from ..presenters import memory_proposal_to_response
from ..schemas import MemoryProposalResponse


router = APIRouter()


@router.get("/api/memory-proposals", response_model=list[MemoryProposalResponse])
def list_memory_proposals_api(
    status: str = "pending",
    session: Session = Depends(get_session),
) -> list[MemoryProposalResponse]:
    try:
        proposals = list_memory_proposals(session, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [memory_proposal_to_response(proposal) for proposal in proposals]


@router.post("/api/memory-proposals/{proposal_id}/accept", response_model=MemoryProposalResponse)
def accept_memory_proposal_api(proposal_id: str, session: Session = Depends(get_session)) -> MemoryProposalResponse:
    proposal = get_memory_proposal(session, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="记忆候选不存在")
    try:
        accept_memory_proposal(session, proposal)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(proposal)
    return memory_proposal_to_response(proposal)


@router.post("/api/memory-proposals/{proposal_id}/dismiss", response_model=MemoryProposalResponse)
def dismiss_memory_proposal_api(proposal_id: str, session: Session = Depends(get_session)) -> MemoryProposalResponse:
    proposal = get_memory_proposal(session, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="记忆候选不存在")
    try:
        dismiss_memory_proposal(session, proposal)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(proposal)
    return memory_proposal_to_response(proposal)
