from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def get_text(self) -> str:
        return "\n".join(self.parts)


def html_to_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value or "")
    return parser.get_text()


def normalize_keyword(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


def compact_text(value: str, limit: int = 160) -> str:
    text_value = re.sub(r"\s+", " ", value or "").strip()
    if len(text_value) <= limit:
        return text_value
    return f"{text_value[:limit].rstrip()}..."

