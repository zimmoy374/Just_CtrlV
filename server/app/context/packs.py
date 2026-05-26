from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from ..core.text import normalize_keyword
from ..models import KnowledgePage, KnowledgePageItemLink, SourceItem
from ..retrieval.engine import RetrievalEngine


PROTOCOL_REMINDER = [
    "Use this ContextPack as a scoped knowledge snapshot, not as a chat endpoint.",
    "Prefer related KnowledgePage summaries first, then KnowledgeItem evidence, then Source excerpts only when needed.",
    "Cite facts with the provided citationRefs. Do not assume omitted knowledge is absent from the full library.",
    "Do not request or infer a full-library dump for ordinary questions; narrow the query instead.",
]


def build_context_pack(
    session: Session,
    *,
    query: str,
    max_pages: int = 3,
    max_items: int = 6,
    max_source_excerpts: int = 3,
    max_chars: int = 4000,
) -> dict[str, Any]:
    trimmed = query.strip()
    budget = {
        "maxPages": max_pages,
        "maxItems": max_items,
        "maxSourceExcerpts": max_source_excerpts,
        "maxChars": max_chars,
        "usedChars": 0,
        "truncated": False,
    }
    pack: dict[str, Any] = {
        "query": trimmed,
        "protocolReminder": PROTOCOL_REMINDER,
        "relatedPages": [],
        "relatedItems": [],
        "sourceExcerpts": [],
        "budget": budget,
        "citationRefs": [],
    }
    citations: dict[str, dict[str, str]] = {}

    if not trimmed:
        return pack

    retrieval_results = RetrievalEngine().search(session, trimmed, limit=max(max_items * 3, max_items))
    candidate_item_ids = [result.knowledge_item.id for result in retrieval_results]
    page_candidates = _merge_pages(
        _direct_page_matches(session, trimmed),
        _related_pages(session, candidate_item_ids),
    )

    used_chars = 0
    for page in page_candidates:
        if len(pack["relatedPages"]) >= max_pages:
            budget["truncated"] = True
            break
        item_refs = _page_item_refs(session, page.id, set(candidate_item_ids))
        page_ref = f"page:{page.id}"
        page_payload = {
            "id": page.id,
            "title": page.title,
            "summary": page.summary,
            "status": page.status,
            "keywords": page.keywords or [],
            "updatedAt": page.updated_at,
            "citationRef": page_ref,
            "itemRefs": item_refs,
        }
        used_chars, added = _append_if_within_budget(pack["relatedPages"], page_payload, used_chars, max_chars)
        if not added:
            budget["truncated"] = True
            break
        citations[page_ref] = {"ref": page_ref, "kind": "knowledge_page", "id": page.id, "label": page.title}

    for result in retrieval_results:
        if len(pack["relatedItems"]) >= max_items:
            budget["truncated"] = True
            break
        knowledge_item = result.knowledge_item
        item_ref = f"item:{knowledge_item.id}"
        item_payload = {
            "id": knowledge_item.id,
            "title": knowledge_item.title,
            "summary": knowledge_item.summary,
            "excerpt": result.excerpt,
            "score": result.score,
            "matchedFields": result.matched_fields,
            "reason": result.reason,
            "source": result.source,
            "sourceRef": knowledge_item.source_ref,
            "citationRef": item_ref,
            "pageRefs": _item_page_refs(session, knowledge_item.id),
            "updatedAt": knowledge_item.updated_at,
        }
        used_chars, added = _append_if_within_budget(pack["relatedItems"], item_payload, used_chars, max_chars)
        if not added:
            budget["truncated"] = True
            break
        citations[item_ref] = {"ref": item_ref, "kind": "knowledge_item", "id": knowledge_item.id, "label": knowledge_item.title}

    for result in retrieval_results:
        if len(pack["sourceExcerpts"]) >= max_source_excerpts:
            budget["truncated"] = True
            break
        knowledge_item = result.knowledge_item
        source_item = session.get(SourceItem, knowledge_item.source_item_id)
        if not source_item or not source_item.content_text:
            continue
        excerpt = _excerpt_around(source_item.content_text, trimmed, limit=220)
        if not excerpt:
            continue
        source_ref = f"source:{source_item.id}"
        source_payload = {
            "id": source_ref,
            "sourceItemId": source_item.id,
            "knowledgeItemId": knowledge_item.id,
            "title": source_item.title,
            "kind": source_item.kind,
            "excerpt": excerpt,
            "citationRef": source_ref,
        }
        used_chars, added = _append_if_within_budget(pack["sourceExcerpts"], source_payload, used_chars, max_chars)
        if not added:
            budget["truncated"] = True
            break
        citations[source_ref] = {"ref": source_ref, "kind": "source_excerpt", "id": source_item.id, "label": source_item.title}

    if len(retrieval_results) > len(pack["relatedItems"]):
        budget["truncated"] = True
    if len(page_candidates) > len(pack["relatedPages"]):
        budget["truncated"] = True

    budget["usedChars"] = used_chars
    pack["citationRefs"] = list(citations.values())
    return pack


