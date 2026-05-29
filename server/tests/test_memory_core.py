from __future__ import annotations

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from server.app.indexing.sqlite_fts import init_knowledge_search_index
from server.app.memory_core.protocol import MemoryQuery, MemoryRef
from server.app.memory_core.router import MemoryRouter
from server.app.memory_core.stores import SemanticKnowledgeStore, TaskMemoryStore
from server.app.memory_kernel.proposals import create_memory_proposal
from server.app.models import (
    KnowledgeItem,
    KnowledgePage,
    MemoryDecision,
    ProvenanceEvent,
    SourceItem,
    TaskEvent,
    TaskSession,
    TaskState,
)
from server.app.retrieval.engine import RetrievalEngine


class FakeIndex:
    def __init__(self, knowledge_item_ids: list[str] | None = None) -> None:
        self.knowledge_item_ids = knowledge_item_ids or []

    def search_knowledge_item_ids(self, session: Session, query: str, limit: int) -> list[str]:
        return self.knowledge_item_ids[:limit]


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    init_knowledge_search_index(engine)
    with Session(engine) as active_session:
        yield active_session


def test_memory_ref_parses_and_formats_current_refs() -> None:
    ref = MemoryRef.parse("task-event:event-1")

    assert ref.kind == "task-event"
    assert ref.id == "event-1"
    assert str(ref) == "task-event:event-1"
    assert MemoryRef.parse_many(["source:source-1", "", "item:item-1", "store:semantic_knowledge"]) == [
        MemoryRef("source", "source-1"),
        MemoryRef("item", "item-1"),
        MemoryRef("store", "semantic_knowledge"),
    ]

    with pytest.raises(ValueError):
        MemoryRef.parse("missing-prefix")

    with pytest.raises(ValueError):
        MemoryRef("unknown", "value")


def test_semantic_store_returns_memory_slice_with_citation_and_evidence(session: Session) -> None:
    source_item = SourceItem(
        id="source-1",
        source="just_ctrl_v",
        external_id="source-1",
        kind="card_text",
        title="Memory Fabric source",
        content_text="Original evidence for the memory fabric.",
    )
    knowledge_item = KnowledgeItem(
        id="item-1",
        source_item_id=source_item.id,
        title="Memory Fabric",
        summary="Protocol first memory architecture",
        content="Memory Fabric keeps stores replaceable behind stable envelopes.",
        keywords=["fabric"],
        source="just_ctrl_v",
        source_ref="source-1",
        knowledge_type="fragment",
        status="active",
    )
    session.add(source_item)
    session.add(knowledge_item)
    session.commit()

    store = SemanticKnowledgeStore(retrieval_engine=RetrievalEngine(index=FakeIndex([knowledge_item.id])))
    slices = store.retrieve(session, MemoryQuery(text="fabric", limit=5))

    assert len(slices) == 1
    memory_slice = slices[0]
    assert memory_slice.store == "semantic_knowledge"
    assert memory_slice.kind == "knowledge_item"
    assert memory_slice.ref == MemoryRef("item", knowledge_item.id)
    assert memory_slice.citation_ref == f"item:{knowledge_item.id}"
    assert memory_slice.evidence_refs == [f"source:{source_item.id}"]
    assert memory_slice.metadata["sourceRef"] == "source-1"


def test_semantic_store_empty_query_returns_empty_slice_list(session: Session) -> None:
    store = SemanticKnowledgeStore(retrieval_engine=RetrievalEngine(index=FakeIndex()))

    assert store.retrieve(session, MemoryQuery(text="   ")) == []


def test_task_store_returns_state_and_recent_event_for_task_scope(session: Session) -> None:
    task = TaskSession(
        id="task-1",
        title="Build memory core",
        user_goal="Create the Step 1 protocol skeleton",
        status="open",
    )
    state = TaskState(
        task_session_id=task.id,
        current_goal="Wire memory stores",
        next_steps_json=["Run backend tests"],
        decisions_json=["Route context through memory_core"],
    )
    event = TaskEvent(
        id="event-1",
        task_session_id=task.id,
        type="agent_action",
        summary="Added MemoryRouter skeleton",
        payload_json={"file": "server/app/memory_core/router.py"},
    )
    session.add(task)
    session.add(state)
    session.add(event)
    session.commit()

    store = TaskMemoryStore()
    slices = store.retrieve(session, MemoryQuery(scope=f"task:{task.id}", limit=3))

    assert [str(item.ref) for item in slices] == [f"task:{task.id}", f"task-event:{event.id}"]
    assert slices[0].kind == "task_state"
    assert slices[0].visibility == "task"
    assert "Run backend tests" in slices[0].excerpt
    assert slices[1].metadata["eventType"] == "agent_action"


