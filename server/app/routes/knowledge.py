from __future__ import annotations

import unicodedata
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..database import get_session
from ..export.bundle import export_knowledge_bundle
from ..knowledge_core.lifecycle import commit_knowledge_item
from ..knowledge_core.source_items import upsert_source_item
from ..memory_core.composer import MemoryContextComposer
from ..models import Card, KnowledgeItem, KnowledgePage, KnowledgePageItemLink, Reflection
from ..organization.suggestions import accept_reflection, create_page_update_suggestions, dismiss_reflection
from ..presenters import card_to_response, knowledge_item_to_response, reflection_to_response
from ..retrieval.engine import RetrievalEngine
from ..schemas import (
    ConfirmedKnowledgeImport,
    ConfirmedKnowledgeImportResponse,
    ContextPackResponse,
    ExportBundleResponse,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    KnowledgeGraphResponse,
    KnowledgePageSummaryResponse,
    KnowledgeSearchResult,
    ReflectionResponse,
)
from ..wiki.pages import ACTIVE_KNOWLEDGE_ITEM_STATUSES


router = APIRouter()


def normalize_keyword(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in normalized if char.isalnum())


@router.get("/api/graph", response_model=KnowledgeGraphResponse)
def get_knowledge_graph(session: Session = Depends(get_session)) -> KnowledgeGraphResponse:
    knowledge_items = session.exec(
        select(KnowledgeItem).where(KnowledgeItem.status.in_(ACTIVE_KNOWLEDGE_ITEM_STATUSES)).order_by(KnowledgeItem.created_at),
    ).all()
    cards = session.exec(select(Card)).all()
    cards_by_id = {card.id: card for card in cards}
    keyword_groups: dict[str, dict] = defaultdict(lambda: {"label": "", "items": {}, "weeks": set()})

    for knowledge_item in knowledge_items:
        card = cards_by_id.get(knowledge_item.card_id or "")
        for keyword in knowledge_item.keywords or []:
            normalized = normalize_keyword(keyword)
            if not normalized:
                continue
            group = keyword_groups[normalized]
            group["label"] = group["label"] or keyword
            group["items"][knowledge_item.id] = knowledge_item
            if card:
                group["weeks"].add(card.week_key)

    connected_groups = {
        key: group
        for key, group in keyword_groups.items()
        if len(group["items"]) >= 2 or len(group["weeks"]) >= 2
    }

    nodes: list[KnowledgeGraphNode] = []
    edges: list[KnowledgeGraphEdge] = []
    added_items: set[str] = set()

    def add_item_node(knowledge_item: KnowledgeItem) -> None:
        if knowledge_item.id in added_items:
            return
        card = cards_by_id.get(knowledge_item.card_id or "")
        nodes.append(
            KnowledgeGraphNode(
                id=f"item:{knowledge_item.id}",
                type="item",
                label=knowledge_item.title or knowledge_item.summary or "知识条目",
                weekKey=card.week_key if card else None,
                count=len(knowledge_item.keywords or []),
                weeks=[card.week_key] if card else [],
                card=card_to_response(card) if card else None,
                knowledgeItem=knowledge_item_to_response(knowledge_item),
            ),
        )
        added_items.add(knowledge_item.id)

    for key, group in sorted(connected_groups.items(), key=lambda item: (-len(item[1]["items"]), item[1]["label"])):
        keyword_node_id = f"keyword:{key}"
        items_for_keyword = sorted(group["items"].values(), key=lambda item: (item.updated_at, item.title))
        nodes.append(
            KnowledgeGraphNode(
                id=keyword_node_id,
                type="keyword",
                label=group["label"],
                count=len(items_for_keyword),
                weeks=sorted(group["weeks"]),
            ),
        )

        for knowledge_item in items_for_keyword:
            item_node_id = f"item:{knowledge_item.id}"
            add_item_node(knowledge_item)
            edges.append(
                KnowledgeGraphEdge(
                    id=f"{keyword_node_id}->{item_node_id}",
                    source=keyword_node_id,
                    target=item_node_id,
                    keyword=group["label"],
                ),
            )

    page_links = session.exec(select(KnowledgePageItemLink)).all()
    active_item_ids = {knowledge_item.id for knowledge_item in knowledge_items}
    page_ids = sorted({link.page_id for link in page_links if link.knowledge_item_id in active_item_ids})
    if page_ids:
        pages = session.exec(
            select(KnowledgePage).where(KnowledgePage.id.in_(page_ids), KnowledgePage.status != "archived"),
        ).all()
        items_by_id = {knowledge_item.id: knowledge_item for knowledge_item in knowledge_items}
        links_by_page: dict[str, list[KnowledgePageItemLink]] = defaultdict(list)
        for link in page_links:
            if link.knowledge_item_id in active_item_ids:
                links_by_page[link.page_id].append(link)

        for page in sorted(pages, key=lambda item: item.updated_at, reverse=True):
            links = links_by_page.get(page.id, [])
            linked_items = [items_by_id[link.knowledge_item_id] for link in links if link.knowledge_item_id in items_by_id]
            if not linked_items:
                continue
            page_node_id = f"page:{page.id}"
            nodes.append(
                KnowledgeGraphNode(
                    id=page_node_id,
                    type="page",
                    label=page.title,
                    count=len(linked_items),
                    status=page.status,
                    itemCount=len(linked_items),
                ),
            )
            for knowledge_item in linked_items:
                item_node_id = f"item:{knowledge_item.id}"
                add_item_node(knowledge_item)
                edges.append(
                    KnowledgeGraphEdge(
                        id=f"{page_node_id}->{item_node_id}",
                        source=page_node_id,
                        target=item_node_id,
                        keyword="included",
                    ),
                )

    return KnowledgeGraphResponse(nodes=nodes, edges=edges)


