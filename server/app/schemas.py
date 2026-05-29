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


class LinkCardCreate(BaseModel):
    week_key: str = Field(alias="weekKey")
    url: str = Field(min_length=1)
    x: float = 120
    y: float = 120

    model_config = ConfigDict(populate_by_name=True)


class CardPatch(BaseModel):
    text_content: Optional[str] = Field(default=None, alias="textContent")
    source_url: Optional[str] = Field(default=None, alias="sourceUrl")
    source_title: Optional[str] = Field(default=None, alias="sourceTitle")
    source_description: Optional[str] = Field(default=None, alias="sourceDescription")
    summary: Optional[str] = None
    keywords: Optional[list[str]] = None
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    rotation: Optional[float] = None
    style_seed: Optional[str] = Field(default=None, alias="styleSeed")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CardResponse(BaseModel):
    id: str
    week_key: str = Field(alias="weekKey")
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


class KnowledgeGraphNode(BaseModel):
    id: str
    type: str
    label: str
    week_key: Optional[str] = Field(default=None, alias="weekKey")
    count: int = 0
    weeks: list[str] = Field(default_factory=list)
    card: Optional[CardResponse] = None
    knowledge_item: Optional[KnowledgeItemResponse] = Field(default=None, alias="knowledgeItem")
    status: Optional[str] = None
    item_count: int = Field(default=0, alias="itemCount")

    model_config = ConfigDict(populate_by_name=True)


class KnowledgeGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    keyword: str


class KnowledgeGraphResponse(BaseModel):
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]


class KnowledgeItemResponse(BaseModel):
    id: str
    source_item_id: str = Field(alias="sourceItemId")
    card_id: Optional[str] = Field(default=None, alias="cardId")
    title: str
    summary: str
    content: str
    keywords: list[str]
    source: str
    source_ref: str = Field(alias="sourceRef")
    knowledge_type: str = Field(alias="knowledgeType")
    status: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class KnowledgeSearchResult(BaseModel):
    knowledge_item: KnowledgeItemResponse = Field(alias="knowledgeItem")
    card: Optional[CardResponse] = None
    matched_fields: list[str] = Field(alias="matchedFields")
    score: float
    excerpt: str = ""
    reason: str = ""
    source: str = ""

    model_config = ConfigDict(populate_by_name=True)


class ConfirmedKnowledgeImport(BaseModel):
    title: str = Field(min_length=1)
    summary: str = ""
    body: str = ""
    keywords: list[str] = Field(default_factory=list)
    selected_original_text: str = Field(alias="selectedOriginalText", min_length=1)
    source_title: str = Field(default="", alias="sourceTitle")
    source_url: str = Field(default="", alias="sourceUrl")
    external_id: str = Field(default="", alias="externalId")
    proposed_pages: list[str] = Field(default_factory=list, alias="proposedPages")
    metadata: dict = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)


class ConfirmedKnowledgeImportResponse(BaseModel):
    source_item_id: str = Field(alias="sourceItemId")
    knowledge_item: KnowledgeItemResponse = Field(alias="knowledgeItem")
    suggestion_ids: list[str] = Field(alias="suggestionIds")

    model_config = ConfigDict(populate_by_name=True)


class ContextBudgetResponse(BaseModel):
    max_pages: int = Field(alias="maxPages")
    max_items: int = Field(alias="maxItems")
    max_source_excerpts: int = Field(alias="maxSourceExcerpts")
    max_chars: int = Field(alias="maxChars")
    used_chars: int = Field(alias="usedChars")
    truncated: bool

    model_config = ConfigDict(populate_by_name=True)


class ContextCitationRef(BaseModel):
    ref: str
    kind: str
    id: str
    label: str


class ContextKnowledgePageSummary(BaseModel):
    id: str
    title: str
    summary: str
    status: str
    keywords: list[str]
    updated_at: datetime = Field(alias="updatedAt")
    citation_ref: str = Field(alias="citationRef")
    item_refs: list[str] = Field(alias="itemRefs")

    model_config = ConfigDict(populate_by_name=True)


class ContextKnowledgeItemEvidence(BaseModel):
    id: str
    title: str
    summary: str
    excerpt: str
    score: float
    matched_fields: list[str] = Field(alias="matchedFields")
    reason: str
    source: str
    source_ref: str = Field(alias="sourceRef")
    citation_ref: str = Field(alias="citationRef")
    page_refs: list[str] = Field(alias="pageRefs")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class ContextSourceExcerpt(BaseModel):
    id: str
    source_item_id: str = Field(alias="sourceItemId")
    knowledge_item_id: str = Field(alias="knowledgeItemId")
    title: str
    kind: str
    excerpt: str
    citation_ref: str = Field(alias="citationRef")

    model_config = ConfigDict(populate_by_name=True)


class ContextPackResponse(BaseModel):
    query: str
    protocol_reminder: list[str] = Field(alias="protocolReminder")
    related_pages: list[ContextKnowledgePageSummary] = Field(alias="relatedPages")
    related_items: list[ContextKnowledgeItemEvidence] = Field(alias="relatedItems")
    source_excerpts: list[ContextSourceExcerpt] = Field(alias="sourceExcerpts")
    budget: ContextBudgetResponse
    citation_refs: list[ContextCitationRef] = Field(alias="citationRefs")

    model_config = ConfigDict(populate_by_name=True)


