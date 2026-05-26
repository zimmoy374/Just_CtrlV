from __future__ import annotations

import ipaddress
import re
import socket
from html import unescape
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urlparse

import httpx


MAX_FETCH_BYTES = 1_000_000
MAX_TEXT_CHARS = 7000
TITLE_LIMIT = 140
DESCRIPTION_LIMIT = 260


class LinkPreviewError(ValueError):
    pass


class _PreviewParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self.text_parts: list[str] = []
        self._current_tag = ""
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg", "canvas"}:
            self._skip_depth += 1
        self._current_tag = lowered

        attr_map = {name.lower(): value or "" for name, value in attrs}
        meta_name = (attr_map.get("name") or attr_map.get("property") or "").lower()
        content = attr_map.get("content", "").strip()
        if content and meta_name in {"description", "og:description", "twitter:description"} and not self.description:
            self.description = _clean_text(content)[:DESCRIPTION_LIMIT]
        if content and meta_name in {"og:title", "twitter:title"} and not self.title:
            self.title = _clean_text(content)[:TITLE_LIMIT]

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg", "canvas"} and self._skip_depth:
            self._skip_depth -= 1
        if lowered == self._current_tag:
            self._current_tag = ""

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = _clean_text(data)
        if not cleaned:
            return
        if self._current_tag == "title" and not self.title:
            self.title = cleaned[:TITLE_LIMIT]
            return
        if self._current_tag in {"p", "article", "section", "main", "h1", "h2", "h3", "li", "blockquote"}:
            self.text_parts.append(cleaned)


def normalize_url(input_url: str) -> str:
    value = input_url.strip()
    if not value:
        raise LinkPreviewError("链接不能为空")
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LinkPreviewError("只支持 http 或 https 链接")
    if parsed.username or parsed.password:
        raise LinkPreviewError("链接不能包含用户名或密码")

    _validate_public_host(parsed.hostname or "")
    return value


def fetch_link_preview(input_url: str) -> dict[str, str]:
    url = normalize_url(input_url)
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(10.0, connect=4.0),
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; JustCtrlV/1.0)",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.4",
            },
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            if response.url.host:
                _validate_public_host(response.url.host)
            content_type = response.headers.get("content-type", "")
            content = response.content[:MAX_FETCH_BYTES]
    except LinkPreviewError:
        raise
    except Exception as exc:
        raise LinkPreviewError(f"链接读取失败：{str(exc)[:160]}") from exc

    text = _decode_content(content, response.encoding)
    if "html" in content_type.lower() or "<html" in text[:500].lower():
        parsed = _parse_html(text)
    else:
        cleaned = _clean_text(text)
        parsed = {
            "title": url,
            "description": cleaned[:DESCRIPTION_LIMIT],
            "content": cleaned[:MAX_TEXT_CHARS],
        }

    parsed["url"] = str(response.url)
    if not parsed.get("content"):
        parsed["content"] = parsed.get("description") or parsed.get("title") or parsed["url"]
    return parsed


def _validate_public_host(host: str) -> None:
    if not host:
        raise LinkPreviewError("链接地址无效")
    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise LinkPreviewError("链接域名无法解析") from exc

    for address in _iter_ip_addresses(addresses):
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise LinkPreviewError("出于安全限制，不能读取内网或本机链接")


def _iter_ip_addresses(addresses: Iterable[tuple]) -> Iterable[str]:
    for item in addresses:
        sockaddr = item[4]
        if sockaddr:
            yield sockaddr[0]


def _decode_content(content: bytes, encoding: str | None) -> str:
    candidates = [encoding, "utf-8", "gb18030"]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return content.decode(candidate, errors="replace")
        except LookupError:
            continue
    return content.decode("utf-8", errors="replace")


def _parse_html(html: str) -> dict[str, str]:
    parser = _PreviewParser()
    parser.feed(html)
    text = _clean_text("\n".join(parser.text_parts))[:MAX_TEXT_CHARS]
    description = parser.description or text[:DESCRIPTION_LIMIT]
    return {
        "title": (parser.title or "未命名链接").strip()[:TITLE_LIMIT],
        "description": description.strip()[:DESCRIPTION_LIMIT],
        "content": text,
    }


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()
