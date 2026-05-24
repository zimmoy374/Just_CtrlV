from __future__ import annotations

import mimetypes
import random
import unicodedata
from collections import defaultdict
from contextlib import asynccontextmanager
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from .ai import analyze_card
from .database import get_session, init_db
from .models import Card, utc_now
from .schemas import CardPatch, CardResponse, KnowledgeGraphEdge, KnowledgeGraphNode, KnowledgeGraphResponse, SearchResult, TextCardCreate
from .settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Inspiration Board", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


def card_to_response(card: Card) -> CardResponse:
    return CardResponse(
        id=card.id,
        weekKey=card.week_key,
        type=card.type,
        textContent=card.text_content,
        imageUrl=f"/uploads/{card.image_filename}" if card.image_filename else None,
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


def new_card_base(week_key: str, card_type: str, x: float, y: float) -> Card:
    seed = uuid4().hex[:10]
    return Card(
        id=str(uuid4()),
        week_key=week_key,
        type=card_type,
        x=x,
        y=y,
        width=300 if card_type == "text" else 280,
        rotation=random.choice([-3, -2, -1, 1, 2, 3]),
        style_seed=seed,
        ai_status="pending",
        keywords=[],
    )


def normalize_keyword(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def keyword_match_score(query: str, keyword: str) -> float:
    if not query or not keyword:
        return 0
    if query == keyword:
        return 100
    if keyword.startswith(query):
        return 90
    if query in keyword:
        return 75
    if keyword in query:
        return 70
    ratio = SequenceMatcher(None, query, keyword).ratio()
    return round(ratio * 68, 2) if ratio >= 0.58 else 0


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/api/weeks/{week_key}/cards", response_model=list[CardResponse])
def list_cards(week_key: str, session: Session = Depends(get_session)) -> list[CardResponse]:
    statement = select(Card).where(Card.week_key == week_key).order_by(Card.created_at)
    cards = session.exec(statement).all()
    return [card_to_response(card) for card in cards]


@app.get("/api/search", response_model=list[SearchResult])
def search_cards(q: str = "", session: Session = Depends(get_session)) -> list[SearchResult]:
    normalized_query = normalize_keyword(q)
    if not normalized_query:
        return []

    cards = session.exec(select(Card)).all()
    results: list[SearchResult] = []
    for card in cards:
        matched_keywords = []
        best_score = 0.0
        for keyword in card.keywords or []:
            score = keyword_match_score(normalized_query, normalize_keyword(keyword))
            if score <= 0:
                continue
            matched_keywords.append(keyword)
            best_score = max(best_score, score)

        if matched_keywords:
            results.append(
                SearchResult(
                    card=card_to_response(card),
                    weekKey=card.week_key,
                    matchedKeywords=matched_keywords,
                    score=best_score,
                ),
            )

    return sorted(results, key=lambda item: (-item.score, item.week_key, item.card.created_at))[:80]


@app.get("/api/graph", response_model=KnowledgeGraphResponse)
def get_knowledge_graph(session: Session = Depends(get_session)) -> KnowledgeGraphResponse:
    cards = session.exec(select(Card).order_by(Card.created_at)).all()
    keyword_groups: dict[str, dict] = defaultdict(lambda: {"label": "", "cards": {}, "weeks": set()})

    for card in cards:
        for keyword in card.keywords or []:
            normalized = normalize_keyword(keyword)
            if not normalized:
                continue
            group = keyword_groups[normalized]
            group["label"] = group["label"] or keyword
            group["cards"][card.id] = card
            group["weeks"].add(card.week_key)

    connected_groups = {
        key: group
        for key, group in keyword_groups.items()
        if len(group["cards"]) >= 2 or len(group["weeks"]) >= 2
    }

    nodes: list[KnowledgeGraphNode] = []
    edges: list[KnowledgeGraphEdge] = []
    added_cards: set[str] = set()

    for key, group in sorted(connected_groups.items(), key=lambda item: (-len(item[1]["cards"]), item[1]["label"])):
        keyword_node_id = f"keyword:{key}"
        cards_for_keyword = sorted(group["cards"].values(), key=lambda card: (card.week_key, card.created_at))
        nodes.append(
            KnowledgeGraphNode(
                id=keyword_node_id,
                type="keyword",
                label=group["label"],
                count=len(cards_for_keyword),
                weeks=sorted(group["weeks"]),
            ),
        )

        for card in cards_for_keyword:
            card_node_id = f"card:{card.id}"
            if card.id not in added_cards:
                nodes.append(
                    KnowledgeGraphNode(
                        id=card_node_id,
                        type="card",
                        label=card.summary or card.text_content or "灵感卡片",
                        weekKey=card.week_key,
                        card=card_to_response(card),
                    ),
                )
                added_cards.add(card.id)
            edges.append(
                KnowledgeGraphEdge(
                    id=f"{keyword_node_id}->{card_node_id}",
                    source=keyword_node_id,
                    target=card_node_id,
                    keyword=group["label"],
                ),
            )

    return KnowledgeGraphResponse(nodes=nodes, edges=edges)


@app.post("/api/cards/text", response_model=CardResponse)
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
    session.commit()
    session.refresh(card)
    background_tasks.add_task(analyze_card, card.id)
    return card_to_response(card)


@app.post("/api/cards/image", response_model=CardResponse)
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
    session.commit()
    session.refresh(card)
    background_tasks.add_task(analyze_card, card.id)
    return card_to_response(card)


@app.patch("/api/cards/{card_id}", response_model=CardResponse)
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
    session.commit()
    session.refresh(card)
    return card_to_response(card)


@app.post("/api/cards/{card_id}/analyze", response_model=CardResponse)
def retry_analyze_card(
    card_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> CardResponse:
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    card.ai_status = "pending"
    card.ai_error = None
    card.updated_at = utc_now()
    session.add(card)
    session.commit()
    session.refresh(card)
    background_tasks.add_task(analyze_card, card.id)
    return card_to_response(card)


@app.delete("/api/cards/{card_id}", status_code=204)
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