def test_memory_router_retrieves_registered_store_slices(session: Session) -> None:
    task = TaskSession(id="task-router", title="Router test", user_goal="Return task slice", status="open")
    state = TaskState(task_session_id=task.id, current_goal="Use registry")
    session.add(task)
    session.add(state)
    session.commit()

    router = MemoryRouter([TaskMemoryStore()])
    slices = router.retrieve(session, MemoryQuery(task_session_id=task.id))

    assert router.get_store("task_memory") is not None
    assert [str(item.ref) for item in slices] == [f"task:{task.id}"]


def test_memory_router_accepts_rule_preference_with_decision_and_provenance(session: Session) -> None:
    proposal = create_memory_proposal(
        session,
        proposal_type="project_rule",
        title="Keep exports inspectable",
        body="Exports must include decisions and provenance.",
        evidence_refs=["task:test-routing"],
        confidence=0.8,
    )

    accepted = MemoryRouter().accept_proposal(session, proposal)
    session.commit()

    assert accepted.status == "accepted"
    assert accepted.target_store == "rule_preference"
    assert accepted.knowledge_item_id
    assert accepted.decision_ref

    knowledge_item = session.get(KnowledgeItem, accepted.knowledge_item_id)
    assert knowledge_item
    assert knowledge_item.knowledge_type == "rule_preference"
    assert "rule_preference" in knowledge_item.keywords

    decisions = session.exec(select(MemoryDecision)).all()
    provenance_events = session.exec(select(ProvenanceEvent)).all()
    assert {decision.decision_type for decision in decisions} >= {
        "proposal_created",
        "proposal_routed",
        "proposal_accepted",
    }
    assert {event.event_type for event in provenance_events} >= {
        "proposal_created",
        "proposal_routed",
        "proposal_created_source",
        "accepted_proposal_created_item",
    }


def test_memory_router_accepts_procedure_lesson_as_typed_knowledge_item(session: Session) -> None:
    proposal = create_memory_proposal(
        session,
        proposal_type="workflow_pattern",
        title="Export verification workflow",
        body="When export changes, verify manifest, jsonl files, and provenance together.",
        evidence_refs=["task:test-procedure-routing"],
        confidence=0.7,
    )

    accepted = MemoryRouter().accept_proposal(session, proposal)
    session.commit()

    assert accepted.status == "accepted"
    assert accepted.target_store == "procedure_lesson"
    assert accepted.knowledge_item_id
    knowledge_item = session.get(KnowledgeItem, accepted.knowledge_item_id)
    assert knowledge_item
    assert knowledge_item.knowledge_type == "procedure_lesson"
    assert knowledge_item.keywords == ["workflow_pattern", "procedure_lesson"]


def test_memory_router_accepts_page_update_with_page_provenance(session: Session) -> None:
    proposal = create_memory_proposal(
        session,
        proposal_type="page_update",
        title="Memory Fabric Router",
        body="Router summary for the page.",
        structured_payload={"body": "Router body stored on the knowledge page."},
        evidence_refs=["item:test-page-evidence"],
        review_note="Create page from reviewed proposal",
    )

    accepted = MemoryRouter().accept_proposal(session, proposal)
    session.commit()

    assert accepted.status == "accepted"
    assert accepted.target_store == "semantic_knowledge"
    assert accepted.page_id
    assert accepted.knowledge_item_id is None
    assert accepted.source_item_id is None
    assert accepted.decision_ref
    page = session.get(KnowledgePage, accepted.page_id)
    assert page
    assert page.title == "Memory Fabric Router"
    assert page.summary == "Router summary for the page."
    assert page.body == "Router body stored on the knowledge page."
    provenance_events = session.exec(select(ProvenanceEvent).where(ProvenanceEvent.from_ref == f"proposal:{accepted.id}")).all()
    assert any(event.event_type == "accepted_proposal_created_page" for event in provenance_events)


def test_memory_router_rejects_unknown_target_store_without_write(session: Session) -> None:
    proposal = create_memory_proposal(
        session,
        proposal_type="lesson",
        title="Invalid target",
        body="This should not write long-term memory.",
        target_store="procedure_lesson",
    )
    proposal.target_store = "unknown_store"
    session.add(proposal)
    session.flush()

    with pytest.raises(ValueError):
        MemoryRouter().accept_proposal(session, proposal)

    assert proposal.status == "pending"
    assert proposal.knowledge_item_id is None
    assert proposal.source_item_id is None


def test_memory_router_rejects_already_accepted_proposal_without_duplicate_write(session: Session) -> None:
    proposal = create_memory_proposal(
        session,
        proposal_type="technical_decision",
        title="Single accept only",
        body="An accepted proposal cannot be accepted a second time.",
    )
    accepted = MemoryRouter().accept_proposal(session, proposal)
    session.commit()

    with pytest.raises(ValueError):
        MemoryRouter().accept_proposal(session, accepted)
