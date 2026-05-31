from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from ..models import (
    Entity,
    HandoffPack,
    KnowledgeItem,
    KnowledgePage,
    KnowledgePageItemLink,
    MemoryConflict,
    MemoryDecision,
    MemoryFact,
    MemoryProposal,
    MemoryRelation,
    ProvenanceEvent,
    SourceItem,
    TaskCheckpoint,
    TaskDigest,
    TaskEvent,
    TaskSession,
    utc_now,
)
from .boundary import DERIVED_PROJECTIONS, DURABLE_EXPORT_CONTENTS, EXPORT_VERSION


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
    task_digests = session.exec(select(TaskDigest).order_by(TaskDigest.updated_at)).all()
    memory_proposals = session.exec(select(MemoryProposal).order_by(MemoryProposal.created_at)).all()
    memory_decisions = session.exec(select(MemoryDecision).order_by(MemoryDecision.created_at)).all()
    provenance_events = session.exec(select(ProvenanceEvent).order_by(ProvenanceEvent.occurred_at)).all()
    handoff_packs = session.exec(select(HandoffPack).order_by(HandoffPack.created_at)).all()
    entities = session.exec(select(Entity).order_by(Entity.created_at)).all()
    memory_facts = session.exec(select(MemoryFact).order_by(MemoryFact.created_at)).all()
    memory_relations = session.exec(select(MemoryRelation).order_by(MemoryRelation.created_at)).all()
    memory_conflicts = session.exec(select(MemoryConflict).order_by(MemoryConflict.created_at)).all()

    source_by_id = {source_item.id: source_item for source_item in source_items}
    proposal_by_item_id = {
        proposal.knowledge_item_id: proposal
        for proposal in memory_proposals
        if proposal.knowledge_item_id
    }
    proposal_by_page_id = {
        proposal.page_id: proposal
        for proposal in memory_proposals
        if proposal.page_id
    }
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
        page_links=page_links,
        task_sessions=task_sessions,
        task_events=task_events,
        task_checkpoints=task_checkpoints,
        task_digests=task_digests,
        memory_proposals=memory_proposals,
        memory_decisions=memory_decisions,
        provenance_events=provenance_events,
        handoff_packs=handoff_packs,
        entities=entities,
        memory_facts=memory_facts,
        memory_relations=memory_relations,
        memory_conflicts=memory_conflicts,
    )
    _write_index(
        root / "index.md",
        pages=pages,
        knowledge_items=knowledge_items,
        source_items=source_items,
        page_links=page_links,
        task_sessions=task_sessions,
        task_events=task_events,
        task_checkpoints=task_checkpoints,
        task_digests=task_digests,
        memory_proposals=memory_proposals,
        memory_decisions=memory_decisions,
        handoff_packs=handoff_packs,
        entities=entities,
        memory_facts=memory_facts,
        memory_relations=memory_relations,
        memory_conflicts=memory_conflicts,
    )
    _write_wiki_pages(wiki_dir, pages=pages, page_links=page_links, knowledge_items_by_id=knowledge_items_by_id)
    _write_pages(root / "pages.jsonl", pages=pages, proposal_by_page_id=proposal_by_page_id)
    _write_page_item_links(root / "page_item_links.jsonl", page_links=page_links)
    _write_items(
        root / "items.jsonl",
        knowledge_items=knowledge_items,
        source_by_id=source_by_id,
        proposal_by_item_id=proposal_by_item_id,
    )
    _write_rules(root / "rules.jsonl", knowledge_items=knowledge_items, source_by_id=source_by_id, proposal_by_item_id=proposal_by_item_id)
    _write_procedures(
        root / "procedures.jsonl",
        knowledge_items=knowledge_items,
        source_by_id=source_by_id,
        proposal_by_item_id=proposal_by_item_id,
    )
    _write_sources(sources_dir, source_items=source_items)
    _write_task_sessions(root / "task_sessions.jsonl", task_sessions=task_sessions)
    _write_task_events(root / "task_events.jsonl", task_events=task_events)
    _write_task_checkpoints(root / "task_checkpoints.jsonl", task_checkpoints=task_checkpoints)
    _write_task_digests(root / "task_digests.jsonl", task_digests=task_digests)
    _write_memory_proposals(root / "memory_proposals.jsonl", memory_proposals=memory_proposals)
    _write_memory_decisions(root / "memory_decisions.jsonl", memory_decisions=memory_decisions)
    _write_entities(root / "entities.jsonl", entities=entities)
    _write_memory_facts(root / "facts.jsonl", memory_facts=memory_facts)
    _write_memory_relations(root / "relations.jsonl", memory_relations=memory_relations)
    _write_memory_conflicts(root / "conflicts.jsonl", memory_conflicts=memory_conflicts)
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
        memory_facts=memory_facts,
        memory_relations=memory_relations,
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
    page_links: list[KnowledgePageItemLink],
    task_sessions: list[TaskSession],
    task_events: list[TaskEvent],
    task_checkpoints: list[TaskCheckpoint],
    task_digests: list[TaskDigest],
    memory_proposals: list[MemoryProposal],
    memory_decisions: list[MemoryDecision],
    provenance_events: list[ProvenanceEvent],
    handoff_packs: list[HandoffPack],
    entities: list[Entity],
    memory_facts: list[MemoryFact],
    memory_relations: list[MemoryRelation],
    memory_conflicts: list[MemoryConflict],
) -> None:
    rules = [item for item in knowledge_items if item.knowledge_type == "rule_preference"]
    procedures = [item for item in knowledge_items if item.knowledge_type == "procedure_lesson"]
    payload = {
        "exportVersion": EXPORT_VERSION,
        "generatedAt": _dt(utc_now()),
        "description": "second brain knowledge export bundle",
        "contents": DURABLE_EXPORT_CONTENTS,
        "counts": {
            "knowledgePages": len(pages),
            "knowledgePageItemLinks": len(page_links),
            "knowledgeItems": len(knowledge_items),
            "rules": len(rules),
            "procedures": len(procedures),
            "sourceItems": len(source_items),
            "taskSessions": len(task_sessions),
            "taskEvents": len(task_events),
            "taskCheckpoints": len(task_checkpoints),
            "taskDigests": len(task_digests),
            "memoryProposals": len(memory_proposals),
            "memoryDecisions": len(memory_decisions),
            "provenanceEvents": len(provenance_events),
            "entities": len(entities),
            "facts": len(memory_facts),
            "relations": len(memory_relations),
            "conflicts": len(memory_conflicts),
            "handoffPacks": len(handoff_packs),
        },
        "durableStores": [
            _store_manifest("source_vault", "sources/", len(source_items), sourceOfTruth=True),
            _store_manifest("semantic_knowledge", "items.jsonl", len(knowledge_items), sourceOfTruth=True),
            _store_manifest("knowledge_pages", "pages.jsonl", len(pages), sourceOfTruth=True),
            _store_manifest("knowledge_page_item_links", "page_item_links.jsonl", len(page_links), sourceOfTruth=True),
            _store_manifest("rule_preference", "rules.jsonl", len(rules), sourceOfTruth=False, physicalStore="knowledge_items"),
            _store_manifest("procedure_lesson", "procedures.jsonl", len(procedures), sourceOfTruth=False, physicalStore="knowledge_items"),
            _store_manifest("task_memory_sessions", "task_sessions.jsonl", len(task_sessions), sourceOfTruth=True),
            _store_manifest("task_memory_events", "task_events.jsonl", len(task_events), sourceOfTruth=True),
            _store_manifest("task_memory_checkpoints", "task_checkpoints.jsonl", len(task_checkpoints), sourceOfTruth=True),
            _store_manifest("task_memory_digests", "task_digests.jsonl", len(task_digests), sourceOfTruth=False, physicalStore="task_events"),
            _store_manifest("task_memory_handoffs", "handoff_packs/", len(handoff_packs), sourceOfTruth=True),
            _store_manifest("memory_proposals", "memory_proposals.jsonl", len(memory_proposals), sourceOfTruth=True),
            _store_manifest("memory_decisions", "memory_decisions.jsonl", len(memory_decisions), sourceOfTruth=True),
            _store_manifest("profile_entities", "entities.jsonl", len(entities), sourceOfTruth=True),
            _store_manifest("profile_facts", "facts.jsonl", len(memory_facts), sourceOfTruth=True),
            _store_manifest("profile_relations", "relations.jsonl", len(memory_relations), sourceOfTruth=True),
            _store_manifest("memory_conflicts", "conflicts.jsonl", len(memory_conflicts), sourceOfTruth=True),
            _store_manifest("provenance", "provenance.jsonl", len(provenance_events), sourceOfTruth=True),
        ],
        "derivedProjections": DERIVED_PROJECTIONS,
    }
    _write_json(path, payload)


