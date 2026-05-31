from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine, select

from second_brain import resolve_task
from server.app.indexing.sqlite_fts import init_knowledge_search_index
from server.app.memory_core.composer import MemoryContextComposer
from server.app.memory_core.protocol import MemoryQuery, MemoryRef, MemorySlice
from server.app.memory_core.router import MemoryRouter
from server.app.memory_core.stores import ProfileTemporalGraphStore, SemanticKnowledgeStore, TaskMemoryStore
from server.app.memory_kernel.proposals import create_memory_proposal
from server.app.models import (
    Entity,
    KnowledgeItem,
    KnowledgePage,
    MemoryConflict,
    MemoryDecision,
    MemoryFact,
    MemoryRelation,
    ProvenanceEvent,
    SourceItem,
    TaskDigest,
    TaskEvent,
    TaskSession,
    TaskState,
)
from server.app.agent_runtime.capabilities import resolve_capabilities
from server.app.agent_runtime.installers import install_agent_target
from server.app.agent_runtime.workspace import read_workspace_state, write_workspace_state
from server.app.tasks.events import append_task_event
from server.app.tasks.handoff import preview_handoff_pack
from server.app.tasks.sessions import create_task_session
from server.app.tasks.state_machine import transition_task_session
from server.app.retrieval.engine import RetrievalEngine


class FakeIndex:
    def __init__(self, knowledge_item_ids: list[str] | None = None) -> None:
        self.knowledge_item_ids = knowledge_item_ids or []

    def search_knowledge_item_ids(self, session: Session, query: str, limit: int) -> list[str]:
        return self.knowledge_item_ids[:limit]


class StaticStore:
    name = "static"

    def __init__(self, slices: list[MemorySlice]) -> None:
        self.slices = slices

    def retrieve(self, session: Session, query: MemoryQuery) -> list[MemorySlice]:
        return self.slices[: query.limit]

    def get(self, session: Session, ref: MemoryRef):
        return None

    def export(self, session: Session):
        return []

    def rebuild_projection(self, session: Session):
        return {"store": self.name, "status": "noop"}


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


def test_task_handoff_uses_digest_for_older_events(session: Session) -> None:
    task = create_task_session(session, title="跨 agent 接力", user_goal="验证滚动摘要", active_agent="codex")
    for index in range(8):
        append_task_event(
            session,
            task,
            event_type="agent_action",
            summary=f"完成阶段 {index}",
            source_ref=f"server/file_{index}.py",
        )

    pack, content, budget = preview_handoff_pack(session, task, handoff_format="json")

    assert pack["taskDigest"]["eventCount"] == 4
    assert "完成阶段 0" in pack["taskDigest"]["summary"]
    assert len(pack["sourceRefs"]) == 5
    assert budget["digestEventCount"] == 4
    assert session.get(TaskDigest, task.id) is not None
    assert "taskDigest" in content


def test_workspace_binding_is_local_to_workspace(session: Session, tmp_path) -> None:
    task = create_task_session(session, title="本地工作区", user_goal="绑定活跃任务")
    workspace = tmp_path / "project-a"
    state = write_workspace_state(workspace, task=task, agent="codex")

    loaded = read_workspace_state(workspace)

    assert state["activeTaskId"] == task.id
    assert loaded["activeTaskId"] == task.id
    assert loaded["workspaceRoot"] == str(workspace.resolve())


def test_resolve_task_requires_workspace_binding(session: Session, tmp_path) -> None:
    task = create_task_session(session, title="全局任务", user_goal="不应被其他项目偷拿")

    assert resolve_task(session, workspace_root=tmp_path / "unbound") is None

    write_workspace_state(tmp_path / "bound", task=task, agent="codex")
    assert resolve_task(session, workspace_root=tmp_path / "bound").id == task.id


def test_task_state_machine_rejects_invalid_terminal_transition(session: Session) -> None:
    task = create_task_session(session, title="状态机验收", user_goal="终态不能被继续写")

    transition_task_session(session, task, "closed", reason="测试关闭")

    assert task.status == "closed"
    with pytest.raises(ValueError):
        transition_task_session(session, task, "open")
    event_types = [event.type for event in session.exec(select(TaskEvent)).all()]
    assert event_types.count("task_status_changed") == 1


