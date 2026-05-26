from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlmodel import Session, select

from ..core.text import normalize_keyword
from ..indexing.sqlite_fts import SqliteFtsIndex
from ..models import KnowledgeItem

SEARCHABLE_KNOWLEDGE_STATUSES = {"active"}


class KnowledgeIndexProvider(Protocol):
    def search_knowledge_item_ids(self, session: Session, query: str, limit: int) -> list[str]:
        ...


@dataclass(frozen=True)
class RetrievalResult:
    knowledge_item: KnowledgeItem
    score: float
    matched_fields: list[str]
    excerpt: str
    reason: str
    source: str


class RetrievalEngine:
    def __init__(self, index: KnowledgeIndexProvider | None = None) -> None:
        self.index = index or SqliteFtsIndex()

    def search(self, session: Session, query: str, limit: int = 80) -> list[RetrievalResult]:
        trimmed = query.strip()
        if not trimmed:
            return []

        indexed_knowledge_item_ids = self.index.search_knowledge_item_ids(session, trimmed, limit)
        knowledge_items = session.exec(select(KnowledgeItem).where(KnowledgeItem.status.in_(SEARCHABLE_KNOWLEDGE_STATUSES))).all()
        ordered = self._order_candidates(knowledge_items, indexed_knowledge_item_ids)

        normalized_query = normalize_keyword(trimmed)
        indexed_id_set = set(indexed_knowledge_item_ids)
        results: list[RetrievalResult] = []
        for knowledge_item in ordered:
            matched_fields, score = self._score_knowledge_item(knowledge_item, normalized_query, indexed_id_set)
            if score <= 0:
                continue
            fields = sorted(set(matched_fields))
            results.append(
                RetrievalResult(
                    knowledge_item=knowledge_item,
                    score=score,
                    matched_fields=fields,
                    excerpt=self._build_excerpt(knowledge_item, trimmed, fields),
                    reason=self._build_reason(fields, knowledge_item.id in indexed_id_set),
                    source=knowledge_item.source_ref or knowledge_item.source,
                ),
            )

        results.sort(key=lambda item: (-item.score, item.knowledge_item.created_at))
        return results[:limit]

    def _order_candidates(self, knowledge_items: list[KnowledgeItem], indexed_knowledge_item_ids: list[str]) -> list[KnowledgeItem]:
        by_id = {knowledge_item.id: knowledge_item for knowledge_item in knowledge_items}
        ordered: list[KnowledgeItem] = [
            by_id[knowledge_item_id] for knowledge_item_id in indexed_knowledge_item_ids if knowledge_item_id in by_id
        ]
        seen = {knowledge_item.id for knowledge_item in ordered}
        ordered.extend(knowledge_item for knowledge_item in knowledge_items if knowledge_item.id not in seen)
        return ordered

    def _score_knowledge_item(
        self,
        knowledge_item: KnowledgeItem,
        normalized_query: str,
        indexed_knowledge_item_ids: set[str],
    ) -> tuple[list[str], float]:
        fields: list[str] = []
        score = 0.0

        for keyword in knowledge_item.keywords or []:
            normalized_keyword = normalize_keyword(keyword)
            if not normalized_keyword:
                continue
            if normalized_query == normalized_keyword:
                fields.append(f"关键词：{keyword}")
                score = max(score, 100)
            elif normalized_query and (normalized_query in normalized_keyword or normalized_keyword in normalized_query):
                fields.append(f"关键词：{keyword}")
                score = max(score, 88)

        for field_name, value, field_score in [
            ("标题", knowledge_item.title, 82),
            ("摘要", knowledge_item.summary, 76),
            ("正文", knowledge_item.content, 64),
            ("来源", knowledge_item.source_ref, 48),
        ]:
            normalized_value = normalize_keyword(value or "")
            if normalized_query and normalized_query in normalized_value:
                fields.append(field_name)
                score = max(score, field_score)

        if knowledge_item.id in indexed_knowledge_item_ids:
            fields.append("全文索引")
            score = max(score, 60)

        return fields, score

    def _build_excerpt(self, knowledge_item: KnowledgeItem, query: str, matched_fields: list[str]) -> str:
        for label, value in [
            ("标题", knowledge_item.title),
            ("摘要", knowledge_item.summary),
            ("正文", knowledge_item.content),
            ("来源", knowledge_item.source_ref),
        ]:
            if label in matched_fields and value:
                return _excerpt_around(value, query)
        for value in [knowledge_item.summary, knowledge_item.content, knowledge_item.title, knowledge_item.source_ref]:
            if value:
                return _excerpt_around(value, query)
        return ""

    def _build_reason(self, matched_fields: list[str], used_index: bool) -> str:
        field_text = "、".join(matched_fields)
        if used_index:
            return f"命中全文索引，并匹配：{field_text}"
        return f"匹配：{field_text}"


def _excerpt_around(value: str, query: str, limit: int = 160) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    lowered = text.casefold()
    lowered_query = query.casefold()
    index = lowered.find(lowered_query) if lowered_query else -1
    if index < 0:
        return f"{text[:limit].rstrip()}..."
    start = max(0, index - 48)
    end = min(len(text), start + limit)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"
