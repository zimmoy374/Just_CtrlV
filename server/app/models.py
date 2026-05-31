from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, JSON, Text, UniqueConstraint
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


class TaskSession(SQLModel, table=True):
    __tablename__ = "task_sessions"

    id: str = Field(primary_key=True)
    title: str = Field(index=True)
    user_goal: str = Field(default="", sa_column=Column(Text, nullable=False))
    status: str = Field(default="open", index=True)
    active_agent: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_event_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class TaskEvent(SQLModel, table=True):
    __tablename__ = "task_events"

    id: str = Field(primary_key=True)
    task_session_id: str = Field(index=True)
    type: str = Field(index=True)
    summary: str = Field(default="", sa_column=Column(Text, nullable=False))
    payload_json: dict = Field(default_factory=dict, sa_column=Column("payload", JSON, nullable=False))
    source: str = Field(default="second_brain", index=True)
    source_ref: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class TaskState(SQLModel, table=True):
    __tablename__ = "task_states"

    task_session_id: str = Field(primary_key=True)
    current_goal: str = Field(default="", sa_column=Column(Text, nullable=False))
    done_json: list[str] = Field(default_factory=list, sa_column=Column("done", JSON, nullable=False))
    in_progress_json: list[str] = Field(default_factory=list, sa_column=Column("in_progress", JSON, nullable=False))
    next_steps_json: list[str] = Field(default_factory=list, sa_column=Column("next_steps", JSON, nullable=False))
    open_questions_json: list[str] = Field(default_factory=list, sa_column=Column("open_questions", JSON, nullable=False))
    constraints_json: list[str] = Field(default_factory=list, sa_column=Column("constraints", JSON, nullable=False))
    risks_json: list[str] = Field(default_factory=list, sa_column=Column("risks", JSON, nullable=False))
    decisions_json: list[str] = Field(default_factory=list, sa_column=Column("decisions", JSON, nullable=False))
    files_touched_json: list[str] = Field(default_factory=list, sa_column=Column("files_touched", JSON, nullable=False))
    confidence: float = 0.6
    updated_at: datetime = Field(default_factory=utc_now)


class TaskCheckpoint(SQLModel, table=True):
    __tablename__ = "task_checkpoints"

    id: str = Field(primary_key=True)
    task_session_id: str = Field(index=True)
    title: str
    summary: str = Field(default="", sa_column=Column(Text, nullable=False))
    state_snapshot_json: dict = Field(default_factory=dict, sa_column=Column("state_snapshot", JSON, nullable=False))
    event_from_id: Optional[str] = None
    event_to_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


class TaskDigest(SQLModel, table=True):
    __tablename__ = "task_digests"

    task_session_id: str = Field(primary_key=True)
    summary: str = Field(default="", sa_column=Column(Text, nullable=False))
    done_json: list[str] = Field(default_factory=list, sa_column=Column("done", JSON, nullable=False))
    decisions_json: list[str] = Field(default_factory=list, sa_column=Column("decisions", JSON, nullable=False))
    open_questions_json: list[str] = Field(default_factory=list, sa_column=Column("open_questions", JSON, nullable=False))
    risks_json: list[str] = Field(default_factory=list, sa_column=Column("risks", JSON, nullable=False))
    files_touched_json: list[str] = Field(default_factory=list, sa_column=Column("files_touched", JSON, nullable=False))
    source_refs_json: list[str] = Field(default_factory=list, sa_column=Column("source_refs", JSON, nullable=False))
    event_from_id: Optional[str] = None
    event_to_id: Optional[str] = None
    event_count: int = 0
    updated_at: datetime = Field(default_factory=utc_now)


