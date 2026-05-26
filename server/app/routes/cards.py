from __future__ import annotations

import mimetypes
import random
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from ..analysis.jobs import enqueue_card_analysis, run_analysis_job
from ..capture.cards_service import commit_card_knowledge_item, sync_card_source_item
from ..database import get_session
from ..knowledge_core.lifecycle import archive_card_knowledge_item
from ..link_preview import LinkPreviewError, fetch_link_preview
from ..models import Card, utc_now
from ..presenters import card_to_response
from ..schemas import CardPatch, CardResponse, LinkCardCreate, TextCardCreate
from ..settings import settings


router = APIRouter()

KNOWLEDGE_PATCH_FIELDS = {
    "summary",
    "keywords",
}

SOURCE_PATCH_FIELDS = {
    "text_content",
    "source_url",
    "source_title",
    "source_description",
}


def new_card_base(week_key: str, card_type: str, x: float, y: float) -> Card:
    seed = uuid4().hex[:10]
    return Card(
        id=str(uuid4()),
        week_key=week_key,
        type=card_type,
        x=x,
        y=y,
        width=320 if card_type == "link" else 300 if card_type == "text" else 280,
        rotation=random.choice([-3, -2, -1, 1, 2, 3]),
        style_seed=seed,
        ai_status="pending",
        keywords=[],
    )


@router.get("/api/weeks/{week_key}/cards", response_model=list[CardResponse])
def list_cards(week_key: str, session: Session = Depends(get_session)) -> list[CardResponse]:
    statement = select(Card).where(Card.week_key == week_key).order_by(Card.created_at)
    cards = session.exec(statement).all()
    return [card_to_response(card) for card in cards]


@router.post("/api/cards/text", response_model=CardResponse)
def create_text_card(
    payload: TextCardCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> CardResponse:
    card = new_card_base(payload.week_key, "text", payload.x, payload.y)
    card.text_content = payload.text_content.strip()
    if not card.text_content:
        raise HTTPException(status_code=400, detail="文本不能为空")

    session.add(card)
    session.flush()
    sync_card_source_item(session, card)
    job = enqueue_card_analysis(session, card, reason="card_created")
    job_id = job.id
    session.commit()
    session.refresh(card)
    background_tasks.add_task(run_analysis_job, job_id)
    return card_to_response(card)


@router.post("/api/cards/link", response_model=CardResponse)
def create_link_card(
    payload: LinkCardCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> CardResponse:
    try:
        preview = fetch_link_preview(payload.url)
    except LinkPreviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    card = new_card_base(payload.week_key, "link", payload.x, payload.y)
    card.source_url = preview["url"]
    card.source_title = preview.get("title") or preview["url"]
    card.source_description = preview.get("description") or ""
    card.text_content = preview.get("content") or card.source_description or card.source_title

    session.add(card)
    session.flush()
    sync_card_source_item(session, card)
    job = enqueue_card_analysis(session, card, reason="card_created")
    job_id = job.id
    session.commit()
    session.refresh(card)
    background_tasks.add_task(run_analysis_job, job_id)
    return card_to_response(card)


@router.post("/api/cards/image", response_model=CardResponse)
async def create_image_card(
    background_tasks: BackgroundTasks,
    week_key: str = Form(..., alias="weekKey"),
    x: float = Form(120),
    y: float = Form(120),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> CardResponse:
    if file.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=400, detail="仅支持 PNG、JPEG、WebP 图片")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="图片不能超过 10MB")

    extension = mimetypes.guess_extension(file.content_type or "") or ".png"
    filename = f"{uuid4().hex}{extension}"
    destination = Path(settings.upload_dir) / filename
    destination.write_bytes(content)

    card = new_card_base(week_key, "image", x, y)
    card.image_filename = filename
    session.add(card)
    session.flush()
    sync_card_source_item(session, card)
    job = enqueue_card_analysis(session, card, reason="card_created")
    job_id = job.id
    session.commit()
    session.refresh(card)
    background_tasks.add_task(run_analysis_job, job_id)
    return card_to_response(card)


@router.patch("/api/cards/{card_id}", response_model=CardResponse)
def patch_card(
    card_id: str,
    payload: CardPatch,
    session: Session = Depends(get_session),
) -> CardResponse:
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    updates = payload.model_dump(exclude_unset=True, by_alias=False)
    for field, value in updates.items():
        setattr(card, field, value)
    card.updated_at = utc_now()
    session.add(card)
    if set(updates) & KNOWLEDGE_PATCH_FIELDS:
        commit_card_knowledge_item(session, card)
    elif set(updates) & SOURCE_PATCH_FIELDS:
        sync_card_source_item(session, card)
    session.commit()
    session.refresh(card)
    return card_to_response(card)


@router.post("/api/cards/{card_id}/analyze", response_model=CardResponse)
def retry_analyze_card(
    card_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> CardResponse:
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    sync_card_source_item(session, card)
    job = enqueue_card_analysis(session, card, reason="manual_retry")
    job_id = job.id
    session.commit()
    session.refresh(card)
    background_tasks.add_task(run_analysis_job, job_id)
    return card_to_response(card)


@router.delete("/api/cards/{card_id}", status_code=204)
def delete_card(card_id: str, session: Session = Depends(get_session)) -> None:
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    if card.image_filename:
        image_path = Path(settings.upload_dir) / card.image_filename
        if image_path.exists():
            image_path.unlink()

    archive_card_knowledge_item(session, card.id)
    session.delete(card)
    session.commit()
