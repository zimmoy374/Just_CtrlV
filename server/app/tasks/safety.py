from __future__ import annotations

import re
from typing import Any


MAX_TASK_TEXT_CHARS = 1200
SENSITIVE_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{12,}"), "sk-***"),
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;]+)"), r"\1=***"),
]


def sanitize_task_text(value: str, *, limit: int = MAX_TASK_TEXT_CHARS) -> str:
    clean = " ".join(str(value or "").split())
    for pattern, replacement in SENSITIVE_PATTERNS:
        clean = pattern.sub(replacement, clean)
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit].rstrip()}..."


def sanitize_task_payload(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_task_text(value)
    if isinstance(value, list):
        return [sanitize_task_payload(item) for item in value[:50]]
    if isinstance(value, dict):
        return {str(key): sanitize_task_payload(item) for key, item in value.items()}
    return value
