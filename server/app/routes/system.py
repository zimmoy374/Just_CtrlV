from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..database import get_session
from ..system.status import collect_system_status


router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def get_system_status_api(session: Session = Depends(get_session)) -> dict[str, Any]:
    return collect_system_status(session)
