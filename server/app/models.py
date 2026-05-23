from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Card(SQLModel, table=True):
    __tablename__ = "cards"

    id: str = Field(primary_key=True)
    week_key: str = Field(index=True)
    type: str
    text_content: Optional[str] = None
    image_filename: Optional[str] = None
    summary: Optional[str] = None
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    x: float = 120
    y: float = 120
    width: float = 280
    rotation: float = 0
    style_seed: str
    ai_status: str = "pending"
    ai_error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
