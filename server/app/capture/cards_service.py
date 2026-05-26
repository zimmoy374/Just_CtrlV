from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from ..core.text import compact_text
from ..knowledge_core.lifecycle import commit_knowledge_item
from ..knowledge_core.source_items import upsert_source_item
from ..models import Card, KnowledgeItem, SourceItem


@dataclass(frozen=True)
class CardKnowledgePayload:
    title: str
    kind: str
    source_content: str
    knowledge_content: str
    source_ref: str


def _card_payload(card: Card) -> CardKnowledgePayload:
    title = card.source_title or card.summary or compact_text(card.text_content or "", 40)
    if not title:
        title = "图片材料" if card.type == "image" else "知识卡片"

    if card.type == "link":
        kind = "card_link"
        source_content = "\n".join(
            part
            for part in [card.source_title or "", card.source_description or "", card.text_content or "", card.source_url or ""]
            if part
        )
        source_ref = card.source_url or card.id
        knowledge_content = source_content
    elif card.type == "image":
        kind = "card_image"
        source_content = card.image_filename or ""
        knowledge_content = card.summary or card.image_filename or "图片材料"
        source_ref = card.image_filename or card.id
    else:
        kind = "card_text"
        source_content = card.text_content or ""
        knowledge_content = source_content
        source_ref = card.id

    return CardKnowledgePayload(
        title=title,
        kind=kind,
        source_content=source_content,
        knowledge_content=knowledge_content,
        source_ref=source_ref,
    )


def sync_card_source_item(session: Session, card: Card) -> SourceItem:
    payload = _card_payload(card)
    return upsert_source_item(
        session,
        source="just_ctrl_v",
        external_id=card.id,
        kind=payload.kind,
        title=payload.title,
        content_text=payload.source_content,
        metadata={
            "weekKey": card.week_key,
            "cardType": card.type,
            "sourceUrl": card.source_url,
            "imageFilename": card.image_filename,
        },
        status="active",
    )

def card_has_formal_knowledge(card: Card) -> bool:
    return card.ai_status == "done" and bool(card.summary or card.keywords)


def commit_card_knowledge_item(session: Session, card: Card) -> KnowledgeItem | None:
    source_item = sync_card_source_item(session, card)
    if not card_has_formal_knowledge(card):
        return None

    payload = _card_payload(card)
    return commit_knowledge_item(
        session,
        source_item=source_item,
        knowledge_type="fragment",
        title=payload.title,
        summary=card.summary or "",
        content=payload.knowledge_content,
        keywords=card.keywords or [],
        source_ref=payload.source_ref,
        card_id=card.id,
        status="active",
    )
