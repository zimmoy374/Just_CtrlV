from __future__ import annotations

import re
from collections import defaultdict
from uuid import uuid4

from sqlmodel import Session, select

from ..core.text import normalize_keyword
from ..models import KnowledgeItem, KnowledgePage, KnowledgePageItemLink, Reflection, utc_now
from ..wiki.pages import link_items_to_page, upsert_knowledge_page

ORGANIZABLE_KNOWLEDGE_STATUSES = {"active"}


def maybe_create_reflections(session: Session) -> None:
    knowledge_items = session.exec(select(KnowledgeItem).where(KnowledgeItem.status.in_(ORGANIZABLE_KNOWLEDGE_STATUSES))).all()
    keyword_groups: dict[str, dict] = defaultdict(lambda: {"label": "", "knowledge_item_ids": []})
    for knowledge_item in knowledge_items:
        for keyword in knowledge_item.keywords or []:
            normalized = normalize_keyword(keyword)
            if not normalized:
                continue
            group = keyword_groups[normalized]
            group["label"] = group["label"] or keyword
            group["knowledge_item_ids"].append(knowledge_item.id)

    for normalized, group in keyword_groups.items():
        knowledge_item_ids = sorted(set(group["knowledge_item_ids"]))
        if len(knowledge_item_ids) < 5:
            continue
        trigger_key = f"keyword:{normalized}"
        existing = session.exec(select(Reflection).where(Reflection.trigger_key == trigger_key)).first()
        if existing:
            continue
        label = group["label"]
        session.add(
            Reflection(
                id=str(uuid4()),
                trigger_key=trigger_key,
                title=f"整理“{label}”主题",
                reason=f"已经有 {len(knowledge_item_ids)} 条知识都提到了“{label}”。",
                question=f"要不要把这些内容整理成一个“{label}”主题？",
                related_knowledge_item_ids=knowledge_item_ids,
            ),
        )

    linked_ids = {link.knowledge_item_id for link in session.exec(select(KnowledgePageItemLink)).all()}
    unclassified_ids = [knowledge_item.id for knowledge_item in knowledge_items if knowledge_item.id not in linked_ids]
    if len(unclassified_ids) >= 10:
        trigger_key = "unclassified:10"
        existing = session.exec(select(Reflection).where(Reflection.trigger_key == trigger_key)).first()
        if not existing:
            session.add(
                Reflection(
                    id=str(uuid4()),
                    trigger_key=trigger_key,
                    title="整理未归类知识",
                    reason=f"当前有 {len(unclassified_ids)} 条知识还没有进入主题。",
                    question="要不要先把这些未归类知识整理成几个主题？",
                    related_knowledge_item_ids=unclassified_ids[:20],
                ),
            )
    session.flush()


def accept_reflection(session: Session, reflection: Reflection) -> KnowledgePage:
    active_item_ids = _active_knowledge_item_ids(session, reflection.related_knowledge_item_ids)
    if not active_item_ids:
        raise ValueError("整理建议里的知识已经没有可用条目")

    page_title = _page_title_for_reflection(reflection)
    page = upsert_knowledge_page(
        session,
        title=page_title,
        summary=reflection.reason,
        body="",
        keywords=_keywords_for_knowledge_item_ids(session, active_item_ids),
        status="draft",
    )
    link_items_to_page(session, page, active_item_ids)

    reflection.status = "accepted"
    reflection.resolved_at = utc_now()
    session.add(reflection)
    session.flush()
    return page


def _keywords_for_knowledge_item_ids(session: Session, knowledge_item_ids: list[str]) -> list[str]:
    knowledge_items = session.exec(select(KnowledgeItem).where(KnowledgeItem.id.in_(knowledge_item_ids))).all()
    keywords: list[str] = []
    for knowledge_item in knowledge_items:
        for keyword in knowledge_item.keywords or []:
            if keyword not in keywords:
                keywords.append(keyword)
    return keywords


