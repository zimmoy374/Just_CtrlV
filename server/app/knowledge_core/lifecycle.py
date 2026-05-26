from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session

from ..indexing.sqlite_fts import refresh_knowledge_search_index
from ..models import KnowledgeItem, SourceItem
from ..organization.suggestions import maybe_create_reflections, refresh_reflections_after_item_archive
from ..wiki.pages import refresh_pages_after_item_archive
from .knowledge_items import archive_card_knowledge_item as archive_card_knowledge_item_asset
from .knowledge_items import upsert_knowledge_item


def commit_knowledge_item(
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
    knowledge_item = upsert_knowledge_item(
        session,
        source_item=source_item,
        knowledge_type=knowledge_type,
        title=title,
        summary=summary,
        content=content,
        keywords=keywords,
        source_ref=source_ref,
        card_id=card_id,
        status=status,
    )
    refresh_knowledge_search_index(session, knowledge_item)
    maybe_create_reflections(session)
    return knowledge_item


def archive_card_knowledge_item(session: Session, card_id: str) -> None:
    knowledge_item = archive_card_knowledge_item_asset(session, card_id)
    if knowledge_item:
        refresh_knowledge_search_index(session, knowledge_item)
        refresh_pages_after_item_archive(session, knowledge_item.id)
        refresh_reflections_after_item_archive(session, knowledge_item.id)
