from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TextCardCreate(BaseModel):
    week_key: str = Field(alias="weekKey")
    text_content: str = Field(alias="textContent", min_length=1)
    x: float = 120
    y: float = 120

    model_config = ConfigDict(populate_by_name=True)


class CardPatch(BaseModel):
    text_content: Optional[str] = Field(default=None, alias="textContent")
    summary: Optional[str] = None
    keywords: Optional[list[str]] = None
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    rotation: Optional[float] = None
    style_seed: Optional[str] = Field(default=None, alias="styleSeed")
    ai_status: Optional[str] = Field(default=None, alias="aiStatus")
    ai_error: Optional[str] = Field(default=None, alias="aiError")

    model_config = ConfigDict(populate_by_name=True)


class CardResponse(BaseModel):
    id: str
    week_key: str = Field(alias="weekKey")
    type: str
    text_content: Optional[str] = Field(default=None, alias="textContent")
    image_url: Optional[str] = Field(default=None, alias="imageUrl")
    summary: Optional[str] = None
    keywords: list[str]
    x: float
    y: float
    width: float
    rotation: float
    style_seed: str = Field(alias="styleSeed")
    ai_status: str = Field(alias="aiStatus")
    ai_error: Optional[str] = Field(default=None, alias="aiError")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class SearchResult(BaseModel):
    card: CardResponse
    week_key: str = Field(alias="weekKey")
    matched_keywords: list[str] = Field(alias="matchedKeywords")
    score: float

    model_config = ConfigDict(populate_by_name=True)


class KnowledgeGraphNode(BaseModel):
    id: str
    type: str
    label: str
    week_key: Optional[str] = Field(default=None, alias="weekKey")
    count: int = 0
    weeks: list[str] = Field(default_factory=list)
    card: Optional[CardResponse] = None

    model_config = ConfigDict(populate_by_name=True)


class KnowledgeGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    keyword: str


class KnowledgeGraphResponse(BaseModel):
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]