def _write_index(
    path: Path,
    *,
    pages: list[KnowledgePage],
    knowledge_items: list[KnowledgeItem],
    source_items: list[SourceItem],
    page_links: list[KnowledgePageItemLink],
    task_sessions: list[TaskSession],
    task_events: list[TaskEvent],
    task_checkpoints: list[TaskCheckpoint],
    task_digests: list[TaskDigest],
    memory_proposals: list[MemoryProposal],
    memory_decisions: list[MemoryDecision],
    handoff_packs: list[HandoffPack],
    entities: list[Entity],
    memory_facts: list[MemoryFact],
    memory_relations: list[MemoryRelation],
    memory_conflicts: list[MemoryConflict],
) -> None:
    rules = [item for item in knowledge_items if item.knowledge_type == "rule_preference"]
    procedures = [item for item in knowledge_items if item.knowledge_type == "procedure_lesson"]
    lines = [
        "# second brain Knowledge Export",
        "",
        f"- Generated at: {_dt(utc_now())}",
        f"- Knowledge pages: {len(pages)}",
        f"- Page item links: {len(page_links)}",
        f"- Knowledge items: {len(knowledge_items)}",
        f"- Rules: {len(rules)}",
        f"- Procedures: {len(procedures)}",
        f"- Source items: {len(source_items)}",
        f"- Task sessions: {len(task_sessions)}",
        f"- Task events: {len(task_events)}",
        f"- Task checkpoints: {len(task_checkpoints)}",
        f"- Task digests: {len(task_digests)}",
        f"- Memory proposals: {len(memory_proposals)}",
        f"- Memory decisions: {len(memory_decisions)}",
        f"- Entities: {len(entities)}",
        f"- Profile facts: {len(memory_facts)}",
        f"- Profile relations: {len(memory_relations)}",
        f"- Memory conflicts: {len(memory_conflicts)}",
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
            "- `pages.jsonl`: KnowledgePage records.",
            "- `page_item_links.jsonl`: KnowledgePageItemLink records.",
            "- `rules.jsonl`: rule/preference store view backed by typed KnowledgeItem records.",
            "- `procedures.jsonl`: procedure/lesson store view backed by typed KnowledgeItem records.",
            "- `task_sessions.jsonl`: TaskSession records.",
            "- `task_events.jsonl`: append-only TaskEvent records.",
            "- `task_checkpoints.jsonl`: TaskCheckpoint records.",
            "- `memory_proposals.jsonl`: MemoryProposal records with routing and review fields.",
            "- `memory_decisions.jsonl`: durable proposal and memory review decisions.",
            "- `entities.jsonl`: profile temporal graph Entity records.",
            "- `facts.jsonl`: profile temporal graph MemoryFact records.",
            "- `relations.jsonl`: profile temporal graph MemoryRelation records.",
            "- `conflicts.jsonl`: open and resolved MemoryConflict records.",
            "- `handoff_packs/`: HandoffPack content and metadata.",
            "- `provenance.jsonl`: durable provenance events plus SourceItem, KnowledgeItem, and KnowledgePage relationships.",
            "- `sources/`: SourceItem original materials and metadata.",
            "",
            "## Export Boundary",
            "",
            "- Durable records and store views are exported as files listed in `manifest.json`.",
            "- Derived projections such as SQLite FTS are not exported; rebuild them from durable records.",
            "- `provenance.jsonl` is hash chained for audit inspection, not decentralized consensus.",
            "",
        ],
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _store_manifest(
    name: str,
    path: str,
    record_count: int,
    *,
    sourceOfTruth: bool,
    physicalStore: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "path": path,
        "recordCount": record_count,
        "sourceOfTruth": sourceOfTruth,
    }
    if physicalStore:
        payload["physicalStore"] = physicalStore
    return payload


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


