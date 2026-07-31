from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TextCardCreate(BaseModel):
    day_key: str = Field(alias="dayKey")
    text_content: str = Field(alias="textContent", min_length=1)
    x: float = Field(default=0.12, ge=0, le=1)
    y: float = Field(default=0.16, ge=0, le=1)

    model_config = ConfigDict(populate_by_name=True)


class LinkCardCreate(BaseModel):
    day_key: str = Field(alias="dayKey")
    url: str = Field(min_length=1)
    x: float = Field(default=0.12, ge=0, le=1)
    y: float = Field(default=0.16, ge=0, le=1)

    model_config = ConfigDict(populate_by_name=True)


class CardPatch(BaseModel):
    text_content: Optional[str] = Field(default=None, alias="textContent")
    source_url: Optional[str] = Field(default=None, alias="sourceUrl")
    source_title: Optional[str] = Field(default=None, alias="sourceTitle")
    source_description: Optional[str] = Field(default=None, alias="sourceDescription")
    summary: Optional[str] = None
    keywords: Optional[list[str]] = None
    x: Optional[float] = Field(default=None, ge=0, le=1)
    y: Optional[float] = Field(default=None, ge=0, le=1)
    width: Optional[float] = None
    rotation: Optional[float] = None
    style_seed: Optional[str] = Field(default=None, alias="styleSeed")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CardResponse(BaseModel):
    id: str
    day_key: str = Field(alias="dayKey")
    type: str
    text_content: Optional[str] = Field(default=None, alias="textContent")
    image_url: Optional[str] = Field(default=None, alias="imageUrl")
    source_url: Optional[str] = Field(default=None, alias="sourceUrl")
    source_title: Optional[str] = Field(default=None, alias="sourceTitle")
    source_description: Optional[str] = Field(default=None, alias="sourceDescription")
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
