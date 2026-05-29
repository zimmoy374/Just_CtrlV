from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from ..models import (
    HandoffPack,
    KnowledgeItem,
    KnowledgePage,
    KnowledgePageItemLink,
    MemoryDecision,
    MemoryProposal,
    ProvenanceEvent,
    SourceItem,
    TaskCheckpoint,
    TaskEvent,
    TaskSession,
    utc_now,
)


EXPORT_VERSION = "0.1"
EXPORT_PAGE_ITEM_STATUSES = {"active"}


def export_knowledge_bundle(session: Session, output_dir: Path) -> Path:
    root = output_dir / "export"
    wiki_dir = root / "wiki"
    sources_dir = root / "sources"
    handoff_packs_dir = root / "handoff_packs"
    root.mkdir(parents=True, exist_ok=True)
    wiki_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)
    handoff_packs_dir.mkdir(parents=True, exist_ok=True)

    pages = session.exec(select(KnowledgePage).order_by(KnowledgePage.updated_at)).all()
    knowledge_items = session.exec(select(KnowledgeItem).order_by(KnowledgeItem.created_at)).all()
    source_items = session.exec(select(SourceItem).order_by(SourceItem.created_at)).all()
    page_links = session.exec(select(KnowledgePageItemLink)).all()
    task_sessions = session.exec(select(TaskSession).order_by(TaskSession.created_at)).all()
    task_events = session.exec(select(TaskEvent).order_by(TaskEvent.created_at)).all()
    task_checkpoints = session.exec(select(TaskCheckpoint).order_by(TaskCheckpoint.created_at)).all()
    memory_proposals = session.exec(select(MemoryProposal).order_by(MemoryProposal.created_at)).all()
    memory_decisions = session.exec(select(MemoryDecision).order_by(MemoryDecision.created_at)).all()
    provenance_events = session.exec(select(ProvenanceEvent).order_by(ProvenanceEvent.occurred_at)).all()
    handoff_packs = session.exec(select(HandoffPack).order_by(HandoffPack.created_at)).all()

    source_by_id = {source_item.id: source_item for source_item in source_items}
    knowledge_items_by_id = {
        knowledge_item.id: knowledge_item
        for knowledge_item in knowledge_items
        if knowledge_item.status in EXPORT_PAGE_ITEM_STATUSES
    }

    _write_manifest(
        root / "manifest.json",
        pages=pages,
        knowledge_items=knowledge_items,
        source_items=source_items,
        task_sessions=task_sessions,
        task_events=task_events,
        task_checkpoints=task_checkpoints,
        memory_proposals=memory_proposals,
        memory_decisions=memory_decisions,
        handoff_packs=handoff_packs,
    )
    _write_index(
        root / "index.md",
        pages=pages,
        knowledge_items=knowledge_items,
        source_items=source_items,
        task_sessions=task_sessions,
        task_events=task_events,
        task_checkpoints=task_checkpoints,
        memory_proposals=memory_proposals,
        memory_decisions=memory_decisions,
        handoff_packs=handoff_packs,
    )
    _write_wiki_pages(wiki_dir, pages=pages, page_links=page_links, knowledge_items_by_id=knowledge_items_by_id)
    _write_items(root / "items.jsonl", knowledge_items=knowledge_items)
    _write_sources(sources_dir, source_items=source_items)
    _write_task_sessions(root / "task_sessions.jsonl", task_sessions=task_sessions)
    _write_task_events(root / "task_events.jsonl", task_events=task_events)
    _write_task_checkpoints(root / "task_checkpoints.jsonl", task_checkpoints=task_checkpoints)
    _write_memory_proposals(root / "memory_proposals.jsonl", memory_proposals=memory_proposals)
    _write_memory_decisions(root / "memory_decisions.jsonl", memory_decisions=memory_decisions)
    _write_handoff_packs(handoff_packs_dir, handoff_packs=handoff_packs)
    _write_provenance(
        root / "provenance.jsonl",
        pages=pages,
        knowledge_items=knowledge_items,
        source_by_id=source_by_id,
        page_links=page_links,
        task_sessions=task_sessions,
        task_checkpoints=task_checkpoints,
        memory_proposals=memory_proposals,
        provenance_events=provenance_events,
        handoff_packs=handoff_packs,
    )
    return root