@router.get("/api/knowledge/search", response_model=list[KnowledgeSearchResult])
def search_knowledge_items(q: str = "", session: Session = Depends(get_session)) -> list[KnowledgeSearchResult]:
    results: list[KnowledgeSearchResult] = []
    for result in RetrievalEngine().search(session, q):
        knowledge_item = result.knowledge_item
        card = session.get(Card, knowledge_item.card_id) if knowledge_item.card_id else None
        results.append(
            KnowledgeSearchResult(
                knowledgeItem=knowledge_item_to_response(knowledge_item),
                card=card_to_response(card) if card else None,
                matchedFields=result.matched_fields,
                score=result.score,
                excerpt=result.excerpt,
                reason=result.reason,
                source=result.source,
            ),
        )
    return results


@router.post("/api/knowledge/import-confirmed", response_model=ConfirmedKnowledgeImportResponse)
def import_confirmed_knowledge(
    payload: ConfirmedKnowledgeImport,
    session: Session = Depends(get_session),
) -> ConfirmedKnowledgeImportResponse:
    """Import knowledge already reviewed by the user in an external AI tool."""
    external_id = payload.external_id.strip() or f"external-ai:{payload.title}:{payload.selected_original_text[:80]}"
    source_item = upsert_source_item(
        session,
        source="external_ai",
        external_id=external_id,
        kind="external_ai_note",
        title=payload.source_title or payload.title,
        content_text=payload.selected_original_text,
        metadata={
            **(payload.metadata or {}),
            "sourceTitle": payload.source_title,
            "sourceUrl": payload.source_url,
            "proposedPages": payload.proposed_pages,
        },
        status="active",
    )
    knowledge_item = commit_knowledge_item(
        session,
        source_item=source_item,
        knowledge_type="fragment",
        title=payload.title,
        summary=payload.summary,
        content=payload.body or payload.summary or payload.selected_original_text,
        keywords=payload.keywords,
        source_ref=payload.source_url or payload.source_title or source_item.id,
        card_id=None,
        status="active",
    )
    suggestions = create_page_update_suggestions(
        session,
        knowledge_item_ids=[knowledge_item.id],
        page_titles=payload.proposed_pages,
    )
    session.commit()
    session.refresh(source_item)
    session.refresh(knowledge_item)
    return ConfirmedKnowledgeImportResponse(
        sourceItemId=source_item.id,
        knowledgeItem=knowledge_item_to_response(knowledge_item),
        suggestionIds=[suggestion.id for suggestion in suggestions],
    )


