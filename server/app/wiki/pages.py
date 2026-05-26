from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from sqlmodel import Session, select

from ..models import KnowledgeItem, KnowledgePage, KnowledgePageItemLink, utc_now


KNOWLEDGE_PAGE_STATUSES = {"draft", "active", "stale", "archived"}
ACTIVE_KNOWLEDGE_ITEM_STATUSES = {"active"}


def clean_keywords(keywords: Iterable[str] | None) -> list[str]:
    cleaned: list[str] = []
    for keyword in keywords or []:
        value = str(keyword).strip()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned


def upsert_knowledge_page(
    session: Session,
    *,
    title: str,
    summary: str = "",
    body: str = "",
    keywords: Iterable[str] | None = None,
    status: str = "draft",
) -> KnowledgePage:
    if status not in KNOWLEDGE_PAGE_STATUSES:
        raise ValueError(f"KnowledgePage status 不支持：{status}")

    clean_title = title.strip()
    if not clean_title:
        raise ValueError("KnowledgePage title 不能为空")
    page = session.exec(select(KnowledgePage).where(KnowledgePage.title == clean_title)).first()
    now = utc_now()
    if page:
        page.summary = summary.strip() or page.summary
        page.body = body.strip() or page.body
        page.keywords = clean_keywords([*(page.keywords or []), *(keywords or [])])
        if page.status == "draft" or status != "draft":
            page.status = status
        page.updated_at = now
    else:
        page = KnowledgePage(
            id=str(uuid4()),
            title=clean_title,
            summary=summary.strip(),
            body=body.strip(),
            keywords=clean_keywords(keywords),
            status=status,
        )
    session.add(page)
    session.flush()
    return page


def link_items_to_page(session: Session, page: KnowledgePage, knowledge_item_ids: Iterable[str]) -> None:
    active_item_ids = _active_knowledge_item_ids(session, knowledge_item_ids)
    existing_links = {
        link.knowledge_item_id
        for link in session.exec(select(KnowledgePageItemLink).where(KnowledgePageItemLink.page_id == page.id)).all()
    }
    for knowledge_item_id in active_item_ids:
        if knowledge_item_id in existing_links:
            continue
        session.add(KnowledgePageItemLink(id=str(uuid4()), page_id=page.id, knowledge_item_id=knowledge_item_id))
    session.flush()


def refresh_pages_after_item_archive(session: Session, knowledge_item_id: str) -> None:
    links = session.exec(
        select(KnowledgePageItemLink).where(KnowledgePageItemLink.knowledge_item_id == knowledge_item_id),
    ).all()
    for link in links:
        page = session.get(KnowledgePage, link.page_id)
        if not page or page.status == "archived":
            continue
        active_count = count_active_page_items(session, page.id)
        page.status = "archived" if active_count == 0 and not (page.body or "").strip() else "stale"
        page.updated_at = utc_now()
        session.add(page)
    session.flush()


def count_active_page_items(session: Session, page_id: str) -> int:
    links = session.exec(select(KnowledgePageItemLink).where(KnowledgePageItemLink.page_id == page_id)).all()
    if not links:
        return 0
    active_item_ids = _active_knowledge_item_ids(session, [link.knowledge_item_id for link in links])
    return len(active_item_ids)


def _active_knowledge_item_ids(session: Session, knowledge_item_ids: Iterable[str]) -> list[str]:
    requested_ids = [knowledge_item_id for knowledge_item_id in dict.fromkeys(knowledge_item_ids) if knowledge_item_id]
    if not requested_ids:
        return []
    active_items = session.exec(
        select(KnowledgeItem).where(
            KnowledgeItem.id.in_(requested_ids),
            KnowledgeItem.status.in_(ACTIVE_KNOWLEDGE_ITEM_STATUSES),
        ),
    ).all()
    active_ids = {item.id for item in active_items}
    return [knowledge_item_id for knowledge_item_id in requested_ids if knowledge_item_id in active_ids]
