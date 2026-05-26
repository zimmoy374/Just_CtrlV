from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from ..models import KnowledgeItem, KnowledgePage, KnowledgePageItemLink, SourceItem, utc_now


EXPORT_VERSION = "0.1"
EXPORT_PAGE_ITEM_STATUSES = {"active"}


def export_knowledge_bundle(session: Session, output_dir: Path) -> Path:
    root = output_dir / "export"
    wiki_dir = root / "wiki"
    sources_dir = root / "sources"
    root.mkdir(parents=True, exist_ok=True)
    wiki_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)

    pages = session.exec(select(KnowledgePage).order_by(KnowledgePage.updated_at)).all()
    knowledge_items = session.exec(select(KnowledgeItem).order_by(KnowledgeItem.created_at)).all()
    source_items = session.exec(select(SourceItem).order_by(SourceItem.created_at)).all()
    page_links = session.exec(select(KnowledgePageItemLink)).all()

    source_by_id = {source_item.id: source_item for source_item in source_items}
    knowledge_items_by_id = {
        knowledge_item.id: knowledge_item
        for knowledge_item in knowledge_items
        if knowledge_item.status in EXPORT_PAGE_ITEM_STATUSES
    }

    _write_manifest(root / "manifest.json", pages=pages, knowledge_items=knowledge_items, source_items=source_items)
    _write_index(root / "index.md", pages=pages, knowledge_items=knowledge_items, source_items=source_items)
    _write_wiki_pages(wiki_dir, pages=pages, page_links=page_links, knowledge_items_by_id=knowledge_items_by_id)
    _write_items(root / "items.jsonl", knowledge_items=knowledge_items)
    _write_sources(sources_dir, source_items=source_items)
    _write_provenance(
        root / "provenance.jsonl",
        pages=pages,
        knowledge_items=knowledge_items,
        source_by_id=source_by_id,
        page_links=page_links,
    )
    return root


def _write_manifest(
    path: Path,
    *,
    pages: list[KnowledgePage],
    knowledge_items: list[KnowledgeItem],
    source_items: list[SourceItem],
) -> None:
    payload = {
        "exportVersion": EXPORT_VERSION,
        "generatedAt": _dt(utc_now()),
        "description": "Just Ctrl V knowledge export bundle",
        "contents": {
            "index": "index.md",
            "wiki": "wiki/",
            "items": "items.jsonl",
            "sources": "sources/",
            "provenance": "provenance.jsonl",
        },
        "counts": {
            "knowledgePages": len(pages),
            "knowledgeItems": len(knowledge_items),
            "sourceItems": len(source_items),
        },
    }
    _write_json(path, payload)


