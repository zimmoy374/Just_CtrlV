from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from ..core.text import html_to_text
from ..models import SourceItem, utc_now


SOURCE_ITEM_SOURCES = {"second_brain", "external_ai"}
SOURCE_ITEM_KINDS = {
    "card_text",
    "card_link",
    "card_image",
    "external_ai_note",
    "task_event",
    "agent_handoff",
    "agent_selection",
}


def validate_choice(value: str, allowed: set[str], field_name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} 不支持：{value}")


def upsert_source_item(
    session: Session,
    *,
    source: str,
    external_id: str,
    kind: str,
    title: str = "",
    content_text: str = "",
    content_html: str = "",
    metadata: dict | None = None,
    status: str = "active",
) -> SourceItem:
    validate_choice(source, SOURCE_ITEM_SOURCES, "source")
    validate_choice(kind, SOURCE_ITEM_KINDS, "kind")
    clean_external_id = external_id.strip()
    if not clean_external_id:
        raise ValueError("externalId 不能为空")

    source_item = session.exec(
        select(SourceItem).where(SourceItem.source == source, SourceItem.external_id == clean_external_id),
    ).first()
    now = utc_now()
    if source_item:
        source_item.kind = kind
        source_item.title = title.strip()
        source_item.content_text = content_text or html_to_text(content_html)
        source_item.content_html = content_html or ""
        source_item.metadata_json = metadata or {}
        source_item.status = status
        source_item.updated_at = now
    else:
        source_item = SourceItem(
            id=str(uuid4()),
            source=source,
            external_id=clean_external_id,
            kind=kind,
            title=title.strip(),
            content_text=content_text or html_to_text(content_html),
            content_html=content_html or "",
            metadata_json=metadata or {},
            status=status,
        )
    session.add(source_item)
    session.flush()
    return source_item
