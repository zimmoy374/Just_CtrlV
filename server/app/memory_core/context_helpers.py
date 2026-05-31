from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from ..core.text import normalize_keyword
from ..models import KnowledgePage, KnowledgePageItemLink


PROTOCOL_REMINDER = [
    "把这个 ContextPack 当作带范围的知识快照，不要当成聊天接口。",
    "优先使用规则、个人事实、流程经验、知识页和知识条目；只有需要核验证据时再读取原始证据摘录。",
    "回答时使用返回的 citationRefs 引用事实；不要把未返回的内容理解为知识库中不存在。",
    "普通问题不要请求或推断全库内容；应该缩小查询词，按需逐步读取。",
]


def related_pages(session: Session, knowledge_item_ids: list[str]) -> list[KnowledgePage]:
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


def direct_page_matches(session: Session, query: str) -> list[KnowledgePage]:
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


def merge_pages(*groups: list[KnowledgePage]) -> list[KnowledgePage]:
    pages: list[KnowledgePage] = []
    seen: set[str] = set()
    for group in groups:
        for page in group:
            if page.id in seen:
                continue
            pages.append(page)
            seen.add(page.id)
    return pages


def page_item_refs(session: Session, page_id: str, relevant_item_ids: set[str]) -> list[str]:
    links = session.exec(select(KnowledgePageItemLink).where(KnowledgePageItemLink.page_id == page_id)).all()
    return [f"item:{link.knowledge_item_id}" for link in links if link.knowledge_item_id in relevant_item_ids]


def item_page_refs(session: Session, knowledge_item_id: str) -> list[str]:
    links = session.exec(select(KnowledgePageItemLink).where(KnowledgePageItemLink.knowledge_item_id == knowledge_item_id)).all()
    page_ids = [link.page_id for link in links]
    if not page_ids:
        return []
    pages = session.exec(select(KnowledgePage).where(KnowledgePage.id.in_(page_ids), KnowledgePage.status != "archived")).all()
    active_page_ids = {page.id for page in pages}
    return [f"page:{link.page_id}" for link in links if link.page_id in active_page_ids]


def char_count(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(char_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(char_count(item) for item in value)
    return 0


def excerpt_around(value: str, query: str, limit: int) -> str:
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
