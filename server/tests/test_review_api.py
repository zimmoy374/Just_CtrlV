from __future__ import annotations

from fastapi.testclient import TestClient

from server.tests.support import app


def test_memory_proposal_pending_is_listed_but_not_searchable() -> None:
    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.memory_kernel.proposals import create_memory_proposal

    marker = "待审记忆候选不可检索标记"
    with Session(engine) as session:
        proposal = create_memory_proposal(
            session,
            proposal_type="lesson",
            title=f"{marker} 标题",
            body=f"{marker} 正文",
            evidence_refs=["test:pending-memory-proposal"],
        )
        session.commit()
        proposal_id = proposal.id

    with TestClient(app) as client:
        listed = client.get("/api/review/workbench", params={"proposalStatus": "pending"})
        assert listed.status_code == 200
        assert any(item["id"] == proposal_id and item["status"] == "pending" for item in listed.json()["proposals"])

        search = client.get("/api/knowledge/search", params={"q": marker})
        assert search.status_code == 200
        assert search.json() == []

def test_accept_memory_proposal_creates_searchable_active_knowledge_item() -> None:
    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.memory_kernel.proposals import create_memory_proposal
    from server.app.models import KnowledgeItem, MemoryDecision, ProvenanceEvent

    marker = "接受记忆候选可检索标记"
    with Session(engine) as session:
        proposal = create_memory_proposal(
            session,
            proposal_type="technical_decision",
            title=f"{marker} 标题",
            body=f"{marker} 正文",
            evidence_refs=["test:accepted-memory-proposal"],
        )
        session.commit()
        proposal_id = proposal.id

    with TestClient(app) as client:
        accepted = client.post(f"/api/review/proposals/{proposal_id}/accept")
        assert accepted.status_code == 200
        payload = accepted.json()
        assert payload["status"] == "accepted"
        assert payload["targetStore"] == "semantic_knowledge"
        assert payload["decisionRef"]
        assert payload["knowledgeItemId"]
        assert payload["sourceItemId"]

        search = client.get("/api/knowledge/search", params={"q": marker})
        assert search.status_code == 200
        results = search.json()
        assert any(result["knowledgeItem"]["id"] == payload["knowledgeItemId"] for result in results)

    with Session(engine) as session:
        knowledge_item = session.exec(select(KnowledgeItem).where(KnowledgeItem.id == payload["knowledgeItemId"])).one()
        decisions = session.exec(select(MemoryDecision).where(MemoryDecision.target_ref == f"proposal:{proposal_id}")).all()
        provenance_events = session.exec(select(ProvenanceEvent).where(ProvenanceEvent.from_ref == f"proposal:{proposal_id}")).all()
    assert knowledge_item.status == "active"
    assert knowledge_item.card_id is None
    assert {decision.decision_type for decision in decisions} >= {"proposal_created", "proposal_routed", "proposal_accepted"}
    assert any(event.event_type == "accepted_proposal_created_item" for event in provenance_events)

def test_dismiss_memory_proposal_is_not_searchable_or_exported(tmp_path) -> None:
    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.export.bundle import export_knowledge_bundle
    from server.app.memory_kernel.proposals import create_memory_proposal
    from server.app.models import KnowledgeItem, MemoryDecision, ProvenanceEvent, SourceItem

    marker = "忽略记忆候选不导出标记"
    with Session(engine) as session:
        proposal = create_memory_proposal(
            session,
            proposal_type="pitfall",
            title=f"{marker} 标题",
            body=f"{marker} 正文",
            evidence_refs=["test:dismissed-memory-proposal"],
        )
        session.commit()
        proposal_id = proposal.id

    with TestClient(app) as client:
        dismissed = client.post(f"/api/review/proposals/{proposal_id}/dismiss")
        assert dismissed.status_code == 200
        payload = dismissed.json()
        assert payload["status"] == "dismissed"
        assert payload["targetStore"] == "procedure_lesson"
        assert payload["decisionRef"]
        assert payload["knowledgeItemId"] is None
        assert payload["sourceItemId"] is None

        search = client.get("/api/knowledge/search", params={"q": marker})
        assert search.status_code == 200
        assert search.json() == []

    with Session(engine) as session:
        export_root = export_knowledge_bundle(session, tmp_path)
        source_items = session.exec(select(SourceItem).where(SourceItem.external_id == f"memory-proposal:{proposal_id}")).all()
        knowledge_items = session.exec(select(KnowledgeItem).where(KnowledgeItem.title.contains(marker))).all()
        decisions = session.exec(select(MemoryDecision).where(MemoryDecision.target_ref == f"proposal:{proposal_id}")).all()
        provenance_events = session.exec(select(ProvenanceEvent).where(ProvenanceEvent.from_ref == f"proposal:{proposal_id}")).all()

    item_text = (export_root / "items.jsonl").read_text(encoding="utf-8")
    assert marker not in item_text
    assert source_items == []
    assert knowledge_items == []
    assert any(decision.decision_type == "proposal_dismissed" for decision in decisions)
    assert any(event.event_type == "proposal_dismissed" for event in provenance_events)

