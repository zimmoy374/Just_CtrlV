from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..memory_core.router import create_default_memory_router


router = APIRouter()


@router.post("/api/memory/projections/rebuild")
def rebuild_memory_projections_api(session: Session = Depends(get_session)) -> dict:
    reports = create_default_memory_router().rebuild_projections(session)
    session.commit()
    return {"status": "rebuilt", "projections": reports}