@router.get("/api/knowledge/context", response_model=ContextPackResponse)
def get_knowledge_context(
    q: str = "",
    item_limit: int = Query(6, alias="itemLimit", ge=1, le=20),
    page_limit: int = Query(3, alias="pageLimit", ge=0, le=10),
    source_excerpt_limit: int = Query(3, alias="sourceExcerptLimit", ge=0, le=10),
    max_chars: int = Query(4000, alias="maxChars", ge=500, le=20000),
    session: Session = Depends(get_session),
) -> ContextPackResponse:
    return ContextPackResponse.model_validate(
        MemoryContextComposer().build_context_pack(
            session,
            query=q,
            max_pages=page_limit,
            max_items=item_limit,
            max_source_excerpts=source_excerpt_limit,
            max_chars=max_chars,
        ),
    )


@router.get("/api/knowledge/pages", response_model=list[KnowledgePageSummaryResponse])
def list_knowledge_pages(session: Session = Depends(get_session)) -> list[KnowledgePageSummaryResponse]:
    pages = session.exec(
        select(KnowledgePage).where(KnowledgePage.status != "archived").order_by(KnowledgePage.updated_at.desc()),
    ).all()
    links = session.exec(select(KnowledgePageItemLink)).all()
    active_item_ids = {
        item.id
        for item in session.exec(
            select(KnowledgeItem).where(KnowledgeItem.status.in_(ACTIVE_KNOWLEDGE_ITEM_STATUSES)),
        ).all()
    }
    item_counts: dict[str, int] = defaultdict(int)
    for link in links:
        if link.knowledge_item_id in active_item_ids:
            item_counts[link.page_id] += 1
    return [
        KnowledgePageSummaryResponse(
            id=page.id,
            title=page.title,
            summary=page.summary,
            status=page.status,
            keywords=page.keywords or [],
            updatedAt=page.updated_at,
            itemCount=item_counts.get(page.id, 0),
        )
        for page in pages
    ]


@router.post("/api/knowledge/export", response_model=ExportBundleResponse)
def export_knowledge(session: Session = Depends(get_session)) -> ExportBundleResponse:
    from ..settings import settings

    export_root = export_knowledge_bundle(session, Path(settings.data_dir) / "exports")
    files = [str(path.relative_to(export_root)) for path in export_root.rglob("*") if path.is_file()]
    return ExportBundleResponse(exportPath=str(export_root), files=sorted(files))


@router.get("/api/reflections", response_model=list[ReflectionResponse])
def list_reflections(status: str = "pending", session: Session = Depends(get_session)) -> list[ReflectionResponse]:
    statement = select(Reflection).order_by(Reflection.created_at)
    if status != "all":
        statement = statement.where(Reflection.status == status)
    return [reflection_to_response(item) for item in session.exec(statement).all()]


@router.post("/api/reflections/{reflection_id}/accept", response_model=ReflectionResponse)
def accept_reflection_api(reflection_id: str, session: Session = Depends(get_session)) -> ReflectionResponse:
    reflection = session.get(Reflection, reflection_id)
    if not reflection:
        raise HTTPException(status_code=404, detail="整理建议不存在")
    try:
        accept_reflection(session, reflection)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(reflection)
    return reflection_to_response(reflection)


@router.post("/api/reflections/{reflection_id}/dismiss", response_model=ReflectionResponse)
def dismiss_reflection_api(reflection_id: str, session: Session = Depends(get_session)) -> ReflectionResponse:
    reflection = session.get(Reflection, reflection_id)
    if not reflection:
        raise HTTPException(status_code=404, detail="整理建议不存在")
    dismiss_reflection(session, reflection)
    session.commit()
    session.refresh(reflection)
    return reflection_to_response(reflection)