def test_capability_profile_limits_requested_capabilities() -> None:
    assert resolve_capabilities("work", ["private_memory", "profile_memory"]) == []
    assert resolve_capabilities("profile") == ["profile_memory"]
    assert resolve_capabilities("trusted", ["private_memory", "not-real"]) == ["private_memory"]

    with pytest.raises(ValueError):
        resolve_capabilities("unknown")


def test_install_agent_updates_marked_blocks_without_overwriting_user_text(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("# 用户规则\n\n保留这一行。\n", encoding="utf-8")

    result = install_agent_target(tmp_path, "all")
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    claude_text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")

    assert result["ok"] is True
    assert "保留这一行。" in agents_text
    assert "<!-- second-brain:start -->" in agents_text
    assert "python second_brain.py resume" in claude_text
    assert (tmp_path / ".second-brain" / "opencli.second-brain.json").exists()

    with pytest.raises(ValueError):
        MemoryRef("unknown", "value")


def test_context_pack_includes_task_digest_projection(session: Session) -> None:
    task = create_task_session(session, title="压缩上下文", user_goal="让 ContextPack 带上较早事件摘要")
    for index in range(8):
        append_task_event(session, task, event_type="agent_action", summary=f"较早事件 {index}")
    preview_handoff_pack(session, task, handoff_format="markdown")

    pack = MemoryContextComposer(MemoryRouter([TaskMemoryStore()])).build_context_pack(
        session,
        query="较早事件",
        task_session_id=task.id,
        max_chars=5000,
        max_task_slices=4,
    )

    assert pack["taskState"]["metadata"]["taskDigest"]["metadata"]["eventCount"] == 4
    assert "较早事件 0" in pack["taskState"]["metadata"]["taskDigest"]["summary"]


def test_semantic_store_returns_memory_slice_with_citation_and_evidence(session: Session) -> None:
    source_item = SourceItem(
        id="source-1",
        source="second_brain",
        external_id="source-1",
        kind="card_text",
        title="second brain source",
        content_text="Original evidence for the second brain.",
    )
    knowledge_item = KnowledgeItem(
        id="item-1",
        source_item_id=source_item.id,
        title="second brain",
        summary="Protocol first memory architecture",
        content="second brain keeps stores replaceable behind stable envelopes.",
        keywords=["fabric"],
        source="second_brain",
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
        title="second brain Router",
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
    assert page.title == "second brain Router"
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


def test_context_composer_prioritizes_task_state_for_task_scope(session: Session) -> None:
    task = TaskSession(id="task-context", title="Context Composer", user_goal="Build Step 3", status="open")
    other_task = TaskSession(id="task-other", title="Other Task", user_goal="Must not leak", status="open")
    state = TaskState(
        task_session_id=task.id,
        current_goal="Compose task scoped memory first",
        next_steps_json=["Add rules after task state"],
    )
    event = TaskEvent(
        id="event-context",
        task_session_id=task.id,
        type="agent_action",
        summary="Implemented task-scoped context composition",
    )
    other_state = TaskState(task_session_id=other_task.id, current_goal="Unrelated task state")
    session.add(task)
    session.add(other_task)
    session.add(state)
    session.add(event)
    session.add(other_state)
    session.commit()

    composer = MemoryContextComposer(router=MemoryRouter([TaskMemoryStore()]))
    pack = composer.build_context_pack(session, query="", task_session_id=task.id)

    assert pack["taskState"]["ref"] == f"task:{task.id}"
    assert pack["taskState"]["recentEvents"][0]["ref"] == f"task-event:{event.id}"
    assert "Unrelated task state" not in str(pack)
    assert any(ref["ref"] == f"task:{task.id}" for ref in pack["citationRefs"])


def test_context_composer_groups_rules_procedures_and_decision_refs(session: Session) -> None:
    rule = create_memory_proposal(
        session,
        proposal_type="project_rule",
        title="Keep exports inspectable",
        body="For export work, keep manifest, jsonl files, and provenance inspectable.",
        evidence_refs=["task:composer-rules"],
        confidence=0.9,
    )
    lesson = create_memory_proposal(
        session,
        proposal_type="workflow_pattern",
        title="Export verification workflow",
        body="For export work, verify manifest, jsonl files, and provenance together.",
        evidence_refs=["task:composer-lessons"],
        confidence=0.8,
    )
    accepted_rule = MemoryRouter().accept_proposal(session, rule)
    accepted_lesson = MemoryRouter().accept_proposal(session, lesson)
    session.commit()

    assert accepted_rule.knowledge_item_id
    assert accepted_lesson.knowledge_item_id
    router = MemoryRouter(
        [
            SemanticKnowledgeStore(
                retrieval_engine=RetrievalEngine(index=FakeIndex([accepted_rule.knowledge_item_id, accepted_lesson.knowledge_item_id])),
            ),
        ],
    )
    pack = MemoryContextComposer(router=router).build_context_pack(session, query="export", max_items=3)

    assert [item["id"] for item in pack["rules"]] == [accepted_rule.knowledge_item_id]
    assert [item["id"] for item in pack["procedureLessons"]] == [accepted_lesson.knowledge_item_id]
    assert pack["relatedItems"] == []
    assert any(ref["ref"] == accepted_rule.decision_ref for ref in pack["decisionRefs"])
    assert any(ref["ref"] == accepted_lesson.decision_ref for ref in pack["decisionRefs"])
    assert pack["rules"][0]["evidenceRefs"]
    assert pack["procedureLessons"][0]["citationRef"] == f"item:{accepted_lesson.knowledge_item_id}"


def test_context_composer_filters_scope_privacy_capability_and_surfaces_conflicts(session: Session) -> None:
    visible = MemorySlice(
        store="static",
        kind="knowledge_item",
        ref=MemoryRef("item", "visible"),
        title="Visible memory",
        summary="Visible scoped memory",
        excerpt="Visible scoped memory",
        score=50,
        citation_ref="item:visible",
    )
    private = MemorySlice(
        store="static",
        kind="knowledge_item",
        ref=MemoryRef("item", "private"),
        title="Private memory",
        summary="Private memory",
        excerpt="Private memory",
        score=49,
        citation_ref="item:private",
        visibility="private",
    )
    other_task = MemorySlice(
        store="static",
        kind="knowledge_item",
        ref=MemoryRef("item", "other-task"),
        title="Other task memory",
        summary="Other task memory",
        excerpt="Other task memory",
        score=48,
        scope="task:other",
        visibility="task",
        citation_ref="item:other-task",
    )
    requires_capability = MemorySlice(
        store="static",
        kind="knowledge_item",
        ref=MemoryRef("item", "capability"),
        title="Capability memory",
        summary="Capability memory",
        excerpt="Capability memory",
        score=47,
        citation_ref="item:capability",
        metadata={"capabilityRequirements": ["external_agent_allowed"]},
    )
    conflict = MemorySlice(
        store="static",
        kind="knowledge_item",
        ref=MemoryRef("item", "conflict"),
        title="Conflict memory",
        summary="Conflict memory",
        excerpt="Conflict memory",
        score=46,
        citation_ref="item:conflict",
        conflict_refs=["conflict:active-1"],
    )

    composer = MemoryContextComposer(router=MemoryRouter([StaticStore([visible, private, other_task, requires_capability, conflict])]))
    pack = composer.build_context_pack(session, query="memory", task_session_id="current", max_items=10)

    assert [item["id"] for item in pack["relatedItems"]] == ["visible", "conflict"]
    warning_types = {warning["type"] for warning in pack["warnings"]}
    assert warning_types >= {"filtered_private", "filtered_scope", "insufficient_capability", "conflict"}
    assert all(ref["ref"] in {"item:visible", "item:conflict"} for ref in pack["citationRefs"])


def test_memory_router_accepts_profile_fact_and_context_retrieves_with_profile_capability(session: Session) -> None:
    proposal = create_memory_proposal(
        session,
        proposal_type="profile_fact",
        title="User preferred editor",
        body="The user prefers VS Code for this workspace.",
        structured_payload={
            "subject": {"type": "user", "name": "User"},
            "predicate": "prefers_editor",
            "objectValue": "VS Code",
        },
        evidence_refs=["source:profile-editor"],
        confidence=0.85,
    )

    accepted = MemoryRouter().accept_proposal(session, proposal)
    session.commit()

    assert accepted.status == "accepted"
    assert accepted.target_store == "profile_temporal_graph"
    fact = session.exec(select(MemoryFact)).one()
    assert fact.status == "active"
    assert fact.evidence_refs == ["source:profile-editor"]
    assert fact.decision_ref == accepted.decision_ref

    store_slices = ProfileTemporalGraphStore().retrieve(session, MemoryQuery(text="editor", limit=5))
    assert [item.kind for item in store_slices] == ["profile_fact"]
    assert store_slices[0].citation_ref == f"fact:{fact.id}"

    composer = MemoryContextComposer(router=MemoryRouter([ProfileTemporalGraphStore()]))
    hidden_pack = composer.build_context_pack(session, query="editor")
    allowed_pack = composer.build_context_pack(session, query="editor", capabilities=["profile_memory"])

    assert hidden_pack["profileFacts"] == []
    assert any(warning["type"] == "filtered_private" for warning in hidden_pack["warnings"])
    assert allowed_pack["profileFacts"][0]["ref"] == f"fact:{fact.id}"
    assert any(ref["ref"] == accepted.decision_ref for ref in allowed_pack["decisionRefs"])


def test_profile_fact_without_evidence_is_rejected_without_active_fact(session: Session) -> None:
    proposal = create_memory_proposal(
        session,
        proposal_type="profile_fact",
        title="Unsupported profile fact",
        body="This should not become active without evidence.",
        structured_payload={
            "subjectName": "User",
            "subjectType": "user",
            "predicate": "prefers_theme",
            "objectValue": "Dark",
        },
    )

    with pytest.raises(ValueError):
        MemoryRouter().accept_proposal(session, proposal)

    assert session.exec(select(MemoryFact)).all() == []
    assert not session.exec(select(MemoryDecision).where(MemoryDecision.decision_type == "proposal_routed")).all()
    assert not session.exec(select(ProvenanceEvent).where(ProvenanceEvent.event_type == "proposal_routed")).all()
    assert proposal.status == "pending"


def test_profile_fact_supersession_and_conflict_lifecycle(session: Session) -> None:
    first = create_memory_proposal(
        session,
        proposal_type="profile_fact",
        title="Initial editor preference",
        body="The user prefers VS Code.",
        structured_payload={
            "subject": {"type": "user", "name": "User"},
            "predicate": "prefers_editor",
            "objectValue": "VS Code",
        },
        evidence_refs=["source:first-editor"],
    )
    MemoryRouter().accept_proposal(session, first)
    session.commit()
    first_fact = session.exec(select(MemoryFact)).one()

    supersession = create_memory_proposal(
        session,
        proposal_type="fact_supersession",
        title="Updated editor preference",
        body="The user now prefers Cursor.",
        structured_payload={
            "supersedesFactRef": f"fact:{first_fact.id}",
            "newFact": {
                "subject": {"type": "user", "name": "User"},
                "predicate": "prefers_editor",
                "objectValue": "Cursor",
            },
        },
        evidence_refs=["source:updated-editor"],
    )
    MemoryRouter().accept_proposal(session, supersession)
    session.commit()

    session.refresh(first_fact)
    active_fact = session.exec(select(MemoryFact).where(MemoryFact.status == "active")).one()
    assert first_fact.status == "superseded"
    assert first_fact.invalid_at is not None
    assert first_fact.superseded_by == active_fact.id
    assert active_fact.object_value == "Cursor"
    assert any(decision.decision_type == "fact_superseded" for decision in session.exec(select(MemoryDecision)).all())

    conflict_proposal = create_memory_proposal(
        session,
        proposal_type="profile_fact",
        title="Conflicting editor preference",
        body="Another agent observed that the user prefers Zed.",
        structured_payload={
            "subject": {"type": "user", "name": "User"},
            "predicate": "prefers_editor",
            "objectValue": "Zed",
        },
        evidence_refs=["source:conflicting-editor"],
    )
    MemoryRouter().accept_proposal(session, conflict_proposal)
    session.commit()

    conflict = session.exec(select(MemoryConflict)).one()
    conflicted_fact = session.exec(select(MemoryFact).where(MemoryFact.status == "conflicted")).one()
    assert conflict.status == "open"
    assert set(conflict.fact_ids) == {active_fact.id, conflicted_fact.id}

    pack = MemoryContextComposer(router=MemoryRouter([ProfileTemporalGraphStore()])).build_context_pack(
        session,
        query="editor",
        capabilities=["profile_memory"],
    )
    assert [item["ref"] for item in pack["profileFacts"]] == [f"fact:{active_fact.id}"]
    assert pack["profileFacts"][0]["conflictRefs"] == [f"conflict:{conflict.id}"]
    assert any(warning["type"] == "conflict" for warning in pack["warnings"])

    conflict_object_pack = MemoryContextComposer(router=MemoryRouter([ProfileTemporalGraphStore()])).build_context_pack(
        session,
        query="Zed",
        capabilities=["profile_memory"],
    )
    assert conflict_object_pack["profileFacts"][0]["ref"] == f"fact:{active_fact.id}"
    assert conflict_object_pack["profileFacts"][0]["conflictRefs"] == [f"conflict:{conflict.id}"]


def test_profile_graph_relation_and_export_files(session: Session, tmp_path) -> None:
    import json

    from server.app.export.bundle import export_knowledge_bundle

    relation_proposal = create_memory_proposal(
        session,
        proposal_type="entity_relation",
        title="User works on second brain",
        body="The user is working on the second brain project.",
        structured_payload={
            "from": {"type": "user", "name": "User"},
            "relationType": "works_on",
            "to": {"type": "project", "name": "second brain"},
        },
        evidence_refs=["task:profile-relation"],
    )
    MemoryRouter().accept_proposal(session, relation_proposal)
    fact_proposal = create_memory_proposal(
        session,
        proposal_type="profile_fact",
        title="User likes second brain",
        body="The user likes second brain work.",
        structured_payload={
            "subject": {"type": "user", "name": "User"},
            "predicate": "likes",
            "objectValue": "second brain",
        },
        evidence_refs=["source:profile-export"],
    )
    MemoryRouter().accept_proposal(session, fact_proposal)
    session.commit()

    assert session.exec(select(Entity)).all()
    assert session.exec(select(MemoryRelation)).one().decision_ref

    export_root = export_knowledge_bundle(session, tmp_path)
    manifest = json.loads((export_root / "manifest.json").read_text(encoding="utf-8"))
    facts = [json.loads(line) for line in (export_root / "facts.jsonl").read_text(encoding="utf-8").splitlines()]
    relations = [json.loads(line) for line in (export_root / "relations.jsonl").read_text(encoding="utf-8").splitlines()]
    conflicts_text = (export_root / "conflicts.jsonl").read_text(encoding="utf-8")

    assert manifest["contents"]["entities"] == "entities.jsonl"
    assert manifest["contents"]["facts"] == "facts.jsonl"
    assert manifest["contents"]["relations"] == "relations.jsonl"
    assert manifest["contents"]["conflicts"] == "conflicts.jsonl"
    assert manifest["counts"]["facts"] == 1
    assert facts[0]["evidenceRefs"] == ["source:profile-export"]
    assert relations[0]["relationType"] == "works_on"
    assert conflicts_text == ""


def test_export_boundary_includes_store_views_and_hash_chained_provenance(session: Session, tmp_path) -> None:
    import json

    from server.app.export.bundle import export_knowledge_bundle

    rule = create_memory_proposal(
        session,
        proposal_type="project_rule",
        title="Export boundary rule",
        body="Derived projections are rebuilt, not exported as durable memory.",
        evidence_refs=["task:export-boundary"],
    )
    procedure = create_memory_proposal(
        session,
        proposal_type="workflow_pattern",
        title="Projection rebuild procedure",
        body="Drop the FTS projection and rebuild it from active KnowledgeItem records.",
        evidence_refs=["task:export-boundary"],
    )
    accepted_rule = MemoryRouter().accept_proposal(session, rule)
    accepted_procedure = MemoryRouter().accept_proposal(session, procedure)
    session.commit()

    export_root = export_knowledge_bundle(session, tmp_path)
    manifest = json.loads((export_root / "manifest.json").read_text(encoding="utf-8"))
    rules = [json.loads(line) for line in (export_root / "rules.jsonl").read_text(encoding="utf-8").splitlines()]
    procedures = [json.loads(line) for line in (export_root / "procedures.jsonl").read_text(encoding="utf-8").splitlines()]
    items = [json.loads(line) for line in (export_root / "items.jsonl").read_text(encoding="utf-8").splitlines()]
    provenance = [json.loads(line) for line in (export_root / "provenance.jsonl").read_text(encoding="utf-8").splitlines()]

    assert manifest["contents"]["pages"] == "pages.jsonl"
    assert manifest["contents"]["pageItemLinks"] == "page_item_links.jsonl"
    assert manifest["contents"]["rules"] == "rules.jsonl"
    assert manifest["contents"]["procedures"] == "procedures.jsonl"
    assert any(item["name"] == "rule_preference" and item["physicalStore"] == "knowledge_items" for item in manifest["durableStores"])
    assert any(item["name"] == "knowledge_search_fts" and item["exported"] is False for item in manifest["derivedProjections"])
    assert rules[0]["id"] == accepted_rule.knowledge_item_id
    assert rules[0]["targetStore"] == "rule_preference"
    assert rules[0]["decisionRef"] == accepted_rule.decision_ref
    assert procedures[0]["id"] == accepted_procedure.knowledge_item_id
    assert any(item["id"] == accepted_rule.knowledge_item_id and item["evidenceRefs"] for item in items)
    assert provenance
    assert provenance[0]["previousHash"] is None
    assert provenance[0]["hash"]
    if len(provenance) > 1:
        assert provenance[1]["previousHash"] == provenance[0]["hash"]


def test_memory_router_rebuilds_deleted_fts_projection(session: Session) -> None:
    source_item = SourceItem(
        id="source-rebuild",
        source="second_brain",
        external_id="source-rebuild",
        kind="card_text",
        title="Projection rebuild source",
        content_text="projection rebuild evidence",
    )
    knowledge_item = KnowledgeItem(
        id="item-rebuild",
        source_item_id=source_item.id,
        title="Projection Rebuild",
        summary="FTS projection can be rebuilt from durable items.",
        content="unique-rebuild-token survives projection rebuild",
        keywords=["projection-rebuild"],
        source="second_brain",
        source_ref="source-rebuild",
        knowledge_type="fragment",
        status="active",
    )
    session.add(source_item)
    session.add(knowledge_item)
    session.commit()

    session.connection().execute(text("DROP TABLE IF EXISTS knowledge_search_fts"))
    session.flush()

    reports = MemoryRouter([SemanticKnowledgeStore()]).rebuild_projections(session)
    session.commit()

    rows = session.connection().execute(text("SELECT knowledge_item_id FROM knowledge_search_fts")).all()
    results = RetrievalEngine().search(session, "unique-rebuild-token", limit=5)
    assert reports[0]["projection"] == "knowledge_search_fts"
    assert reports[0]["status"] == "rebuilt"
    assert "item-rebuild" in {str(row[0]) for row in rows}
    assert [result.knowledge_item.id for result in results] == ["item-rebuild"]