def _write_pages(
    path: Path,
    *,
    pages: list[KnowledgePage],
    proposal_by_page_id: dict[str, MemoryProposal],
) -> None:
    with path.open("w", encoding="utf-8") as file:
        for page in pages:
            proposal = proposal_by_page_id.get(page.id)
            _write_jsonl(
                file,
                {
                    "id": page.id,
                    "title": page.title,
                    "summary": page.summary,
                    "body": page.body,
                    "keywords": page.keywords or [],
                    "status": page.status,
                    "scope": proposal.scope if proposal else "workspace",
                    "evidenceRefs": proposal.evidence_refs if proposal else [],
                    "decisionRef": proposal.decision_ref if proposal else None,
                    "sourceProposalRef": f"proposal:{proposal.id}" if proposal else None,
                    "createdAt": _dt(page.created_at),
                    "updatedAt": _dt(page.updated_at),
                },
            )


def _write_page_item_links(path: Path, *, page_links: list[KnowledgePageItemLink]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for link in page_links:
            _write_jsonl(
                file,
                {
                    "id": link.id,
                    "pageRef": f"page:{link.page_id}",
                    "itemRef": f"item:{link.knowledge_item_id}",
                    "createdAt": _dt(link.created_at),
                },
            )


def _write_items(
    path: Path,
    *,
    knowledge_items: list[KnowledgeItem],
    source_by_id: dict[str, SourceItem],
    proposal_by_item_id: dict[str, MemoryProposal],
) -> None:
    with path.open("w", encoding="utf-8") as file:
        for knowledge_item in knowledge_items:
            _write_jsonl(file, _item_export_payload(knowledge_item, source_by_id, proposal_by_item_id))


def _write_rules(
    path: Path,
    *,
    knowledge_items: list[KnowledgeItem],
    source_by_id: dict[str, SourceItem],
    proposal_by_item_id: dict[str, MemoryProposal],
) -> None:
    with path.open("w", encoding="utf-8") as file:
        for knowledge_item in knowledge_items:
            if knowledge_item.knowledge_type != "rule_preference":
                continue
            _write_jsonl(file, _item_export_payload(knowledge_item, source_by_id, proposal_by_item_id, store="rule_preference"))


def _write_procedures(
    path: Path,
    *,
    knowledge_items: list[KnowledgeItem],
    source_by_id: dict[str, SourceItem],
    proposal_by_item_id: dict[str, MemoryProposal],
) -> None:
    with path.open("w", encoding="utf-8") as file:
        for knowledge_item in knowledge_items:
            if knowledge_item.knowledge_type != "procedure_lesson":
                continue
            _write_jsonl(file, _item_export_payload(knowledge_item, source_by_id, proposal_by_item_id, store="procedure_lesson"))


def _item_export_payload(
    knowledge_item: KnowledgeItem,
    source_by_id: dict[str, SourceItem],
    proposal_by_item_id: dict[str, MemoryProposal],
    *,
    store: str | None = None,
) -> dict[str, Any]:
    source_item = source_by_id.get(knowledge_item.source_item_id)
    source_metadata = source_item.metadata_json if source_item else {}
    proposal = proposal_by_item_id.get(knowledge_item.id)
    evidence_refs = _dedupe_strings(
        [
            *(proposal.evidence_refs if proposal else []),
            *_string_list(source_metadata.get("evidenceRefs")),
            f"source:{knowledge_item.source_item_id}" if knowledge_item.source_item_id else "",
        ],
    )
    target_store = store or (proposal.target_store if proposal else source_metadata.get("targetStore")) or _target_store_for_knowledge_type(
        knowledge_item.knowledge_type,
    )
    return {
        "id": knowledge_item.id,
        "ref": f"item:{knowledge_item.id}",
        "sourceItemRef": f"source:{knowledge_item.source_item_id}" if knowledge_item.source_item_id else None,
        "cardId": knowledge_item.card_id,
        "title": knowledge_item.title,
        "summary": knowledge_item.summary,
        "content": knowledge_item.content,
        "keywords": knowledge_item.keywords or [],
        "source": knowledge_item.source,
        "sourceRef": knowledge_item.source_ref,
        "knowledgeType": knowledge_item.knowledge_type,
        "targetStore": target_store,
        "status": knowledge_item.status,
        "scope": (proposal.scope if proposal else source_metadata.get("scope")) or "workspace",
        "visibility": source_metadata.get("visibility") or "workspace",
        "privacyLabels": _string_list(source_metadata.get("privacyLabels")),
        "evidenceRefs": evidence_refs,
        "decisionRef": proposal.decision_ref if proposal else None,
        "sourceProposalRef": f"proposal:{proposal.id}" if proposal else None,
        "createdAt": _dt(knowledge_item.created_at),
        "updatedAt": _dt(knowledge_item.updated_at),
    }


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


def _write_task_digests(path: Path, *, task_digests: list[TaskDigest]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for digest in task_digests:
            _write_jsonl(
                file,
                {
                    "taskSessionId": digest.task_session_id,
                    "summary": digest.summary,
                    "done": digest.done_json or [],
                    "decisions": digest.decisions_json or [],
                    "openQuestions": digest.open_questions_json or [],
                    "risks": digest.risks_json or [],
                    "filesTouched": digest.files_touched_json or [],
                    "sourceRefs": digest.source_refs_json or [],
                    "eventFromId": digest.event_from_id,
                    "eventToId": digest.event_to_id,
                    "eventCount": digest.event_count,
                    "updatedAt": _dt(digest.updated_at),
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


def _write_entities(path: Path, *, entities: list[Entity]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for entity in entities:
            _write_jsonl(
                file,
                {
                    "id": entity.id,
                    "type": entity.type,
                    "name": entity.name,
                    "aliases": entity.aliases or [],
                    "sourceRefs": entity.source_refs or [],
                    "createdAt": _dt(entity.created_at),
                    "updatedAt": _dt(entity.updated_at),
                },
            )


def _write_memory_facts(path: Path, *, memory_facts: list[MemoryFact]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for fact in memory_facts:
            _write_jsonl(
                file,
                {
                    "id": fact.id,
                    "subjectEntityRef": f"entity:{fact.subject_entity_id}",
                    "predicate": fact.predicate,
                    "objectValue": fact.object_value,
                    "objectEntityRef": f"entity:{fact.object_entity_id}" if fact.object_entity_id else None,
                    "confidence": fact.confidence,
                    "validAt": _dt(fact.valid_at),
                    "invalidAt": _dt(fact.invalid_at),
                    "supersededBy": f"fact:{fact.superseded_by}" if fact.superseded_by else None,
                    "evidenceRefs": fact.evidence_refs or [],
                    "status": fact.status,
                    "scope": fact.scope,
                    "sourceProposalRef": f"proposal:{fact.source_proposal_id}" if fact.source_proposal_id else None,
                    "decisionRef": fact.decision_ref,
                    "createdAt": _dt(fact.created_at),
                    "updatedAt": _dt(fact.updated_at),
                },
            )


def _write_memory_relations(path: Path, *, memory_relations: list[MemoryRelation]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for relation in memory_relations:
            _write_jsonl(
                file,
                {
                    "id": relation.id,
                    "fromEntityRef": f"entity:{relation.from_entity_id}",
                    "relationType": relation.relation_type,
                    "toEntityRef": f"entity:{relation.to_entity_id}",
                    "confidence": relation.confidence,
                    "validAt": _dt(relation.valid_at),
                    "invalidAt": _dt(relation.invalid_at),
                    "supersededBy": f"relation:{relation.superseded_by}" if relation.superseded_by else None,
                    "evidenceRefs": relation.evidence_refs or [],
                    "status": relation.status,
                    "scope": relation.scope,
                    "sourceProposalRef": f"proposal:{relation.source_proposal_id}" if relation.source_proposal_id else None,
                    "decisionRef": relation.decision_ref,
                    "createdAt": _dt(relation.created_at),
                    "updatedAt": _dt(relation.updated_at),
                },
            )


def _write_memory_conflicts(path: Path, *, memory_conflicts: list[MemoryConflict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for conflict in memory_conflicts:
            _write_jsonl(
                file,
                {
                    "id": conflict.id,
                    "conflictType": conflict.conflict_type,
                    "factRefs": [f"fact:{fact_id}" for fact_id in conflict.fact_ids or []],
                    "relationRefs": [f"relation:{relation_id}" for relation_id in conflict.relation_ids or []],
                    "reason": conflict.reason,
                    "status": conflict.status,
                    "resolution": conflict.resolution,
                    "scope": conflict.scope,
                    "decisionRef": conflict.decision_ref,
                    "createdAt": _dt(conflict.created_at),
                    "resolvedAt": _dt(conflict.resolved_at),
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
    memory_facts: list[MemoryFact],
    memory_relations: list[MemoryRelation],
    provenance_events: list[ProvenanceEvent],
    handoff_packs: list[HandoffPack],
) -> None:
    rows: list[dict[str, Any]] = []
    for event in provenance_events:
        rows.append(
            {
                "id": event.id,
                "type": event.event_type,
                "from": event.from_ref,
                "to": event.to_ref,
                "actor": event.actor,
                "reason": event.reason,
                "evidenceRefs": event.evidence_refs or [],
                "payload": event.payload_json or {},
                "occurredAt": _dt(event.occurred_at),
                "source": "durable_provenance_event",
            },
        )

    for knowledge_item in knowledge_items:
        if knowledge_item.source_item_id in source_by_id:
            rows.append(
                {
                    "type": "derived_from",
                    "from": f"item:{knowledge_item.id}",
                    "to": f"source:{knowledge_item.source_item_id}",
                    "source": "export_derived_relationship",
                },
            )

    for fact in memory_facts:
        for evidence_ref in fact.evidence_refs or []:
            rows.append(
                {
                    "type": "fact_supported_by",
                    "from": f"fact:{fact.id}",
                    "to": evidence_ref,
                    "source": "export_derived_relationship",
                },
            )
        if fact.superseded_by:
            rows.append(
                {
                    "type": "fact_superseded",
                    "from": f"fact:{fact.id}",
                    "to": f"fact:{fact.superseded_by}",
                    "source": "export_derived_relationship",
                },
            )

    for relation in memory_relations:
        rows.append(
            {
                "type": "relation_between_entities",
                "from": f"relation:{relation.id}",
                "to": f"entity:{relation.from_entity_id}",
                "source": "export_derived_relationship",
            },
        )
        rows.append(
            {
                "type": "relation_between_entities",
                "from": f"relation:{relation.id}",
                "to": f"entity:{relation.to_entity_id}",
                "source": "export_derived_relationship",
            },
        )
        for evidence_ref in relation.evidence_refs or []:
            rows.append(
                {
                    "type": "relation_supported_by",
                    "from": f"relation:{relation.id}",
                    "to": evidence_ref,
                    "source": "export_derived_relationship",
                },
            )

    task_ids = {task.id for task in task_sessions}
    source_ids = set(source_by_id)
    knowledge_item_ids_all = {knowledge_item.id for knowledge_item in knowledge_items}
    knowledge_page_ids_all = {page.id for page in pages}
    for proposal in memory_proposals:
        if proposal.task_session_id in task_ids:
            rows.append(
                {
                    "type": "proposal_for_task",
                    "from": f"proposal:{proposal.id}",
                    "to": f"task:{proposal.task_session_id}",
                    "source": "export_derived_relationship",
                },
            )
        if proposal.source_item_id in source_ids:
            rows.append(
                {
                    "type": "proposal_created_source",
                    "from": f"proposal:{proposal.id}",
                    "to": f"source:{proposal.source_item_id}",
                    "source": "export_derived_relationship",
                },
            )
        if proposal.status == "accepted" and proposal.knowledge_item_id in knowledge_item_ids_all:
            rows.append(
                {
                    "type": "accepted_proposal_created_item",
                    "from": f"proposal:{proposal.id}",
                    "to": f"item:{proposal.knowledge_item_id}",
                    "source": "export_derived_relationship",
                },
            )
        if proposal.status == "accepted" and proposal.page_id in knowledge_page_ids_all:
            rows.append(
                {
                    "type": "accepted_proposal_created_page",
                    "from": f"proposal:{proposal.id}",
                    "to": f"page:{proposal.page_id}",
                    "source": "export_derived_relationship",
                },
            )

    for checkpoint in task_checkpoints:
        if checkpoint.task_session_id in task_ids:
            rows.append(
                {
                    "type": "checkpoint_for_task",
                    "from": f"checkpoint:{checkpoint.id}",
                    "to": f"task:{checkpoint.task_session_id}",
                    "source": "export_derived_relationship",
                },
            )

    for handoff in handoff_packs:
        if handoff.task_session_id in task_ids:
            rows.append(
                {
                    "type": "handoff_for_task",
                    "from": f"handoff:{handoff.id}",
                    "to": f"task:{handoff.task_session_id}",
                    "source": "export_derived_relationship",
                },
            )

    page_ids = {page.id for page in pages}
    knowledge_item_ids = {
        knowledge_item.id for knowledge_item in knowledge_items if knowledge_item.status in EXPORT_PAGE_ITEM_STATUSES
    }
    for link in page_links:
        if link.page_id in page_ids and link.knowledge_item_id in knowledge_item_ids:
            rows.append(
                {
                    "type": "included_in_page",
                    "from": f"item:{link.knowledge_item_id}",
                    "to": f"page:{link.page_id}",
                    "source": "export_derived_relationship",
                },
            )

    with path.open("w", encoding="utf-8") as file:
        previous_hash = ""
        for row in rows:
            previous_hash = _write_hash_chained_jsonl(file, row, previous_hash)


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


def _target_store_for_knowledge_type(knowledge_type: str) -> str:
    if knowledge_type == "rule_preference":
        return "rule_preference"
    if knowledge_type == "procedure_lesson":
        return "procedure_lesson"
    return "semantic_knowledge"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _dedupe_strings(values: list[str]) -> list[str]:
    return [item for item in dict.fromkeys(values) if item]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(file, payload: dict[str, Any]) -> None:
    file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_hash_chained_jsonl(file, payload: dict[str, Any], previous_hash: str) -> str:
    chained = {**payload, "previousHash": previous_hash or None}
    digest = sha256(json.dumps(chained, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    _write_jsonl(file, {**chained, "hash": digest})
    return digest
