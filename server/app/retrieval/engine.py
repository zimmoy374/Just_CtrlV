from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Literal, Protocol

from sqlalchemy import func
from sqlmodel import Session, select

from ..core.text import normalize_keyword
from ..indexing.sqlite_fts import SqliteFtsIndex
from ..models import KnowledgeItem
from .fusion import reciprocal_rank_fusion
from .rerank import RetrievalCandidate, rerank_candidate
from .vector import LocalVectorSearch

SEARCHABLE_KNOWLEDGE_STATUSES = {"active"}
RetrievalMode = Literal["lexical", "vector", "hybrid"]
_SNAPSHOT_CACHE_LIMIT = 8


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


@dataclass(frozen=True)
class _NormalizedKnowledgeText:
    keywords: tuple[tuple[str, str], ...]
    title: str
    summary: str
    content: str
    source_ref: str


@dataclass(frozen=True)
class _KnowledgeSnapshot:
    cache_key: str
    items: tuple[KnowledgeItem, ...]
    by_id: dict[str, KnowledgeItem]
    normalized_by_id: dict[str, _NormalizedKnowledgeText]


class RetrievalEngine:
    _snapshot_cache: OrderedDict[str, _KnowledgeSnapshot] = OrderedDict()
    _snapshot_lock = RLock()

    def __init__(
        self,
        index: KnowledgeIndexProvider | None = None,
        *,
        vector_search: LocalVectorSearch | None = None,
        mode: RetrievalMode = "hybrid",
    ) -> None:
        self.index = index or SqliteFtsIndex()
        self.vector_search = vector_search or LocalVectorSearch()
        self.mode = mode

    def search(self, session: Session, query: str, limit: int = 80) -> list[RetrievalResult]:
        trimmed = query.strip()
        if not trimmed:
            return []

        snapshot = self._active_snapshot(session)
        knowledge_items = list(snapshot.items)
        by_id = snapshot.by_id
        lexical_candidates = self._lexical_candidates(
            session,
            trimmed,
            knowledge_items,
            normalized_by_id=snapshot.normalized_by_id,
            limit=limit * 3,
        )
        vector_candidates = self._vector_candidates(trimmed, knowledge_items, limit=limit * 3, cache_key=snapshot.cache_key)

        lexical_ranking = [item_id for item_id, _score, _fields in sorted(lexical_candidates, key=lambda item: (-item[1], item[0]))]
        vector_ranking = [candidate.knowledge_item_id for candidate in vector_candidates]
        if self.mode == "lexical":
            fused_scores = reciprocal_rank_fusion([lexical_ranking])
            candidate_ids = set(lexical_ranking)
        elif self.mode == "vector":
            fused_scores = reciprocal_rank_fusion([vector_ranking])
            candidate_ids = set(vector_ranking)
        else:
            fused_scores = reciprocal_rank_fusion([lexical_ranking, vector_ranking])
            candidate_ids = set(lexical_ranking) | set(vector_ranking)

        lexical_by_id = {item_id: (score, fields) for item_id, score, fields in lexical_candidates}
        vector_by_id = {candidate.knowledge_item_id: candidate for candidate in vector_candidates}
        candidates: list[RetrievalCandidate] = []
        for item_id in candidate_ids:
            knowledge_item = by_id.get(item_id)
            if not knowledge_item:
                continue
            lexical_score, matched_fields = lexical_by_id.get(item_id, (0.0, []))
            vector_candidate = vector_by_id.get(item_id)
            candidate = RetrievalCandidate(
                knowledge_item=knowledge_item,
                lexical_score=lexical_score,
                vector_score=vector_candidate.score if vector_candidate else 0.0,
                fusion_score=fused_scores.get(item_id, 0.0),
                matched_fields=list(matched_fields),
                vector_features=vector_candidate.matched_features if vector_candidate else [],
                used_lexical=item_id in lexical_by_id,
                used_vector=vector_candidate is not None,
            )
            if candidate.used_vector:
                candidate.matched_fields.append("向量召回")
            if candidate.used_lexical and candidate.used_vector:
                candidate.matched_fields.append("RRF融合")
            candidates.append(candidate)

        results: list[RetrievalResult] = []
        for candidate in candidates:
            score = rerank_candidate(candidate)
            if score <= 0:
                continue
            fields = sorted(set(candidate.matched_fields))
            results.append(
                RetrievalResult(
                    knowledge_item=candidate.knowledge_item,
                    score=score,
                    matched_fields=fields,
                    excerpt=self._build_excerpt(candidate.knowledge_item, trimmed, fields),
                    reason=self._build_reason(candidate),
                    source=candidate.knowledge_item.source_ref or candidate.knowledge_item.source,
                ),
            )

        results.sort(key=lambda item: (-item.score, item.knowledge_item.created_at))
        return results[:limit]

    @classmethod
    def clear_cache(cls) -> None:
        with cls._snapshot_lock:
            cls._snapshot_cache.clear()
        LocalVectorSearch.clear_cache()

    def _active_snapshot(self, session: Session) -> _KnowledgeSnapshot:
        bind = session.get_bind()
        count_value, max_updated_at = session.exec(
            select(func.count(KnowledgeItem.id), func.max(KnowledgeItem.updated_at)).where(
                KnowledgeItem.status.in_(SEARCHABLE_KNOWLEDGE_STATUSES),
            ),
        ).one()
        cache_key = f"{id(bind)}:{bind.url}:{int(count_value or 0)}:{max_updated_at or ''}"
        with self._snapshot_lock:
            cached = self._snapshot_cache.get(cache_key)
            if cached is not None:
                self._snapshot_cache.move_to_end(cache_key)
                return cached

        items = tuple(
            _detached_knowledge_item(item)
            for item in session.exec(
                select(KnowledgeItem).where(KnowledgeItem.status.in_(SEARCHABLE_KNOWLEDGE_STATUSES)),
            ).all()
        )
        snapshot = _KnowledgeSnapshot(
            cache_key=cache_key,
            items=items,
            by_id={item.id: item for item in items},
            normalized_by_id={item.id: _normalized_text(item) for item in items},
        )
        with self._snapshot_lock:
            self._snapshot_cache[cache_key] = snapshot
            if len(self._snapshot_cache) > _SNAPSHOT_CACHE_LIMIT:
                self._snapshot_cache.popitem(last=False)
        return snapshot

    def _lexical_candidates(
        self,
        session: Session,
        query: str,
        knowledge_items: list[KnowledgeItem],
        *,
        normalized_by_id: dict[str, _NormalizedKnowledgeText],
        limit: int,
    ) -> list[tuple[str, float, list[str]]]:
        if self.mode == "vector":
            return []
        indexed_ids = self.index.search_knowledge_item_ids(session, query, limit)
        indexed_id_set = set(indexed_ids)
        normalized_query = normalize_keyword(query)
        candidates: list[tuple[str, float, list[str]]] = []
        for knowledge_item in self._order_candidates(knowledge_items, indexed_ids):
            matched_fields, score = self._score_knowledge_item(
                knowledge_item,
                normalized_query,
                indexed_id_set,
                normalized_by_id.get(knowledge_item.id),
            )
            if score <= 0:
                continue
            candidates.append((knowledge_item.id, score, sorted(set(matched_fields))))
        candidates.sort(key=lambda item: (-item[1], item[0]))
        return candidates[:limit]

    def _vector_candidates(self, query: str, knowledge_items: list[KnowledgeItem], *, limit: int, cache_key: str | None = None):
        if self.mode == "lexical":
            return []
        return self.vector_search.search(knowledge_items, query, limit=limit, collection_cache_key=cache_key)

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
        normalized_text: _NormalizedKnowledgeText | None = None,
    ) -> tuple[list[str], float]:
        fields: list[str] = []
        score = 0.0
        normalized_text = normalized_text or _normalized_text(knowledge_item)

        for keyword, normalized_keyword in normalized_text.keywords:
            if not normalized_keyword:
                continue
            if normalized_query == normalized_keyword:
                fields.append(f"关键词：{keyword}")
                score = max(score, 100)
            elif normalized_query and (normalized_query in normalized_keyword or normalized_keyword in normalized_query):
                fields.append(f"关键词部分：{keyword}")
                score = max(score, 68)

        for field_name, value, field_score in [
            ("标题", normalized_text.title, 82),
            ("摘要", normalized_text.summary, 76),
            ("正文", normalized_text.content, 64),
            ("来源", normalized_text.source_ref, 48),
        ]:
            if normalized_query and normalized_query in value:
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

    def _build_reason(self, candidate: RetrievalCandidate) -> str:
        parts: list[str] = []
        lexical_fields = [field for field in candidate.matched_fields if field not in {"向量召回", "RRF融合"}]
        if lexical_fields:
            parts.append(f"lexical matched {', '.join(sorted(set(lexical_fields)))}")
        if candidate.used_vector:
            features = ", ".join(candidate.vector_features[:4])
            suffix = f" ({features})" if features else ""
            parts.append(f"vector recall score {candidate.vector_score:.3f}{suffix}")
        if candidate.used_lexical and candidate.used_vector:
            parts.append("fused by RRF")
        return "；".join(parts) if parts else "matched retrieval pipeline"


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


def _normalized_text(knowledge_item: KnowledgeItem) -> _NormalizedKnowledgeText:
    return _NormalizedKnowledgeText(
        keywords=tuple((keyword, normalize_keyword(keyword)) for keyword in knowledge_item.keywords or []),
        title=normalize_keyword(knowledge_item.title or ""),
        summary=normalize_keyword(knowledge_item.summary or ""),
        content=normalize_keyword(knowledge_item.content or ""),
        source_ref=normalize_keyword(knowledge_item.source_ref or ""),
    )


def _detached_knowledge_item(knowledge_item: KnowledgeItem) -> KnowledgeItem:
    return KnowledgeItem(
        id=knowledge_item.id,
        source_item_id=knowledge_item.source_item_id,
        card_id=knowledge_item.card_id,
        title=knowledge_item.title,
        summary=knowledge_item.summary,
        content=knowledge_item.content,
        keywords=list(knowledge_item.keywords or []),
        source=knowledge_item.source,
        source_ref=knowledge_item.source_ref,
        knowledge_type=knowledge_item.knowledge_type,
        status=knowledge_item.status,
        created_at=knowledge_item.created_at,
        updated_at=knowledge_item.updated_at,
    )