def _related_pages(session: Session, knowledge_item_ids: list[str]) -> list[KnowledgePage]:
    if not knowledge_item_ids:
        return []
    links = session.exec(
        select(KnowledgePageItemLink).where(KnowledgePageItemLink.knowledge_item_id.in_(knowledge_item_ids)),
    ).all()
    page_ids: list[str] = []
    for knowledge_item_id in knowledge_item_ids:
        for link in links:
            if link.knowledge_item_id == knowledge_item_id and link.page_id not in page_ids:
                page_ids.append(link.page_id)

    if not page_ids:
        return []
    pages = session.exec(select(KnowledgePage).where(KnowledgePage.id.in_(page_ids))).all()
    by_id = {page.id: page for page in pages if page.status != "archived"}
    return [by_id[page_id] for page_id in page_ids if page_id in by_id]


def _direct_page_matches(session: Session, query: str) -> list[KnowledgePage]:
    normalized_query = normalize_keyword(query)
    if not normalized_query:
        return []

    matches: list[tuple[float, KnowledgePage]] = []
    pages = session.exec(select(KnowledgePage)).all()
    for page in pages:
        if page.status == "archived":
            continue
        score = 0.0
        for keyword in page.keywords or []:
            normalized_keyword = normalize_keyword(keyword)
            if normalized_query == normalized_keyword:
                score = max(score, 100)
            elif normalized_query in normalized_keyword or normalized_keyword in normalized_query:
                score = max(score, 86)
        for value, value_score in [(page.title, 92), (page.summary, 72), (page.body, 58)]:
            if normalized_query in normalize_keyword(value or ""):
                score = max(score, value_score)
        if score > 0:
            matches.append((score, page))

    matches.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
    return [page for _score, page in matches]


def _merge_pages(*groups: list[KnowledgePage]) -> list[KnowledgePage]:
    pages: list[KnowledgePage] = []
    seen: set[str] = set()
    for group in groups:
        for page in group:
            if page.id in seen:
                continue
            pages.append(page)
            seen.add(page.id)
    return pages


def _page_item_refs(session: Session, page_id: str, relevant_item_ids: set[str]) -> list[str]:
    links = session.exec(select(KnowledgePageItemLink).where(KnowledgePageItemLink.page_id == page_id)).all()
    return [f"item:{link.knowledge_item_id}" for link in links if link.knowledge_item_id in relevant_item_ids]


def _item_page_refs(session: Session, knowledge_item_id: str) -> list[str]:
    links = session.exec(select(KnowledgePageItemLink).where(KnowledgePageItemLink.knowledge_item_id == knowledge_item_id)).all()
    page_ids = [link.page_id for link in links]
    if not page_ids:
        return []
    pages = session.exec(select(KnowledgePage).where(KnowledgePage.id.in_(page_ids), KnowledgePage.status != "archived")).all()
    active_page_ids = {page.id for page in pages}
    return [f"page:{link.page_id}" for link in links if link.page_id in active_page_ids]


def _append_if_within_budget(items: list[dict[str, Any]], payload: dict[str, Any], used_chars: int, max_chars: int) -> tuple[int, bool]:
    payload_chars = _char_count(payload)
    if used_chars + payload_chars > max_chars:
        return used_chars, False
    items.append(payload)
    return used_chars + payload_chars, True


def _char_count(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(_char_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_char_count(item) for item in value)
    return 0


def _excerpt_around(value: str, query: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    lowered = text.casefold()
    lowered_query = query.casefold()
    index = lowered.find(lowered_query) if lowered_query else -1
    if index < 0:
        return f"{text[:limit].rstrip()}..."
    start = max(0, index - 70)
    end = min(len(text), start + limit)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"