def _write_manifest(
    path: Path,
    *,
    pages: list[KnowledgePage],
    knowledge_items: list[KnowledgeItem],
    source_items: list[SourceItem],
    task_sessions: list[TaskSession],
    task_events: list[TaskEvent],
    task_checkpoints: list[TaskCheckpoint],
    memory_proposals: list[MemoryProposal],
    memory_decisions: list[MemoryDecision],
    handoff_packs: list[HandoffPack],
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
            "taskSessions": "task_sessions.jsonl",
            "taskEvents": "task_events.jsonl",
            "taskCheckpoints": "task_checkpoints.jsonl",
            "memoryProposals": "memory_proposals.jsonl",
            "memoryDecisions": "memory_decisions.jsonl",
            "handoffPacks": "handoff_packs/",
            "provenance": "provenance.jsonl",
        },
        "counts": {
            "knowledgePages": len(pages),
            "knowledgeItems": len(knowledge_items),
            "sourceItems": len(source_items),
            "taskSessions": len(task_sessions),
            "taskEvents": len(task_events),
            "taskCheckpoints": len(task_checkpoints),
            "memoryProposals": len(memory_proposals),
            "memoryDecisions": len(memory_decisions),
            "handoffPacks": len(handoff_packs),
        },
    }
    _write_json(path, payload)