def _active_knowledge_item_ids(session: Session, knowledge_item_ids: list[str]) -> list[str]:
    requested_ids = [knowledge_item_id for knowledge_item_id in dict.fromkeys(knowledge_item_ids) if knowledge_item_id]
    if not requested_ids:
        return []
    active_items = session.exec(
        select(KnowledgeItem).where(
            KnowledgeItem.id.in_(requested_ids),
            KnowledgeItem.status.in_(ORGANIZABLE_KNOWLEDGE_STATUSES),
        ),
    ).all()
    active_ids = {item.id for item in active_items}
    return [knowledge_item_id for knowledge_item_id in requested_ids if knowledge_item_id in active_ids]


def create_page_update_suggestions(session: Session, *, knowledge_item_ids: list[str], page_titles: list[str]) -> list[Reflection]:
    created: list[Reflection] = []
    clean_knowledge_item_ids = [knowledge_item_id for knowledge_item_id in dict.fromkeys(knowledge_item_ids) if knowledge_item_id]
    if not clean_knowledge_item_ids:
        return created

    seen_titles: set[str] = set()
    for title in page_titles:
        clean_title = title.strip()
        normalized = normalize_keyword(clean_title)
        if not clean_title or not normalized:
            continue
        if normalized in seen_titles:
            continue
        seen_titles.add(normalized)
        trigger_key = f"external-import-page:{normalized}:{clean_knowledge_item_ids[0]}"
        existing = session.exec(select(Reflection).where(Reflection.trigger_key == trigger_key)).first()
        if existing:
            continue
        reflection = Reflection(
            id=str(uuid4()),
            trigger_key=trigger_key,
            title=clean_title,
            reason="外部 AI 导入了一条已确认知识，并建议把它纳入这个主题页。",
            question=f"要不要把这条已确认知识整理进“{clean_title}”主题页？",
            related_knowledge_item_ids=clean_knowledge_item_ids,
        )
        session.add(reflection)
        created.append(reflection)

    if created:
        session.flush()
    return created


def _page_title_for_reflection(reflection: Reflection) -> str:
    if reflection.trigger_key.startswith("keyword:"):
        quoted = re.search(r"“(.+?)”", reflection.title)
        if quoted:
            return quoted.group(1).strip() or reflection.title
    if reflection.trigger_key == "unclassified:10":
        return "未归类知识"
    return reflection.title


def dismiss_reflection(session: Session, reflection: Reflection) -> None:
    reflection.status = "dismissed"
    reflection.resolved_at = utc_now()
    session.add(reflection)
    session.flush()


def refresh_reflections_after_item_archive(session: Session, knowledge_item_id: str) -> None:
    pending_reflections = session.exec(select(Reflection).where(Reflection.status == "pending")).all()
    for reflection in pending_reflections:
        if knowledge_item_id not in (reflection.related_knowledge_item_ids or []):
            continue

        active_item_ids = _active_knowledge_item_ids(session, reflection.related_knowledge_item_ids)
        if _should_dismiss_after_item_archive(reflection, active_item_ids):
            reflection.status = "dismissed"
            reflection.resolved_at = utc_now()
        else:
            reflection.related_knowledge_item_ids = active_item_ids
            reflection.reason = _refreshed_reason(reflection, len(active_item_ids))
        session.add(reflection)
    session.flush()


def _should_dismiss_after_item_archive(reflection: Reflection, active_item_ids: list[str]) -> bool:
    if reflection.trigger_key.startswith("keyword:"):
        return len(active_item_ids) < 5
    if reflection.trigger_key == "unclassified:10":
        return len(active_item_ids) < 10
    return not active_item_ids


def _refreshed_reason(reflection: Reflection, active_count: int) -> str:
    if reflection.trigger_key.startswith("keyword:"):
        quoted = re.search(r"“(.+?)”", reflection.title)
        label = quoted.group(1).strip() if quoted else reflection.title
        return f"当前有 {active_count} 条知识都提到了“{label}”。"
    if reflection.trigger_key == "unclassified:10":
        return f"当前有 {active_count} 条知识还没有进入主题。"
    return reflection.reason
