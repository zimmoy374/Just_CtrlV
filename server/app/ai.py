from __future__ import annotations

import json
import mimetypes
from base64 import b64encode
from pathlib import Path

import httpx
from google import genai
from google.genai import types
from sqlmodel import Session

from .database import engine
from .models import Card, utc_now
from .settings import settings


TEXT_PROMPT = """
你是一个灵感剪切板助手。请根据用户粘贴的文本，提炼一句不超过 40 字的中文总结，
并给出 5 到 10 个短关键词。关键词要像灵感标签，清晰、可复用、不要太正式。
只返回 JSON，格式为 {"summary":"...","keywords":["..."]}。
"""

IMAGE_PROMPT = """
你是一个视觉灵感剪切板助手。请观察图片里的画面、文字、布局、色彩和设计风格，
提炼一句不超过 40 字的中文总结，并给出 5 到 10 个短关键词。
关键词要像灵感标签，清晰、可复用、不要太正式。
只返回 JSON，格式为 {"summary":"...","keywords":["..."]}。
"""


def _clean_json(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1:
        stripped = stripped[start : end + 1]
    return json.loads(stripped)


def _normalize_result(payload: dict) -> tuple[str, list[str]]:
    summary = str(payload.get("summary") or "").strip()
    raw_keywords = payload.get("keywords") or []
    keywords = []
    for item in raw_keywords:
        keyword = str(item).strip()
        if keyword and keyword not in keywords:
            keywords.append(keyword)
    return summary[:120], keywords[:10]


def _missing_config_error() -> str | None:
    if settings.ai_provider == "openai":
        if not settings.openai_api_key:
            return "OPENAI_API_KEY 未配置"
        if not settings.openai_model:
            return "OPENAI_MODEL 未配置"
        if not settings.openai_base_url:
            return "OPENAI_BASE_URL 未配置"
        return None
    if not settings.gemini_api_key:
        return "GEMINI_API_KEY 未配置"
    return None


def _analyze_with_gemini(card: Card) -> dict:
    client = genai.Client(api_key=settings.gemini_api_key)
    contents: list[object]
    if card.type == "image":
        if not card.image_filename:
            raise ValueError("图片文件不存在")
        image_path = Path(settings.upload_dir) / card.image_filename
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        contents = [
            IMAGE_PROMPT,
            types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime_type),
        ]
    else:
        contents = [TEXT_PROMPT, card.text_content or ""]

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return _clean_json(response.text or "{}")


def _openai_content(card: Card) -> list[dict]:
    if card.type == "image":
        if not card.image_filename:
            raise ValueError("图片文件不存在")
        image_path = Path(settings.upload_dir) / card.image_filename
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        data_url = f"data:{mime_type};base64,{b64encode(image_path.read_bytes()).decode('ascii')}"
        return [
            {"type": "text", "text": IMAGE_PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
    return [{"type": "text", "text": f"{TEXT_PROMPT}\n\n用户文本：\n{card.text_content or ''}"}]


def _analyze_with_openai_compatible(card: Card) -> dict:
    payload = {
        "model": settings.openai_model,
        "messages": [{"role": "user", "content": _openai_content(card)}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    url = f"{settings.openai_base_url}/chat/completions"

    with httpx.Client(timeout=60) as client:
        response = client.post(url, headers=headers, json=payload)
        if response.status_code == 400 and "response_format" in response.text:
            payload.pop("response_format", None)
            response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"].get("content") or "{}"
    return _clean_json(content)


def _analyze_with_provider(card: Card) -> dict:
    if settings.ai_provider == "openai":
        return _analyze_with_openai_compatible(card)
    if settings.ai_provider != "gemini":
        raise ValueError(f"不支持的 AI_PROVIDER: {settings.ai_provider}")
    return _analyze_with_gemini(card)


def analyze_card(card_id: str) -> None:
    with Session(engine) as session:
        card = session.get(Card, card_id)
        if not card:
            return

        config_error = _missing_config_error()
        if config_error:
            card.ai_status = "failed"
            card.ai_error = config_error
            card.updated_at = utc_now()
            session.add(card)
            session.commit()
            return

        card.ai_status = "generating"
        card.ai_error = None
        card.updated_at = utc_now()
        session.add(card)
        session.commit()

        try:
            payload = _analyze_with_provider(card)
            summary, keywords = _normalize_result(payload)
            if not summary and not keywords:
                raise ValueError("AI 返回为空")

            card = session.get(Card, card_id)
            if not card:
                return
            card.summary = summary
            card.keywords = keywords
            card.ai_status = "done"
            card.ai_error = None
            card.updated_at = utc_now()
            session.add(card)
            session.commit()
        except Exception as exc:
            card = session.get(Card, card_id)
            if not card:
                return
            card.ai_status = "failed"
            card.ai_error = str(exc)[:240]
            card.updated_at = utc_now()
            session.add(card)
            session.commit()