class HandoffPack(SQLModel, table=True):
    __tablename__ = "handoff_packs"

    id: str = Field(primary_key=True)
    task_session_id: str = Field(index=True)
    format: str = Field(default="markdown", index=True)
    content: str = Field(default="", sa_column=Column(Text, nullable=False))
    budget_json: dict = Field(default_factory=dict, sa_column=Column("budget", JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now)


class MemoryProposal(SQLModel, table=True):
    __tablename__ = "memory_proposals"

    id: str = Field(primary_key=True)
    task_session_id: Optional[str] = Field(default=None, index=True)
    target_store: str = Field(index=True)
    type: str = Field(index=True)
    title: str
    body: str = Field(default="", sa_column=Column(Text, nullable=False))
    structured_payload_json: dict = Field(default_factory=dict, sa_column=Column("structured_payload", JSON, nullable=False))
    scope: str = Field(default="workspace", index=True)
    evidence_refs: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    confidence: Optional[float] = None
    review_note: str = Field(default="", sa_column=Column(Text, nullable=False))
    status: str = Field(default="pending", index=True)
    source_item_id: Optional[str] = Field(default=None, index=True)
    knowledge_item_id: Optional[str] = Field(default=None, index=True)
    page_id: Optional[str] = Field(default=None, index=True)
    decision_ref: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: Optional[datetime] = None


class MemoryDecision(SQLModel, table=True):
    __tablename__ = "memory_decisions"

    id: str = Field(primary_key=True)
    decision_type: str = Field(index=True)
    target_ref: str = Field(index=True)
    actor: str = Field(default="user", index=True)
    reason: str = Field(default="", sa_column=Column(Text, nullable=False))
    policy: str = ""
    evidence_refs: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    confidence: Optional[float] = None
    scope: str = Field(default="workspace", index=True)
    metadata_json: dict = Field(default_factory=dict, sa_column=Column("metadata", JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now)


class ProvenanceEvent(SQLModel, table=True):
    __tablename__ = "provenance_events"

    id: str = Field(primary_key=True)
    event_type: str = Field(index=True)
    from_ref: Optional[str] = Field(default=None, index=True)
    to_ref: Optional[str] = Field(default=None, index=True)
    actor: str = Field(default="system", index=True)
    reason: str = Field(default="", sa_column=Column(Text, nullable=False))
    evidence_refs: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    payload_json: dict = Field(default_factory=dict, sa_column=Column("payload", JSON, nullable=False))
    occurred_at: datetime = Field(default_factory=utc_now, index=True)


class Entity(SQLModel, table=True):
    __tablename__ = "entities"

    id: str = Field(primary_key=True)
    type: str = Field(index=True)
    name: str = Field(index=True)
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    source_refs: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryFact(SQLModel, table=True):
    __tablename__ = "memory_facts"

    id: str = Field(primary_key=True)
    subject_entity_id: str = Field(index=True)
    predicate: str = Field(index=True)
    object_value: str = Field(default="", sa_column=Column(Text, nullable=False))
    object_entity_id: Optional[str] = Field(default=None, index=True)
    confidence: Optional[float] = None
    valid_at: datetime = Field(default_factory=utc_now, index=True)
    invalid_at: Optional[datetime] = Field(default=None, index=True)
    superseded_by: Optional[str] = Field(default=None, index=True)
    evidence_refs: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="active", index=True)
    scope: str = Field(default="workspace", index=True)
    source_proposal_id: Optional[str] = Field(default=None, index=True)
    decision_ref: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryRelation(SQLModel, table=True):
    __tablename__ = "memory_relations"

    id: str = Field(primary_key=True)
    from_entity_id: str = Field(index=True)
    relation_type: str = Field(index=True)
    to_entity_id: str = Field(index=True)
    confidence: Optional[float] = None
    valid_at: datetime = Field(default_factory=utc_now, index=True)
    invalid_at: Optional[datetime] = Field(default=None, index=True)
    superseded_by: Optional[str] = Field(default=None, index=True)
    evidence_refs: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="active", index=True)
    scope: str = Field(default="workspace", index=True)
    source_proposal_id: Optional[str] = Field(default=None, index=True)
    decision_ref: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryConflict(SQLModel, table=True):
    __tablename__ = "memory_conflicts"

    id: str = Field(primary_key=True)
    conflict_type: str = Field(default="fact_conflict", index=True)
    fact_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    relation_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    reason: str = Field(default="", sa_column=Column(Text, nullable=False))
    status: str = Field(default="open", index=True)
    resolution: str = Field(default="", sa_column=Column(Text, nullable=False))
    scope: str = Field(default="workspace", index=True)
    decision_ref: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: Optional[datetime] = None


class SourceItem(SQLModel, table=True):
    __tablename__ = "source_items"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_items_source_external_id"),)

    id: str = Field(primary_key=True)
    source: str = Field(index=True)
    external_id: str = Field(index=True)
    kind: str = Field(index=True)
    title: str = ""
    content_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    content_html: str = Field(default="", sa_column=Column(Text, nullable=False))
    metadata_json: dict = Field(default_factory=dict, sa_column=Column("metadata", JSON, nullable=False))
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgeItem(SQLModel, table=True):
    __tablename__ = "knowledge_items"

    id: str = Field(primary_key=True)
    source_item_id: str = Field(index=True)
    card_id: Optional[str] = Field(default=None, index=True)
    title: str = ""
    summary: str = ""
    content: str = Field(default="", sa_column=Column(Text, nullable=False))
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    source: str = Field(index=True)
    source_ref: str = ""
    knowledge_type: str = Field(index=True)
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgePage(SQLModel, table=True):
    __tablename__ = "knowledge_pages"

    id: str = Field(primary_key=True)
    title: str = Field(index=True)
    summary: str = ""
    body: str = Field(default="", sa_column=Column(Text, nullable=False))
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="draft", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class KnowledgePageItemLink(SQLModel, table=True):
    __tablename__ = "knowledge_page_item_links"
    __table_args__ = (UniqueConstraint("page_id", "knowledge_item_id", name="uq_knowledge_page_item_link"),)

    id: str = Field(primary_key=True)
    page_id: str = Field(index=True)
    knowledge_item_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)


class Reflection(SQLModel, table=True):
    __tablename__ = "reflections"

    id: str = Field(primary_key=True)
    trigger_key: str = Field(index=True)
    title: str
    reason: str = Field(default="", sa_column=Column(Text, nullable=False))
    question: str = Field(default="", sa_column=Column(Text, nullable=False))
    related_knowledge_item_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    status: str = Field(default="pending", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: Optional[datetime] = None