def _write_index(
    path: Path,
    *,
    pages: list[KnowledgePage],
    knowledge_items: list[KnowledgeItem],
    source_items: list[SourceItem],
    task_sessions: list[TaskSession],
    task_events: list[TaskEvent],
    task_checkpoints: list[TaskCheckpoint],
    memory_proposals: list[MemoryProposal],
    memory_decisions: list[MemoryDecision],
    handoff_packs: list[HandoffPack],
) -> None:
    lines = [
        "# Just Ctrl V Knowledge Export",
        "",
        f"- Generated at: {_dt(utc_now())}",
        f"- Knowledge pages: {len(pages)}",
        f"- Knowledge items: {len(knowledge_items)}",
        f"- Source items: {len(source_items)}",
        f"- Task sessions: {len(task_sessions)}",
        f"- Task events: {len(task_events)}",
        f"- Task checkpoints: {len(task_checkpoints)}",
        f"- Memory proposals: {len(memory_proposals)}",
        f"- Memory decisions: {len(memory_decisions)}",
        f"- Handoff packs: {len(handoff_packs)}",
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
            "- `task_sessions.jsonl`: TaskSession records.",
            "- `task_events.jsonl`: append-only TaskEvent records.",
            "- `task_checkpoints.jsonl`: TaskCheckpoint records.",
            "- `memory_proposals.jsonl`: MemoryProposal records with routing and review fields.",
            "- `memory_decisions.jsonl`: durable proposal and memory review decisions.",
            "- `handoff_packs/`: HandoffPack content and metadata.",
            "- `provenance.jsonl`: durable provenance events plus SourceItem, KnowledgeItem, and KnowledgePage relationships.",
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


def _write_task_sessions(path: Path, *, task_sessions: list[TaskSession]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for task in task_sessions:
            _write_jsonl(
                file,
                {
                    "id": task.id,
                    "title": task.title,
                    "userGoal": task.user_goal,
                    "status": task.status,
                    "activeAgent": task.active_agent,
                    "createdAt": _dt(task.created_at),
                    "updatedAt": _dt(task.updated_at),
                    "lastEventAt": _dt(task.last_event_at),
                    "closedAt": _dt(task.closed_at),
                    "expiresAt": _dt(task.expires_at),
                },
            )


def _write_task_events(path: Path, *, task_events: list[TaskEvent]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for event in task_events:
            _write_jsonl(
                file,
                {
                    "id": event.id,
                    "taskSessionId": event.task_session_id,
                    "type": event.type,
                    "summary": event.summary,
                    "payload": event.payload_json or {},
                    "source": event.source,
                    "sourceRef": event.source_ref,
                    "createdAt": _dt(event.created_at),
                },
            )


def _write_task_checkpoints(path: Path, *, task_checkpoints: list[TaskCheckpoint]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for checkpoint in task_checkpoints:
            _write_jsonl(
                file,
                {
                    "id": checkpoint.id,
                    "taskSessionId": checkpoint.task_session_id,
                    "title": checkpoint.title,
                    "summary": checkpoint.summary,
                    "stateSnapshot": checkpoint.state_snapshot_json or {},
                    "eventFromId": checkpoint.event_from_id,
                    "eventToId": checkpoint.event_to_id,
                    "createdAt": _dt(checkpoint.created_at),
                },
            )


def _write_memory_proposals(path: Path, *, memory_proposals: list[MemoryProposal]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for proposal in memory_proposals:
            _write_jsonl(
                file,
                {
                    "id": proposal.id,
                    "taskSessionId": proposal.task_session_id,
                    "targetStore": proposal.target_store,
                    "type": proposal.type,
                    "title": proposal.title,
                    "body": proposal.body,
                    "structuredPayload": proposal.structured_payload_json or {},
                    "scope": proposal.scope,
                    "evidenceRefs": proposal.evidence_refs or [],
                    "confidence": proposal.confidence,
                    "reviewNote": proposal.review_note,
                    "status": proposal.status,
                    "sourceItemId": proposal.source_item_id,
                    "knowledgeItemId": proposal.knowledge_item_id,
                    "pageId": proposal.page_id,
                    "decisionRef": proposal.decision_ref,
                    "createdAt": _dt(proposal.created_at),
                    "resolvedAt": _dt(proposal.resolved_at),
                },
            )


def _write_memory_decisions(path: Path, *, memory_decisions: list[MemoryDecision]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for decision in memory_decisions:
            _write_jsonl(
                file,
                {
                    "id": decision.id,
                    "decisionType": decision.decision_type,
                    "targetRef": decision.target_ref,
                    "actor": decision.actor,
                    "reason": decision.reason,
                    "policy": decision.policy,
                    "evidenceRefs": decision.evidence_refs or [],
                    "confidence": decision.confidence,
                    "scope": decision.scope,
                    "metadata": decision.metadata_json or {},
                    "createdAt": _dt(decision.created_at),
                },
            )


def _write_handoff_packs(handoff_packs_dir: Path, *, handoff_packs: list[HandoffPack]) -> None:
    index_path = handoff_packs_dir / "index.jsonl"
    with index_path.open("w", encoding="utf-8") as index_file:
        for handoff in handoff_packs:
            extension = _handoff_extension(handoff.format)
            content_file = f"{handoff.id}{extension}"
            metadata_file = f"{handoff.id}.metadata.json"
            (handoff_packs_dir / content_file).write_text(handoff.content or "", encoding="utf-8")
            metadata = {
                "id": handoff.id,
                "taskSessionId": handoff.task_session_id,
                "format": handoff.format,
                "contentFile": content_file,
                "budget": handoff.budget_json or {},
                "createdAt": _dt(handoff.created_at),
            }
            _write_json(handoff_packs_dir / metadata_file, metadata)
            _write_jsonl(index_file, {**metadata, "metadataFile": metadata_file})


def _write_provenance(
    path: Path,
    *,
    pages: list[KnowledgePage],
    knowledge_items: list[KnowledgeItem],
    source_by_id: dict[str, SourceItem],
    page_links: list[KnowledgePageItemLink],
    task_sessions: list[TaskSession],
    task_checkpoints: list[TaskCheckpoint],
    memory_proposals: list[MemoryProposal],
    provenance_events: list[ProvenanceEvent],
    handoff_packs: list[HandoffPack],
) -> None:
    with path.open("w", encoding="utf-8") as file:
        for event in provenance_events:
            _write_jsonl(
                file,
                {
                    "type": event.event_type,
                    "from": event.from_ref,
                    "to": event.to_ref,
                    "actor": event.actor,
                    "reason": event.reason,
                    "evidenceRefs": event.evidence_refs or [],
                    "payload": event.payload_json or {},
                    "occurredAt": _dt(event.occurred_at),
                },
            )
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
        task_ids = {task.id for task in task_sessions}
        source_ids = set(source_by_id)
        knowledge_item_ids_all = {knowledge_item.id for knowledge_item in knowledge_items}
        knowledge_page_ids_all = {page.id for page in pages}
        for proposal in memory_proposals:
            if proposal.task_session_id in task_ids:
                _write_jsonl(
                    file,
                    {
                        "type": "proposal_for_task",
                        "from": f"proposal:{proposal.id}",
                        "to": f"task:{proposal.task_session_id}",
                    },
                )
            if proposal.source_item_id in source_ids:
                _write_jsonl(
                    file,
                    {
                        "type": "proposal_created_source",
                        "from": f"proposal:{proposal.id}",
                        "to": f"source:{proposal.source_item_id}",
                    },
                )
            if proposal.status == "accepted" and proposal.knowledge_item_id in knowledge_item_ids_all:
                _write_jsonl(
                    file,
                    {
                        "type": "accepted_proposal_created_item",
                        "from": f"proposal:{proposal.id}",
                        "to": f"item:{proposal.knowledge_item_id}",
                    },
                )
            if proposal.status == "accepted" and proposal.page_id in knowledge_page_ids_all:
                _write_jsonl(
                    file,
                    {
                        "type": "accepted_proposal_created_page",
                        "from": f"proposal:{proposal.id}",
                        "to": f"page:{proposal.page_id}",
                    },
                )
        for checkpoint in task_checkpoints:
            if checkpoint.task_session_id in task_ids:
                _write_jsonl(
                    file,
                    {
                        "type": "checkpoint_for_task",
                        "from": f"checkpoint:{checkpoint.id}",
                        "to": f"task:{checkpoint.task_session_id}",
                    },
                )
        for handoff in handoff_packs:
            if handoff.task_session_id in task_ids:
                _write_jsonl(
                    file,
                    {
                        "type": "handoff_for_task",
                        "from": f"handoff:{handoff.id}",
                        "to": f"task:{handoff.task_session_id}",
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


def _handoff_extension(format: str) -> str:
    if format == "markdown":
        return ".md"
    if format == "json":
        return ".json"
    return ".txt"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(file, payload: dict[str, Any]) -> None:
    file.write(json.dumps(payload, ensure_ascii=False) + "\n")
