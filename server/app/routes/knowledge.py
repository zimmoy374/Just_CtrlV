from __future__ import annotations

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
    KnowledgePageSummaryResponse,
    KnowledgeSearchResult,
    ReflectionResponse,
)
from ..wiki.pages import ACTIVE_KNOWLEDGE_ITEM_STATUSES


router = APIRouter()


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
    task_session_id: str | None = Query(default=None, alias="taskSessionId"),
    scope: str | None = Query(default=None),
    visibility: str = Query("workspace"),
    capabilities: list[str] | None = Query(default=None, alias="capability"),
    item_limit: int = Query(6, alias="itemLimit", ge=1, le=20),
    page_limit: int = Query(3, alias="pageLimit", ge=0, le=10),
    source_excerpt_limit: int = Query(3, alias="sourceExcerptLimit", ge=0, le=10),
    profile_fact_limit: int = Query(5, alias="profileFactLimit", ge=0, le=20),
    max_chars: int = Query(4000, alias="maxChars", ge=500, le=20000),
    session: Session = Depends(get_session),
) -> ContextPackResponse:
    return ContextPackResponse.model_validate(
        MemoryContextComposer().build_context_pack(
            session,
            query=q,
            task_session_id=task_session_id,
            scope=scope,
            visibility=visibility,
            capabilities=capabilities or [],
            max_pages=page_limit,
            max_items=item_limit,
            max_source_excerpts=source_excerpt_limit,
            max_profile_facts=profile_fact_limit,
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
