from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from sqlmodel import Session


CURRENT_MEMORY_REF_KINDS = {
    "source",
    "item",
    "page",
    "store",
    "task",
    "task-event",
    "checkpoint",
    "handoff",
    "proposal",
}

FUTURE_MEMORY_REF_KINDS = {
    "entity",
    "fact",
    "relation",
    "conflict",
    "decision",
    "provenance",
    "rule",
    "procedure",
}

MEMORY_REF_KINDS = CURRENT_MEMORY_REF_KINDS | FUTURE_MEMORY_REF_KINDS

MEMORY_TARGET_STORES = {
    "semantic_knowledge",
    "rule_preference",
    "procedure_lesson",
}

DEFAULT_PROPOSAL_TARGET_STORES = {
    "page_update": "semantic_knowledge",
    "technical_decision": "semantic_knowledge",
    "environment_fact": "semantic_knowledge",
    "user_preference": "rule_preference",
    "project_rule": "rule_preference",
    "lesson": "procedure_lesson",
    "pitfall": "procedure_lesson",
    "workflow_pattern": "procedure_lesson",
}


@dataclass(frozen=True, slots=True)
class MemoryRef:
    kind: str
    id: str

    def __post_init__(self) -> None:
        if self.kind not in MEMORY_REF_KINDS:
            raise ValueError(f"Unsupported memory ref kind: {self.kind}")
        if not self.id:
            raise ValueError("MemoryRef id cannot be empty")

    @classmethod
    def parse(cls, value: str) -> "MemoryRef":
        prefix, separator, ref_id = value.partition(":")
        if not separator or not prefix or not ref_id:
            raise ValueError(f"Invalid memory ref: {value}")
        return cls(kind=prefix, id=ref_id)

    @classmethod
    def parse_many(cls, values: Iterable[str]) -> list["MemoryRef"]:
        refs: list[MemoryRef] = []
        for value in values:
            if not value:
                continue
            refs.append(cls.parse(value))
        return refs

    def __str__(self) -> str:
        return f"{self.kind}:{self.id}"


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    text: str = ""
    scope: str | None = None
    task_session_id: str | None = None
    limit: int = 20
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def trimmed_text(self) -> str:
        return self.text.strip()


@dataclass(frozen=True, slots=True)
class MemoryEpisodeInput:
    id: str | None = None
    source: str = ""
    source_ref: str = ""
    actor: str = "user"
    occurred_at: datetime | None = None
    kind: str = ""
    title: str = ""
    content_text: str = ""
    content_html: str = ""
    media_refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    scope: str | None = None
    visibility: str = "workspace"
    privacy_labels: list[str] = field(default_factory=list)
    retention_policy: str | None = None


@dataclass(frozen=True, slots=True)
class MemorySlice:
    store: str
    kind: str
    ref: MemoryRef
    title: str = ""
    summary: str = ""
    excerpt: str = ""
    score: float = 0.0
    reason: str = ""
    scope: str | None = None
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    evidence_refs: list[str] = field(default_factory=list)
    citation_ref: str | None = None
    decision_ref: str | None = None
    visibility: str = "workspace"
    privacy_labels: list[str] = field(default_factory=list)
    staleness: str | None = None
    conflict_refs: list[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def with_ref_strings(self) -> dict[str, Any]:
        return {
            "store": self.store,
            "kind": self.kind,
            "ref": str(self.ref),
            "title": self.title,
            "summary": self.summary,
            "excerpt": self.excerpt,
            "score": self.score,
            "reason": self.reason,
            "scope": self.scope,
            "validAt": self.valid_at,
            "invalidAt": self.invalid_at,
            "evidenceRefs": self.evidence_refs,
            "citationRef": self.citation_ref,
            "decisionRef": self.decision_ref,
            "visibility": self.visibility,
            "privacyLabels": self.privacy_labels,
            "staleness": self.staleness,
            "conflictRefs": self.conflict_refs,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class MemoryDecisionRecord:
    id: str | None = None
    decision_type: str = ""
    target_ref: str = ""
    actor: str = ""
    reason: str = ""
    policy: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float | None = None
    scope: str | None = None
    created_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProvenanceEvent:
    id: str | None = None
    event_type: str = ""
    from_ref: str | None = None
    to_ref: str | None = None
    actor: str = ""
    reason: str = ""
    occurred_at: datetime | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    hash: str | None = None
    previous_hash: str | None = None


@runtime_checkable
class MemoryStore(Protocol):
    name: str

    def retrieve(self, session: Session, query: MemoryQuery) -> list[MemorySlice]:
        ...

    def get(self, session: Session, ref: MemoryRef) -> Any | None:
        ...

    def export(self, session: Session) -> list[Mapping[str, Any]]:
        ...

    def rebuild_projection(self, session: Session) -> Mapping[str, Any]:
        ...