def test_review_workbench_supports_user_review_actions_and_audit() -> None:
    from uuid import uuid4

    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.memory_core.router import MemoryRouter
    from server.app.memory_kernel.proposals import create_memory_proposal
    from server.app.models import MemoryConflict, MemoryFact, SourceItem

    marker = f"review-step7-{uuid4()}"
    source_id = f"source-{marker}"

    with Session(engine) as session:
        first = create_memory_proposal(
            session,
            proposal_type="profile_fact",
            title=f"{marker} first profile fact",
            body="The user prefers Review Editor A.",
            structured_payload={
                "subject": {"type": "user", "name": f"{marker} user"},
                "predicate": "prefers_editor",
                "objectValue": "Review Editor A",
            },
            evidence_refs=[f"source:{marker}-first"],
        )
        MemoryRouter().accept_proposal(session, first)
        second = create_memory_proposal(
            session,
            proposal_type="profile_fact",
            title=f"{marker} conflicting profile fact",
            body="The user prefers Review Editor B.",
            structured_payload={
                "subject": {"type": "user", "name": f"{marker} user"},
                "predicate": "prefers_editor",
                "objectValue": "Review Editor B",
            },
            evidence_refs=[f"source:{marker}-second"],
        )
        MemoryRouter().accept_proposal(session, second)
        session.add(
            SourceItem(
                id=source_id,
                source="external_ai",
                external_id=source_id,
                kind="external_ai_note",
                title=f"{marker} source",
                content_text="Sensitive source body should be policy controlled.",
                metadata_json={"visibility": "workspace", "privacyLabels": []},
            ),
        )
        session.commit()
        active_fact = session.exec(select(MemoryFact).where(MemoryFact.status == "active", MemoryFact.source_proposal_id == first.id)).one()
        conflicted_fact = session.exec(select(MemoryFact).where(MemoryFact.status == "conflicted", MemoryFact.source_proposal_id == second.id)).one()
        conflict = session.exec(select(MemoryConflict).where(MemoryConflict.status == "open")).all()[-1]
        active_fact_id = active_fact.id
        conflicted_fact_id = conflicted_fact.id
        conflict_id = conflict.id

    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={"title": f"{marker} review task", "userGoal": "create agent audit for review workbench"},
        ).json()["task"]
        assert client.get("/api/agent/tasks", params={"caller": "review-agent"}).status_code == 200

        proposal = client.post(
            "/api/agent/proposals",
            json={
                "caller": "review-agent",
                "taskSessionId": task["id"],
                "type": "lesson",
                "title": f"{marker} pending proposal",
                "body": "Review workbench should reroute this into a project rule.",
                "evidenceRefs": [f"task:{task['id']}"],
            },
        ).json()
        patched = client.patch(
            f"/api/review/proposals/{proposal['id']}",
            json={"type": "project_rule", "targetStore": "rule_preference", "reviewNote": "Rerouted by review workbench"},
        )
        assert patched.status_code == 200
        assert patched.json()["targetStore"] == "rule_preference"
        assert patched.json()["type"] == "project_rule"
        assert patched.json()["decisionRef"]

        accepted = client.post(f"/api/review/proposals/{proposal['id']}/accept")
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"

        supersede = client.post(
            f"/api/review/profile-facts/{active_fact_id}/supersede",
            json={
                "objectValue": "Review Editor C",
                "evidenceRefs": [f"source:{marker}-supersede"],
                "reviewNote": "User supplied an updated editor preference",
            },
        )
        assert supersede.status_code == 200
        assert supersede.json()["type"] == "fact_supersession"
        assert supersede.json()["status"] == "pending"

        resolved = client.post(
            f"/api/review/conflicts/{conflict_id}/resolve",
            json={"resolution": "Review chose the first fact for now.", "winningFactId": active_fact_id},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved"
        assert resolved.json()["decisionRef"]

        invalidated = client.post(
            f"/api/review/profile-facts/{active_fact_id}/invalidate",
            json={"reason": "User explicitly invalidated this fact after review."},
        )
        assert invalidated.status_code == 200
        assert invalidated.json()["status"] == "invalidated"

        policy = client.patch(
            f"/api/review/sources/{source_id}/policy",
            json={"visibility": "private", "privacyLabels": ["sensitive"]},
        )
        assert policy.status_code == 200
        assert policy.json()["visibility"] == "private"
        assert policy.json()["privacyLabels"] == ["sensitive"]

        purged = client.post(f"/api/review/sources/{source_id}/purge", json={"reason": "Remove sensitive source body"})
        assert purged.status_code == 200
        assert purged.json()["status"] == "purged"
        assert purged.json()["contentChars"] == 0

        workbench = client.get("/api/review/workbench", params={"proposalStatus": "all"})
        assert workbench.status_code == 200
        payload = workbench.json()
        assert any(item["id"] == proposal["id"] and item["status"] == "accepted" for item in payload["proposals"])
        assert any(item["id"] == active_fact_id and item["status"] == "invalidated" for item in payload["profileFacts"])
        assert any(item["id"] == conflict_id and item["status"] == "resolved" for item in payload["conflicts"])
        assert any(item["title"] == f"{marker} pending proposal" for item in payload["rules"])
        assert any(item["id"] == source_id and item["status"] == "purged" for item in payload["sources"])
        assert "agentAccesses" not in payload
        assert "taskCapsules" not in payload

    with Session(engine) as session:
        from server.app.models import ProvenanceEvent

        assert session.exec(select(ProvenanceEvent).where(ProvenanceEvent.actor == "review-agent")).all()
        conflicted = session.get(MemoryFact, conflicted_fact_id)
        assert conflicted
        assert conflicted.status == "invalidated"
