from __future__ import annotations

import json
import mimetypes
from base64 import b64encode
from copy import deepcopy
from json import JSONDecodeError
from pathlib import Path

import httpx

from .models import Card
from .settings import settings


TEXT_PROMPT = """
你是 Just Ctrl+V 的内容整理助手。请根据用户粘贴的文本，提炼一句不超过 40 字的中文总结，
并给出 5 到 7 个短关键词。关键词要像要点标签，清晰、可复用。
只返回 JSON，格式为 {"summary":"...","keywords":["..."]}。
"""

LINK_PROMPT = """
你是 Just Ctrl+V 的链接整理助手。请根据网页标题、描述和正文提炼一句不超过 40 字的中文总结，
并给出 5 到 7 个短关键词。关键词要像要点标签，清晰、可复用。
只返回 JSON，格式为 {"summary":"...","keywords":["..."]}。
"""

IMAGE_PROMPT = """
你是 Just Ctrl+V 的图片整理助手。请观察图片里的内容信息，
提炼一句不超过 40 字的中文总结，并给出 5 到 7 个短关键词。
关键词要像知识标签，清晰、可复用。
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
    if not stripped:
        raise ValueError("AI 返回为空，无法解析 JSON")
    try:
        return json.loads(stripped)
    except JSONDecodeError as exc:
        preview = stripped[:120].replace("\n", " ")
        raise ValueError(f"AI 未返回有效 JSON：{preview}") from exc


def _friendly_ai_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if "not been recharged" in lowered or "free resources" in lowered:
        return "AI 服务商返回免费额度限制：当前账号试用次数已用完或需要充值。请更换可用模型/账号，或给中转账号充值后重试。"
    if "insufficient" in lowered and ("quota" in lowered or "balance" in lowered or "credit" in lowered):
        return "AI 服务商返回额度不足：请检查账号余额、套餐额度或更换模型后重试。"
    if "rate limit" in lowered or "too many requests" in lowered:
        return "AI 服务商请求过快：稍后重试，或换一个限流更宽的模型。"
    return message[:240]


def _normalize_result(payload: dict) -> tuple[str, list[str]]:
    summary = str(payload.get("summary") or "").strip()
    keyword_values = payload.get("keywords") or []
    keywords = []
    for item in keyword_values:
        keyword = str(item).strip()
        if keyword and keyword not in keywords:
            keywords.append(keyword)
    return summary[:120], keywords[:10]


def _missing_config_error() -> str | None:
    if not settings.openai_api_key:
        return "OPENAI_API_KEY 未配置"
    if not settings.openai_model:
        return "OPENAI_MODEL 未配置"
    if not settings.openai_base_url:
        return "OPENAI_BASE_URL 未配置"
    return None


def get_ai_config_error() -> str | None:
    return _missing_config_error()


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
    if card.type == "link":
        return [
            {
                "type": "text",
                "text": f"{LINK_PROMPT}\n\n网页标题：\n{card.source_title or ''}\n\n网页描述：\n{card.source_description or ''}\n\n网页正文：\n{card.text_content or ''}",
            },
        ]
    return [{"type": "text", "text": f"{TEXT_PROMPT}\n\n用户文本：\n{card.text_content or ''}"}]


def _analyze_with_provider(card: Card) -> dict:
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
        should_retry_without_format = response.status_code == 400 and "response_format" in response.text
        if should_retry_without_format:
            payload.pop("response_format", None)
            response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"].get("content") or ""
        try:
            return _clean_json(content)
        except ValueError:
            if "response_format" not in payload:
                raise
            retry_payload = deepcopy(payload)
            retry_payload.pop("response_format", None)
            retry_response = client.post(url, headers=headers, json=retry_payload)
            retry_response.raise_for_status()
            retry_data = retry_response.json()
            retry_content = retry_data["choices"][0]["message"].get("content") or ""
            return _clean_json(retry_content)


def analyze_card(card_id: str) -> None:
    from .analysis.jobs import run_card_analysis_now

    run_card_analysis_now(card_id, reason="direct-card-analysis")
