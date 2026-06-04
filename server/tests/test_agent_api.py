from __future__ import annotations

from fastapi.testclient import TestClient

from server.tests.support import app


def test_agent_source_excerpt_enforces_scope_privacy_and_budget_errors() -> None:
    from uuid import uuid4

    from sqlmodel import Session

    from server.app.database import engine
    from server.app.models import SourceItem

    private_source_id = f"agent-private-{uuid4()}"
    scoped_source_id = f"agent-task-source-{uuid4()}"
    marker = "agent-step6-private-needle"

    with TestClient(app) as client:
        task_a = client.post("/api/tasks", json={"title": "Agent source scope A", "userGoal": "scope A"}).json()["task"]
        task_b = client.post("/api/tasks", json={"title": "Agent source scope B", "userGoal": "scope B"}).json()["task"]

        with Session(engine) as session:
            session.add(
                SourceItem(
                    id=private_source_id,
                    source="external_ai",
                    external_id=private_source_id,
                    kind="external_ai_note",
                    title="Agent private source",
                    content_text=f"Private source before {marker}. " * 20,
                    metadata_json={"visibility": "private", "privacyLabels": ["private"]},
                ),
            )
            session.add(
                SourceItem(
                    id=scoped_source_id,
                    source="second_brain",
                    external_id=scoped_source_id,
                    kind="task_event",
                    title="Agent scoped source",
                    content_text="Task scoped source material",
                    metadata_json={"taskSessionId": task_a["id"]},
                ),
            )
            session.commit()

        denied = client.get(
            "/api/agent/source-excerpt",
            params={"ref": f"source:{private_source_id}", "caller": "agent-test", "q": marker},
        )
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == "permission_denied"

        allowed = client.get(
            "/api/agent/source-excerpt",
            params=[
                ("ref", f"source:{private_source_id}"),
                ("caller", "agent-test"),
                ("q", marker),
                ("capabilityProfile", "private"),
                ("capability", "private_memory"),
                ("maxChars", "80"),
            ],
        )
        assert allowed.status_code == 200
        assert allowed.json()["citationRef"] == f"source:{private_source_id}"
        assert allowed.json()["budget"]["truncated"] is True
        assert allowed.json()["warnings"][0]["type"] == "budget_exceeded"

        wrong_task = client.get(
            "/api/agent/source-excerpt",
            params={
                "ref": f"source:{scoped_source_id}",
                "caller": "agent-test",
                "taskSessionId": task_b["id"],
            },
        )
        assert wrong_task.status_code == 403
        assert wrong_task.json()["detail"]["code"] == "permission_denied"

        too_small = client.get(
            "/api/agent/source-excerpt",
            params={"ref": f"source:{private_source_id}", "caller": "agent-test", "maxChars": "20"},
        )
        assert too_small.status_code == 413
        assert too_small.json()["detail"]["code"] == "budget_exceeded"

        missing = client.get("/api/agent/source-excerpt", params={"ref": "source:missing-agent-source"})
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "missing_ref"

def test_agent_context_filters_profile_memory_without_capability() -> None:
    from uuid import uuid4

    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.memory_core.router import MemoryRouter
    from server.app.memory_kernel.proposals import create_memory_proposal
    from server.app.models import MemoryFact

    marker = f"agent-step6-editor-{uuid4()}"

    with Session(engine) as session:
        proposal = create_memory_proposal(
            session,
            proposal_type="profile_fact",
            title="Agent profile preference",
            body=f"The user prefers {marker}.",
            structured_payload={
                "subject": {"type": "user", "name": f"Agent Step6 User {marker}"},
                "predicate": "prefers_editor",
                "objectValue": marker,
            },
            evidence_refs=[f"source:{marker}"],
        )
        MemoryRouter().accept_proposal(session, proposal)
        session.commit()
        fact_id = session.exec(select(MemoryFact).where(MemoryFact.source_proposal_id == proposal.id)).one().id

    with TestClient(app) as client:
        hidden = client.get("/api/agent/context", params={"q": marker, "caller": "agent-test"})
        assert hidden.status_code == 200
        assert hidden.json()["profileFacts"] == []
        assert any(warning["type"] == "filtered_private" for warning in hidden.json()["warnings"])
        assert hidden.json()["selectionTrace"]
        assert marker not in str(hidden.json()["selectionTrace"])

        allowed = client.get(
            "/api/agent/context",
            params=[("q", marker), ("caller", "agent-test"), ("capabilityProfile", "profile"), ("capability", "profile_memory")],
        )
        assert allowed.status_code == 200
        assert allowed.json()["profileFacts"][0]["ref"] == f"fact:{fact_id}"
        assert any(item["status"] == "selected" and item["ref"] == f"fact:{fact_id}" for item in allowed.json()["selectionTrace"])

        too_small = client.get("/api/agent/context", params={"q": marker, "caller": "agent-test", "maxChars": "100"})
        assert too_small.status_code == 413
        assert too_small.json()["detail"]["code"] == "budget_exceeded"