class ExportBundleResponse(BaseModel):
    export_path: str = Field(alias="exportPath")
    files: list[str]

    model_config = ConfigDict(populate_by_name=True)


class MemoryProposalResponse(BaseModel):
    id: str
    task_session_id: Optional[str] = Field(default=None, alias="taskSessionId")
    target_store: str = Field(alias="targetStore")
    type: str
    title: str
    body: str
    structured_payload: dict = Field(alias="structuredPayload")
    scope: str
    evidence_refs: list[str] = Field(alias="evidenceRefs")
    confidence: Optional[float] = None
    review_note: str = Field(alias="reviewNote")
    status: str
    source_item_id: Optional[str] = Field(default=None, alias="sourceItemId")
    knowledge_item_id: Optional[str] = Field(default=None, alias="knowledgeItemId")
    page_id: Optional[str] = Field(default=None, alias="pageId")
    decision_ref: Optional[str] = Field(default=None, alias="decisionRef")
    created_at: datetime = Field(alias="createdAt")
    resolved_at: Optional[datetime] = Field(default=None, alias="resolvedAt")

    model_config = ConfigDict(populate_by_name=True)


class TaskSessionCreate(BaseModel):
    title: str = Field(min_length=1)
    user_goal: str = Field(alias="userGoal", min_length=1)
    active_agent: str = Field(default="", alias="activeAgent")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class TaskEventCreate(BaseModel):
    type: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    payload: dict = Field(default_factory=dict)
    source: str = "just_ctrl_v"
    source_ref: str = Field(default="", alias="sourceRef")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class TaskStatePatch(BaseModel):
    current_goal: Optional[str] = Field(default=None, alias="currentGoal")
    done: Optional[list[str]] = None
    in_progress: Optional[list[str]] = Field(default=None, alias="inProgress")
    next_steps: Optional[list[str]] = Field(default=None, alias="nextSteps")
    open_questions: Optional[list[str]] = Field(default=None, alias="openQuestions")
    constraints: Optional[list[str]] = None
    risks: Optional[list[str]] = None
    decisions: Optional[list[str]] = None
    files_touched: Optional[list[str]] = Field(default=None, alias="filesTouched")
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class TaskCheckpointCreate(BaseModel):
    title: str = Field(min_length=1)
    summary: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class TaskSessionResponse(BaseModel):
    id: str
    title: str
    user_goal: str = Field(alias="userGoal")
    status: str
    active_agent: str = Field(alias="activeAgent")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    last_event_at: Optional[datetime] = Field(default=None, alias="lastEventAt")
    closed_at: Optional[datetime] = Field(default=None, alias="closedAt")
    expires_at: Optional[datetime] = Field(default=None, alias="expiresAt")

    model_config = ConfigDict(populate_by_name=True)


class TaskEventResponse(BaseModel):
    id: str
    task_session_id: str = Field(alias="taskSessionId")
    type: str
    summary: str
    payload: dict
    source: str
    source_ref: str = Field(alias="sourceRef")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class TaskStateResponse(BaseModel):
    task_session_id: str = Field(alias="taskSessionId")
    current_goal: str = Field(alias="currentGoal")
    done: list[str]
    in_progress: list[str] = Field(alias="inProgress")
    next_steps: list[str] = Field(alias="nextSteps")
    open_questions: list[str] = Field(alias="openQuestions")
    constraints: list[str]
    risks: list[str]
    decisions: list[str]
    files_touched: list[str] = Field(alias="filesTouched")
    confidence: float
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class TaskCheckpointResponse(BaseModel):
    id: str
    task_session_id: str = Field(alias="taskSessionId")
    title: str
    summary: str
    state_snapshot: dict = Field(alias="stateSnapshot")
    event_from_id: Optional[str] = Field(default=None, alias="eventFromId")
    event_to_id: Optional[str] = Field(default=None, alias="eventToId")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class TaskDetailResponse(BaseModel):
    task: TaskSessionResponse
    state: TaskStateResponse
    events: list[TaskEventResponse]
    checkpoints: list[TaskCheckpointResponse]

    model_config = ConfigDict(populate_by_name=True)


class HandoffPackResponse(BaseModel):
    id: Optional[str] = None
    task_session_id: str = Field(alias="taskSessionId")
    format: str
    content: str
    pack: dict
    budget: dict
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class KnowledgePageSummaryResponse(BaseModel):
    id: str
    title: str
    summary: str
    status: str
    keywords: list[str]
    updated_at: datetime = Field(alias="updatedAt")
    item_count: int = Field(alias="itemCount")

    model_config = ConfigDict(populate_by_name=True)


class ReflectionResponse(BaseModel):
    id: str
    trigger_key: str = Field(alias="triggerKey")
    title: str
    reason: str
    question: str
    related_knowledge_item_ids: list[str] = Field(alias="relatedKnowledgeItemIds")
    status: str
    created_at: datetime = Field(alias="createdAt")
    resolved_at: Optional[datetime] = Field(default=None, alias="resolvedAt")

    model_config = ConfigDict(populate_by_name=True)
