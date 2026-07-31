from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Column, JSON, Text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Card(SQLModel, table=True):
    __tablename__ = "cards"

    id: str = Field(primary_key=True)
    # Kept for compatibility with existing databases. The app now has one board.
    week_key: str = Field(default="board", index=True)
    day_key: str = Field(default_factory=lambda: date.today().isoformat(), index=True)
    type: str
    text_content: Optional[str] = None
    image_filename: Optional[str] = None
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    source_description: Optional[str] = None
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


class AnalysisJob(SQLModel, table=True):
    __tablename__ = "analysis_jobs"

    id: str = Field(primary_key=True)
    card_id: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    reason: str = ""
    error: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    attempts: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
