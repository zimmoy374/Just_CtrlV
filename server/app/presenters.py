from __future__ import annotations

from .models import Card
from .schemas import CardResponse


def card_to_response(card: Card) -> CardResponse:
    return CardResponse(
        id=card.id,
        dayKey=card.day_key,
        type=card.type,
        textContent=card.text_content,
        imageUrl=f"/uploads/{card.image_filename}" if card.image_filename else None,
        sourceUrl=card.source_url,
        sourceTitle=card.source_title,
        sourceDescription=card.source_description,
        summary=card.summary,
        keywords=card.keywords or [],
        x=card.x,
        y=card.y,
        width=card.width,
        rotation=card.rotation,
        styleSeed=card.style_seed,
        aiStatus=card.ai_status,
        aiError=card.ai_error,
        createdAt=card.created_at,
        updatedAt=card.updated_at,
    )
