from __future__ import annotations

import json
import mimetypes
from base64 import b64encode
from pathlib import Path

import httpx

from . import db
from .config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, UPLOAD_DIR


PROMPT = """你在整理个人知识白板上的一块内容，方便用户以后快速回想。
请写一句自然、具体、可独立理解的中文短总结，不超过 36 个字：
- 优先保留核心事实、结论、方法或用途；
- 避免“本文介绍了”“图片展示了”等空泛开头；
- 不补充原内容没有的信息。
再给出 2 到 5 个中文关键词，每个尽量控制在 2 到 8 个字：
- 优先选择主题、对象、方法和用途；
- 不要使用近义重复词，也不要使用“内容”“图片”“知识”等泛词。
只返回 JSON：{"summary":"...","keywords":["..."]}。"""


def analyze_card(card_id: str) -> None:
    card = db.get_card(card_id)
    if not card:
        return
    db.update_card(card_id, ai_status="generating", ai_error=None)
    if not OPENAI_API_KEY:
        db.update_card(card_id, ai_status="failed", ai_error="未配置 AI 密钥")
        return
    try:
        result = call_provider(card)
        summary = str(result.get("summary") or "").strip()[:60]
        keywords = []
        for value in result.get("keywords") or []:
            keyword = str(value).strip()
            if keyword and keyword not in keywords:
                keywords.append(keyword[:16])
        if not summary and not keywords:
            raise ValueError("AI 返回内容为空")
        db.update_card(card_id, summary=summary, keywords=keywords[:5], ai_status="done", ai_error=None)
    except Exception as exc:
        db.update_card(card_id, ai_status="failed", ai_error=friendly_error(exc))


def recover_unfinished() -> None:
    for card_id in db.unfinished_card_ids():
        analyze_card(card_id)


def call_provider(card: dict) -> dict:
    content: list[dict[str, object]] = [{"type": "text", "text": build_text(card)}]
    if card["type"] == "image":
        filename = card.get("imageFilename")
        if not filename:
            raise ValueError("图片文件不存在")
        path = Path(UPLOAD_DIR) / filename
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = b64encode(path.read_bytes()).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}})

    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=60) as client:
        response = client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload,
        )
        response.raise_for_status()
    return parse_json(response.json()["choices"][0]["message"].get("content") or "")


def build_text(card: dict) -> str:
    if card["type"] == "link":
        source = f"标题：{card.get('sourceTitle') or ''}\n描述：{card.get('sourceDescription') or ''}\n正文：{card.get('textContent') or ''}"
    elif card["type"] == "image":
        source = "请观察随附图片。"
    else:
        source = f"文本：{card.get('textContent') or ''}"
    return f"{PROMPT}\n\n{source}"


def parse_json(value: str) -> dict:
    text = value.strip().strip("`").strip()
    if text.lower().startswith("json"):
        text = text[4:].strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start : end + 1]
    return json.loads(text)


def friendly_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "rate limit" in text or "too many requests" in text:
        return "AI 请求过快，请稍后重试"
    if "quota" in text or "balance" in text or "credit" in text or "recharged" in text:
        return "AI 额度不足，请检查服务商账户"
    if isinstance(exc, httpx.TimeoutException):
        return "AI 响应超时，请重试"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"AI 服务请求失败（{exc.response.status_code}）"
    if isinstance(exc, (json.JSONDecodeError, KeyError, TypeError)):
        return "AI 返回格式无法识别，请重试"
    return "AI 整理失败，请重试"
