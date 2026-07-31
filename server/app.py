from __future__ import annotations

import mimetypes
import math
from io import BytesIO
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from threading import Thread
from typing import Literal
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image

from . import ai, db, desktop_capture, settings
from .config import ALLOWED_ORIGINS, MAX_UPLOAD_BYTES, ROOT, UPLOAD_DIR
from .preview import PreviewError, fetch_preview


class TextCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    day_key: str = Field(alias="dayKey")
    text_content: str = Field(alias="textContent", min_length=1)
    x: float
    y: float


class LinkCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    day_key: str = Field(alias="dayKey")
    url: str = Field(min_length=1)
    x: float
    y: float


class CardPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    x: float | None = None
    y: float | None = None
    position_space: Literal["world"] | None = Field(default=None, alias="positionSpace")
    keywords: list[str] | None = Field(default=None, max_length=5)


class CaptureSettingsPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    enabled: bool | None = None
    hotkey: str | None = Field(default=None, min_length=1, max_length=80)
    day_mode: Literal["today", "current"] | None = Field(default=None, alias="dayMode")
    last_day: str | None = Field(default=None, alias="lastDay")


db.init_db()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Thread(target=ai.recover_unfinished, daemon=True).start()
    yield


app = FastAPI(title="CtrlV", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/days")
def days() -> list[str]:
    return db.list_days()


@app.get("/api/days/{day_key}/cards")
def cards(day_key: str) -> list[dict]:
    return [public_card(card) for card in db.list_cards(valid_day(day_key))]


@app.post("/api/cards/text")
def create_text(payload: TextCreate, tasks: BackgroundTasks) -> dict:
    text = payload.text_content.strip()
    if not text:
        raise HTTPException(400, "文本不能为空")
    return create_card(tasks, payload.day_key, "text", payload.x, payload.y, text_content=text)


@app.post("/api/cards/link")
def create_link(payload: LinkCreate, tasks: BackgroundTasks) -> dict:
    try:
        preview = fetch_preview(payload.url)
    except PreviewError as exc:
        raise HTTPException(400, str(exc)) from exc
    return create_card(
        tasks,
        payload.day_key,
        "link",
        payload.x,
        payload.y,
        source_url=preview["url"],
        source_title=preview["title"],
        source_description=preview["description"],
        text_content=preview["content"],
    )


@app.post("/api/cards/image")
async def create_image(
    tasks: BackgroundTasks,
    day_key: str = Form(alias="dayKey"),
    x: float = Form(),
    y: float = Form(),
    cutout: bool = Form(default=False),
    display_width: float | None = Form(default=None, alias="displayWidth"),
    display_height: float | None = Form(default=None, alias="displayHeight"),
    file: UploadFile = File(),
) -> dict:
    valid_point(x, y)
    if display_width is not None and display_width <= 0:
        raise HTTPException(422, "图片显示宽度必须大于 0")
    if display_height is not None and display_height <= 0:
        raise HTTPException(422, "图片显示高度必须大于 0")
    filename, pixel_width, pixel_height = await save_image_upload(file, cutout=cutout)
    try:
        return create_card(
            tasks,
            day_key,
            "image",
            x,
            y,
            analyze=not cutout,
            image_filename=filename,
            media_width=display_width if cutout and display_width else pixel_width,
            media_height=display_height if cutout and display_height else pixel_height,
        )
    except Exception:
        (UPLOAD_DIR / filename).unlink(missing_ok=True)
        raise


@app.get("/api/settings/capture")
def capture_setup() -> dict:
    return {
        **settings.get_capture_settings(),
        "status": desktop_capture.capture_status(),
    }


@app.patch("/api/settings/capture")
def patch_capture_settings(payload: CaptureSettingsPatch) -> dict:
    changes = payload.model_dump(by_alias=True, exclude_none=True)
    if "hotkey" in changes:
        try:
            changes["hotkey"] = desktop_capture.normalize_hotkey(changes["hotkey"])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    if "lastDay" in changes:
        changes["lastDay"] = valid_day(changes["lastDay"])
    return settings.update_capture_settings(changes)


@app.patch("/api/cards/{card_id}")
def patch_card(card_id: str, payload: CardPatch) -> dict:
    changes = payload.model_dump(exclude_none=True)
    if "x" in changes or "y" in changes:
        valid_point(float(changes.get("x", 0)), float(changes.get("y", 0)))
    card = db.update_card(card_id, **changes)
    if not card:
        raise HTTPException(404, "卡片不存在")
    return public_card(card)


@app.post("/api/cards/{card_id}/analyze")
def retry_card(card_id: str, tasks: BackgroundTasks) -> dict:
    card = db.update_card(card_id, ai_status="pending", ai_error=None)
    if not card:
        raise HTTPException(404, "卡片不存在")
    tasks.add_task(ai.analyze_card, card_id)
    return public_card(card)


@app.delete("/api/cards/{card_id}", status_code=204)
def delete_card(card_id: str) -> Response:
    card = db.delete_card(card_id)
    if not card:
        raise HTTPException(404, "卡片不存在")
    if card.get("imageFilename"):
        (UPLOAD_DIR / card["imageFilename"]).unlink(missing_ok=True)
    return Response(status_code=204)


def create_card(
    tasks: BackgroundTasks,
    day_key: str,
    card_type: str,
    x: float,
    y: float,
    *,
    analyze: bool = True,
    **content: object,
) -> dict:
    valid_point(x, y)
    card_id = str(uuid4())
    card = db.insert_card(
        {
            "id": card_id,
            "day_key": valid_day(day_key),
            "type": card_type,
            "x": x,
            "y": y,
            "position_space": "world",
            "style_seed": uuid4().hex[:10],
            "ai_status": "pending" if analyze else "done",
            "ai_error": None,
            "keywords": [],
            **content,
        }
    )
    if analyze:
        tasks.add_task(ai.analyze_card, card_id)
    return public_card(card)


def valid_day(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(400, "日期格式必须是 YYYY-MM-DD") from exc


def valid_point(x: float, y: float) -> None:
    if not math.isfinite(x) or not math.isfinite(y) or abs(x) > 100000 or abs(y) > 100000:
        raise HTTPException(422, "卡片位置超出白板可保存范围")


async def save_image_upload(file: UploadFile, *, cutout: bool) -> tuple[str, int, int]:
    if file.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(400, "仅支持 PNG、JPEG、WebP 图片")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "图片不能超过 10MB")
    try:
        with Image.open(BytesIO(content)) as image:
            pixel_width, pixel_height = image.size
    except OSError as exc:
        raise HTTPException(400, "无法读取图片内容") from exc
    extension = mimetypes.guess_extension(file.content_type) or ".png"
    filename = f"{'cutout-' if cutout else ''}{uuid4().hex}{extension}"
    (UPLOAD_DIR / filename).write_bytes(content)
    return filename, pixel_width, pixel_height


def public_card(card: dict) -> dict:
    return {key: value for key, value in card.items() if key != "imageFilename"}


client = ROOT / "client"
app.mount("/", StaticFiles(directory=client, html=True), name="client")