def test_agent_tools_preserve_review_gate_and_stale_task_boundaries() -> None:
    from datetime import timedelta

    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.models import KnowledgeItem, TaskSession, utc_now

    marker = "agent-step6-pending-proposal-only"

    with TestClient(app) as client:
        instructions = client.get("/api/agent/instructions").json()
        assert instructions["toolsEndpoint"] == "/api/agent/tools"
        assert instructions["runtimePolicy"]["defaultMode"] == "balanced"
        assert "quiet" in instructions["runtimePolicy"]["modes"]
        assert any("不要在每次 record_progress" in rule for rule in instructions["runtimePolicy"]["rules"])
        assert any("/api/agent/context" in item["call"] for item in instructions["workflow"])
        assert any("不能直接写入长期记忆" in rule for rule in instructions["operatingRules"])
        assert client.get("/api/agent").json()["toolsEndpoint"] == "/api/agent/tools"

        capabilities = client.get("/api/agent/capabilities")
        assert capabilities.status_code == 200
        assert capabilities.json()["defaultProfile"] == "work"
        assert "private" in capabilities.json()["profiles"]

        tools = client.get("/api/agent/tools").json()
        tool_names = {tool["name"] for tool in tools}
        assert tool_names == {
            "list_capability_profiles",
            "get_context_pack",
            "get_source_excerpt",
            "list_active_tasks",
            "record_task_event",
            "update_task_state",
            "create_checkpoint",
            "get_handoff_pack",
            "propose_memory",
            "list_memory_proposals",
        }
        assert "accept_memory_proposal" not in tool_names
        assert all(tool["directLongTermWrite"] is False for tool in tools)
        tools_by_name = {tool["name"]: tool for tool in tools}
        assert any("工作状态事件" in item for item in tools_by_name["record_task_event"]["restrictions"])
        assert any("task state" in item for item in tools_by_name["update_task_state"]["restrictions"])
        assert any("pending 待审记忆" in item for item in tools_by_name["propose_memory"]["restrictions"])
        assert any("不替代全量历史读取" in item for item in tools_by_name["get_handoff_pack"]["restrictions"])

        system_status = client.get("/api/system/status")
        assert system_status.status_code == 200
        assert system_status.json()["storage"]["dataDirExists"] is True
        assert "tasks" in system_status.json()

        created = client.post(
            "/api/tasks",
            json={"title": "Agent Step6 task tools", "userGoal": "Verify agent protocol tools"},
        ).json()
        task_id = created["task"]["id"]

        event = client.post(
            f"/api/agent/tasks/{task_id}/events",
            json={"caller": "agent-test", "type": "agent_action", "summary": "Agent recorded a bounded event"},
        )
        assert event.status_code == 200
        assert event.json()["payload"]["caller"] == "agent-test"

        state = client.patch(
            f"/api/agent/tasks/{task_id}/state",
            params={"caller": "agent-test"},
            json={"currentGoal": "Use stable agent protocol", "nextSteps": ["Check handoff freshness"]},
        )
        assert state.status_code == 200
        assert state.json()["currentGoal"] == "Use stable agent protocol"

        checkpoint = client.post(
            f"/api/agent/tasks/{task_id}/checkpoints",
            json={"caller": "agent-test", "title": "Agent checkpoint", "summary": "Checkpoint through agent protocol"},
        )
        assert checkpoint.status_code == 200

        with Session(engine) as session:
            task = session.get(TaskSession, task_id)
            assert task
            stale_at = utc_now() - timedelta(days=2)
            task.updated_at = stale_at
            task.last_event_at = stale_at
            session.add(task)
            session.commit()

        handoff = client.get(f"/api/agent/tasks/{task_id}/handoff", params={"caller": "agent-test", "format": "json"})
        assert handoff.status_code == 200
        assert handoff.json()["pack"]["freshness"]["state"] == "stale"
        assert handoff.json()["pack"]["nextRecommendedActions"][0]["label"] == "confirm_current_state"
        assert handoff.json()["warnings"][0]["type"] == "stale_task"

        proposal = client.post(
            "/api/agent/proposals",
            json={
                "caller": "agent-test",
                "taskSessionId": task_id,
                "type": "technical_decision",
                "title": marker,
                "body": "This should remain pending until the review gate accepts it.",
                "evidenceRefs": [f"task:{task_id}"],
            },
        )
        assert proposal.status_code == 200
        proposal_payload = proposal.json()
        assert proposal_payload["status"] == "pending"
        assert proposal_payload["knowledgeItemId"] is None
        assert proposal_payload["sourceItemId"] is None

        assert client.post(f"/api/agent/proposals/{proposal_payload['id']}/accept").status_code == 404
        listed = client.get("/api/agent/proposals", params={"caller": "agent-test"}).json()
        assert any(item["id"] == proposal_payload["id"] for item in listed)

        assert client.post(f"/api/tasks/{task_id}/close").status_code == 200
        stale_write = client.post(
            f"/api/agent/tasks/{task_id}/events",
            json={"caller": "agent-test", "type": "agent_action", "summary": "Should be rejected"},
        )
        assert stale_write.status_code == 409
        assert stale_write.json()["detail"]["code"] == "stale_task"

    with Session(engine) as session:
        assert not session.exec(select(KnowledgeItem).where(KnowledgeItem.title == marker)).all()
