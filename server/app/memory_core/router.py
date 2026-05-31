from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlmodel import Session

from ..knowledge_core.lifecycle import commit_knowledge_item
from ..knowledge_core.source_items import upsert_source_item, validate_choice
from ..models import MemoryProposal, utc_now
from ..wiki.pages import upsert_knowledge_page
from .decisions import record_memory_decision, record_provenance_event
from .profile_graph import accept_profile_graph_proposal, validate_profile_graph_proposal
from .protocol import DEFAULT_PROPOSAL_TARGET_STORES, MEMORY_TARGET_STORES, MemoryQuery, MemorySlice, MemoryStore
from .stores import ProfileTemporalGraphStore, SemanticKnowledgeStore, TaskMemoryStore


class MemoryRouter:
    def __init__(self, stores: Iterable[MemoryStore] | None = None) -> None:
        self._stores: dict[str, MemoryStore] = {}
        for store in stores or []:
            self.register(store)

    def register(self, store: MemoryStore) -> None:
        self._stores[store.name] = store

    def get_store(self, name: str) -> MemoryStore | None:
        return self._stores.get(name)

    def retrieve(
        self,
        session: Session,
        query: MemoryQuery,
        *,
        store_names: Iterable[str] | None = None,
    ) -> list[MemorySlice]:
        stores = [self._stores[name] for name in store_names or self._stores.keys() if name in self._stores]
        slices: list[MemorySlice] = []
        for store in stores:
            slices.extend(store.retrieve(session, query))
        return sorted(slices, key=lambda item: item.score, reverse=True)

    def rebuild_projections(
        self,
        session: Session,
        *,
        store_names: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        stores = [self._stores[name] for name in store_names or self._stores.keys() if name in self._stores]
        return [dict(store.rebuild_projection(session)) for store in stores]

    def accept_proposal(self, session: Session, proposal: MemoryProposal) -> MemoryProposal:
        if proposal.status != "pending":
            raise ValueError("只有 pending 的记忆候选可以接受")

        target_store = proposal.target_store or DEFAULT_PROPOSAL_TARGET_STORES.get(proposal.type, "")
        validate_choice(target_store, MEMORY_TARGET_STORES, "memoryTargetStore")
        if not proposal.title.strip():
            raise ValueError("MemoryProposal title 不能为空")
        if target_store == "profile_temporal_graph":
            validate_profile_graph_proposal(session, proposal)
        if target_store != "profile_temporal_graph" and proposal.type != "page_update" and not proposal.body.strip():
            raise ValueError("MemoryProposal body 不能为空")

        routed_decision = record_memory_decision(
            session,
            decision_type="proposal_routed",
            target_ref=f"proposal:{proposal.id}",
            reason=f"Route proposal to {target_store}",
            evidence_refs=proposal.evidence_refs or [],
            confidence=proposal.confidence,
            scope=proposal.scope,
            metadata={"targetStore": target_store, "proposalType": proposal.type},
        )
        record_provenance_event(
            session,
            event_type="proposal_routed",
            from_ref=f"proposal:{proposal.id}",
            to_ref=f"store:{target_store}",
            reason=f"Route proposal to {target_store}",
            evidence_refs=proposal.evidence_refs or [],
            payload={"decisionRef": f"decision:{routed_decision.id}", "targetStore": target_store},
        )

        if target_store == "profile_temporal_graph":
            accepted = accept_profile_graph_proposal(
                session,
                proposal,
                target_store=target_store,
                routed_decision=routed_decision,
            )
            session.add(accepted)
            session.flush()
            return accepted

        if target_store == "semantic_knowledge" and proposal.type == "page_update":
            page = upsert_knowledge_page(
                session,
                title=proposal.title,
                summary=proposal.body,
                body=proposal.structured_payload_json.get("body", ""),
                keywords=[proposal.type, target_store],
                status="draft",
            )
            proposal.page_id = page.id
            target_ref = f"page:{page.id}"
            created_event_type = "accepted_proposal_created_page"
        else:
            source_item = upsert_source_item(
                session,
                source="second_brain",
                external_id=f"memory-proposal:{proposal.id}",
                kind="agent_selection",
                title=proposal.title,
                content_text=proposal.body,
                metadata={
                    "proposalType": proposal.type,
                    "targetStore": target_store,
                    "scope": proposal.scope,
                    "taskSessionId": proposal.task_session_id,
                    "evidenceRefs": proposal.evidence_refs,
                    "structuredPayload": proposal.structured_payload_json or {},
                },
                status="active",
            )
            knowledge_item = commit_knowledge_item(
                session,
                source_item=source_item,
                knowledge_type=_knowledge_type_for_target_store(target_store),
                title=proposal.title,
                summary=proposal.body[:160],
                content=proposal.body,
                keywords=[proposal.type, target_store],
                source_ref=f"proposal:{proposal.id}",
                status="active",
            )
            proposal.source_item_id = source_item.id
            proposal.knowledge_item_id = knowledge_item.id
            target_ref = f"item:{knowledge_item.id}"
            created_event_type = "accepted_proposal_created_item"
            record_provenance_event(
                session,
                event_type="proposal_created_source",
                from_ref=f"proposal:{proposal.id}",
                to_ref=f"source:{source_item.id}",
                reason="Accepted proposal materialized source evidence",
                evidence_refs=proposal.evidence_refs or [],
                payload={"targetStore": target_store},
            )

        accepted_decision = record_memory_decision(
            session,
            decision_type="proposal_accepted",
            target_ref=f"proposal:{proposal.id}",
            reason=proposal.review_note or f"Accepted into {target_store}",
            evidence_refs=proposal.evidence_refs or [],
            confidence=proposal.confidence,
            scope=proposal.scope,
            metadata={"targetStore": target_store, "createdRef": target_ref, "routedDecisionRef": f"decision:{routed_decision.id}"},
        )
        record_provenance_event(
            session,
            event_type=created_event_type,
            from_ref=f"proposal:{proposal.id}",
            to_ref=target_ref,
            reason=proposal.review_note or f"Accepted into {target_store}",
            evidence_refs=proposal.evidence_refs or [],
            payload={"decisionRef": f"decision:{accepted_decision.id}", "targetStore": target_store},
        )

        proposal.target_store = target_store
        proposal.decision_ref = f"decision:{accepted_decision.id}"
        proposal.status = "accepted"
        proposal.resolved_at = utc_now()
        session.add(proposal)
        session.flush()
        return proposal


def create_default_memory_router() -> MemoryRouter:
    return MemoryRouter(
        [
            SemanticKnowledgeStore(),
            ProfileTemporalGraphStore(),
            TaskMemoryStore(),
        ],
    )


def _knowledge_type_for_target_store(target_store: str) -> str:
    if target_store == "rule_preference":
        return "rule_preference"
    if target_store == "procedure_lesson":
        return "procedure_lesson"
    return "fragment"
