from __future__ import annotations

import mimetypes
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from ..analysis.jobs import enqueue_card_analysis, run_analysis_job
from ..database import get_session
from ..link_preview import LinkPreviewError, fetch_link_preview
from ..models import Card, utc_now
from ..presenters import card_to_response
from ..schemas import CardPatch, CardResponse, LinkCardCreate, TextCardCreate
from ..settings import settings


router = APIRouter()


def validate_day_key(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式必须是 YYYY-MM-DD") from exc


def new_card(card_type: str, day_key: str, x: float, y: float) -> Card:
    return Card(
        id=str(uuid4()),
        day_key=validate_day_key(day_key),
        type=card_type,
        x=x,
        y=y,
        width=320 if card_type == "link" else 300 if card_type == "text" else 280,
        rotation=0,
        style_seed=uuid4().hex[:10],
        ai_status="pending",
        keywords=[],
    )


def save_and_analyze(session: Session, card: Card, background_tasks: BackgroundTasks) -> CardResponse:
    session.add(card)
    session.flush()
    job = enqueue_card_analysis(session, card, reason="card_created")
    session.commit()
    session.refresh(card)
    background_tasks.add_task(run_analysis_job, job.id)
    return card_to_response(card)


@router.get("/api/days", response_model=list[str])
def list_active_days(session: Session = Depends(get_session)) -> list[str]:
    return list(session.exec(select(Card.day_key).distinct().order_by(Card.day_key)).all())


@router.get("/api/days/{day_key}/cards", response_model=list[CardResponse])
def list_cards(day_key: str, session: Session = Depends(get_session)) -> list[CardResponse]:
    clean_day_key = validate_day_key(day_key)
    cards = session.exec(select(Card).where(Card.day_key == clean_day_key).order_by(Card.created_at)).all()
    return [card_to_response(card) for card in cards]


@router.post("/api/cards/text", response_model=CardResponse)
def create_text_card(
    payload: TextCardCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> CardResponse:
    card = new_card("text", payload.day_key, payload.x, payload.y)
    card.text_content = payload.text_content.strip()
    if not card.text_content:
        raise HTTPException(status_code=400, detail="文本不能为空")
    return save_and_analyze(session, card, background_tasks)


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

    card = new_card("link", payload.day_key, payload.x, payload.y)
    card.source_url = preview["url"]
    card.source_title = preview.get("title") or preview["url"]
    card.source_description = preview.get("description") or ""
    card.text_content = preview.get("content") or card.source_description or card.source_title
    return save_and_analyze(session, card, background_tasks)


@router.post("/api/cards/image", response_model=CardResponse)
async def create_image_card(
    background_tasks: BackgroundTasks,
    day_key: str = Form(..., alias="dayKey"),
    x: float = Form(0.12),
    y: float = Form(0.16),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> CardResponse:
    if not 0 <= x <= 1 or not 0 <= y <= 1:
        raise HTTPException(status_code=422, detail="卡片位置必须在页面范围内")
    if file.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=400, detail="仅支持 PNG、JPEG、WebP 图片")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="图片不能超过 10MB")

    extension = mimetypes.guess_extension(file.content_type or "") or ".png"
    filename = f"{uuid4().hex}{extension}"
    (Path(settings.upload_dir) / filename).write_bytes(content)

    card = new_card("image", day_key, x, y)
    card.image_filename = filename
    return save_and_analyze(session, card, background_tasks)


@router.patch("/api/cards/{card_id}", response_model=CardResponse)
def patch_card(card_id: str, payload: CardPatch, session: Session = Depends(get_session)) -> CardResponse:
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    updates = payload.model_dump(exclude_unset=True, by_alias=False)
    for field, value in updates.items():
        setattr(card, field, value)
    card.updated_at = utc_now()
    session.add(card)
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
    job = enqueue_card_analysis(session, card, reason="manual_retry")
    session.commit()
    session.refresh(card)
    background_tasks.add_task(run_analysis_job, job.id)
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

    session.delete(card)
    session.commit()