def _write_index(
    path: Path,
    *,
    pages: list[KnowledgePage],
    knowledge_items: list[KnowledgeItem],
    source_items: list[SourceItem],
) -> None:
    lines = [
        "# Just Ctrl V Knowledge Export",
        "",
        f"- Generated at: {_dt(utc_now())}",
        f"- Knowledge pages: {len(pages)}",
        f"- Knowledge items: {len(knowledge_items)}",
        f"- Source items: {len(source_items)}",
        "",
        "## Knowledge Pages",
        "",
    ]
    if pages:
        for page in pages:
            lines.append(f"- [{page.title}](wiki/{_page_filename(page)}) - {page.status}")
    else:
        lines.append("- No knowledge pages exported yet.")
    lines.extend(
        [
            "",
            "## Machine-Readable Files",
            "",
            "- `items.jsonl`: KnowledgeItem records.",
            "- `provenance.jsonl`: SourceItem, KnowledgeItem, and KnowledgePage relationships.",
            "- `sources/`: SourceItem original materials and metadata.",
            "",
        ],
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_wiki_pages(
    wiki_dir: Path,
    *,
    pages: list[KnowledgePage],
    page_links: list[KnowledgePageItemLink],
    knowledge_items_by_id: dict[str, KnowledgeItem],
) -> None:
    links_by_page: dict[str, list[KnowledgePageItemLink]] = {}
    for link in page_links:
        links_by_page.setdefault(link.page_id, []).append(link)

    for page in pages:
        links = links_by_page.get(page.id, [])
        linked_items = [
            knowledge_items_by_id[link.knowledge_item_id]
            for link in links
            if link.knowledge_item_id in knowledge_items_by_id
        ]
        item_refs = [f"item:{knowledge_item.id}" for knowledge_item in linked_items]
        source_refs = sorted({f"source:{knowledge_item.source_item_id}" for knowledge_item in linked_items})
        frontmatter = {
            "id": page.id,
            "title": page.title,
            "status": page.status,
            "updatedAt": _dt(page.updated_at),
            "sourceRefs": source_refs,
            "itemRefs": item_refs,
        }
        body_lines = [
            "---",
            *[f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in frontmatter.items()],
            "---",
            "",
            f"# {page.title}",
            "",
        ]
        if page.summary:
            body_lines.extend([page.summary, ""])
        if page.body:
            body_lines.extend([page.body, ""])
        if linked_items:
            body_lines.extend(["## Related Knowledge Items", ""])
            for knowledge_item in linked_items:
                body_lines.extend(
                    [
                        f"### {knowledge_item.title or knowledge_item.id}",
                        "",
                        f"- Citation: `item:{knowledge_item.id}`",
                        f"- Source: `source:{knowledge_item.source_item_id}`",
                        f"- Status: `{knowledge_item.status}`",
                        "",
                        knowledge_item.summary or knowledge_item.content or "",
                        "",
                    ],
                )
        else:
            body_lines.extend(["No linked KnowledgeItems yet.", ""])
        (wiki_dir / _page_filename(page)).write_text("\n".join(body_lines), encoding="utf-8")


def _write_items(path: Path, *, knowledge_items: list[KnowledgeItem]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for knowledge_item in knowledge_items:
            file.write(
                json.dumps(
                    {
                        "id": knowledge_item.id,
                        "sourceItemId": knowledge_item.source_item_id,
                        "cardId": knowledge_item.card_id,
                        "title": knowledge_item.title,
                        "summary": knowledge_item.summary,
                        "content": knowledge_item.content,
                        "keywords": knowledge_item.keywords or [],
                        "source": knowledge_item.source,
                        "sourceRef": knowledge_item.source_ref,
                        "knowledgeType": knowledge_item.knowledge_type,
                        "status": knowledge_item.status,
                        "createdAt": _dt(knowledge_item.created_at),
                        "updatedAt": _dt(knowledge_item.updated_at),
                    },
                    ensure_ascii=False,
                )
                + "\n",
            )


def _write_sources(sources_dir: Path, *, source_items: list[SourceItem]) -> None:
    for source_item in source_items:
        source_dir = sources_dir / source_item.id
        source_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            source_dir / "metadata.json",
            {
                "id": source_item.id,
                "source": source_item.source,
                "externalId": source_item.external_id,
                "kind": source_item.kind,
                "title": source_item.title,
                "metadata": source_item.metadata_json or {},
                "status": source_item.status,
                "createdAt": _dt(source_item.created_at),
                "updatedAt": _dt(source_item.updated_at),
            },
        )
        (source_dir / "content.txt").write_text(source_item.content_text or "", encoding="utf-8")
        if source_item.content_html:
            (source_dir / "content.html").write_text(source_item.content_html, encoding="utf-8")


def _write_provenance(
    path: Path,
    *,
    pages: list[KnowledgePage],
    knowledge_items: list[KnowledgeItem],
    source_by_id: dict[str, SourceItem],
    page_links: list[KnowledgePageItemLink],
) -> None:
    with path.open("w", encoding="utf-8") as file:
        for knowledge_item in knowledge_items:
            if knowledge_item.source_item_id in source_by_id:
                _write_jsonl(
                    file,
                    {
                        "type": "derived_from",
                        "from": f"item:{knowledge_item.id}",
                        "to": f"source:{knowledge_item.source_item_id}",
                    },
                )
        page_ids = {page.id for page in pages}
        knowledge_item_ids = {
            knowledge_item.id for knowledge_item in knowledge_items if knowledge_item.status in EXPORT_PAGE_ITEM_STATUSES
        }
        for link in page_links:
            if link.page_id in page_ids and link.knowledge_item_id in knowledge_item_ids:
                _write_jsonl(
                    file,
                    {
                        "type": "included_in_page",
                        "from": f"item:{link.knowledge_item_id}",
                        "to": f"page:{link.page_id}",
                    },
                )


def _page_filename(page: KnowledgePage) -> str:
    return f"{_slugify(page.title) or 'knowledge-page'}-{page.id[:8]}.md"


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", lowered, flags=re.UNICODE)
    return slug.strip("-")[:80]


def _dt(value: Any) -> str:
    return value.isoformat() if value else ""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(file, payload: dict[str, Any]) -> None:
    file.write(json.dumps(payload, ensure_ascii=False) + "\n")
