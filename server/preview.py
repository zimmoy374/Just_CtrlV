from __future__ import annotations

import ipaddress
import re
import socket
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx


class PreviewError(ValueError):
    pass


class PreviewParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self.parts: list[str] = []
        self.tag = ""
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag = tag.lower()
        if self.tag in {"script", "style", "noscript", "svg", "canvas"}:
            self.skip += 1
        values = {key.lower(): value or "" for key, value in attrs}
        name = (values.get("name") or values.get("property") or "").lower()
        content = clean(values.get("content", ""))
        if content and name in {"description", "og:description", "twitter:description"} and not self.description:
            self.description = content[:260]
        if content and name in {"og:title", "twitter:title"} and not self.title:
            self.title = content[:140]

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "canvas"} and self.skip:
            self.skip -= 1
        self.tag = ""

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        text = clean(data)
        if self.tag == "title" and text and not self.title:
            self.title = text[:140]
        elif self.tag in {"p", "article", "section", "main", "h1", "h2", "li", "blockquote"} and text:
            self.parts.append(text)


def fetch_preview(raw_url: str) -> dict[str, str]:
    url = normalize_url(raw_url)
    try:
        with httpx.Client(timeout=httpx.Timeout(10, connect=4), headers={"User-Agent": "ctrlv/1.0"}) as client:
            for _ in range(5):
                response = client.get(url, follow_redirects=False)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise PreviewError("链接跳转地址无效")
                    url = normalize_url(urljoin(url, location))
                    continue
                response.raise_for_status()
                break
            else:
                raise PreviewError("链接跳转次数过多")
    except PreviewError:
        raise
    except Exception as exc:
        raise PreviewError("链接读取失败") from exc

    body = response.content[:1_000_000]
    text = decode(body, response.encoding)
    if "html" not in response.headers.get("content-type", "").lower() and "<html" not in text[:500].lower():
        content = clean(text)[:7000]
        return {"url": url, "title": url, "description": content[:260], "content": content}

    parser = PreviewParser()
    parser.feed(text)
    content = clean(" ".join(parser.parts))[:7000]
    return {
        "url": url,
        "title": parser.title or "未命名链接",
        "description": parser.description or content[:260],
        "content": content or parser.description or parser.title or url,
    }


def normalize_url(value: str) -> str:
    url = value.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise PreviewError("只支持公开的 HTTP 或 HTTPS 链接")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise PreviewError("链接域名无法解析") from exc
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise PreviewError("不能读取内网或本机链接")
    return url


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def decode(content: bytes, encoding: str | None) -> str:
    for name in (encoding, "utf-8", "gb18030"):
        if name:
            try:
                return content.decode(name, errors="replace")
            except LookupError:
                pass
    return content.decode("utf-8", errors="replace")
