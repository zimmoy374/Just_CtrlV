from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from sqlmodel import Session, select

from ..models import KnowledgeItem, SourceItem, utc_now
from .source_items import validate_choice


KNOWLEDGE_TYPES = {"fragment"}
KNOWLEDGE_ITEM_STATUSES = {"active", "merged", "archived"}


def upsert_knowledge_item(
    session: Session,
    *,
    source_item: SourceItem,
    knowledge_type: str,
    title: str,
    summary: str = "",
    content: str = "",
    keywords: Iterable[str] | None = None,
    source_ref: str = "",
    card_id: str | None = None,
    status: str = "active",
) -> KnowledgeItem:
    validate_choice(knowledge_type, KNOWLEDGE_TYPES, "knowledgeType")
    validate_choice(status, KNOWLEDGE_ITEM_STATUSES, "status")
    clean_keywords: list[str] = []
    for keyword in keywords or []:
        clean = str(keyword).strip()
        if clean and clean not in clean_keywords:
            clean_keywords.append(clean)

    knowledge_item = session.exec(select(KnowledgeItem).where(KnowledgeItem.source_item_id == source_item.id)).first()
    if not knowledge_item and card_id:
        knowledge_item = session.exec(select(KnowledgeItem).where(KnowledgeItem.card_id == card_id)).first()

    now = utc_now()
    if knowledge_item:
        knowledge_item.card_id = card_id
        knowledge_item.title = title.strip()
        knowledge_item.summary = summary.strip()
        knowledge_item.content = content.strip()
        knowledge_item.keywords = clean_keywords
        knowledge_item.source = source_item.source
        knowledge_item.source_ref = source_ref
        knowledge_item.knowledge_type = knowledge_type
        knowledge_item.status = status
        knowledge_item.updated_at = now
    else:
        knowledge_item = KnowledgeItem(
            id=str(uuid4()),
            source_item_id=source_item.id,
            card_id=card_id,
            title=title.strip(),
            summary=summary.strip(),
            content=content.strip(),
            keywords=clean_keywords,
            source=source_item.source,
            source_ref=source_ref,
            knowledge_type=knowledge_type,
            status=status,
        )

    session.add(knowledge_item)
    session.flush()
    return knowledge_item


def archive_card_knowledge_item(session: Session, card_id: str) -> KnowledgeItem | None:
    knowledge_item = session.exec(select(KnowledgeItem).where(KnowledgeItem.card_id == card_id)).first()
    if not knowledge_item:
        return None
    knowledge_item.status = "archived"
    knowledge_item.updated_at = utc_now()
    session.add(knowledge_item)
    session.flush()
    return knowledge_item
