from __future__ import annotations

from fastapi.testclient import TestClient

from server.tests.support import app


def test_export_bundle_contains_wiki_items_sources_and_provenance(monkeypatch, tmp_path) -> None:
    import json

    from sqlmodel import Session, select

    from server.app import ai
    from server.app.database import engine
    from server.app.export.bundle import export_knowledge_bundle
    from server.app.models import KnowledgePage

    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai.settings, "openai_model", "test-model")
    monkeypatch.setattr(
        ai,
        "_analyze_with_provider",
        lambda card: {"summary": f"导出主题证据 {card.text_content}", "keywords": ["导出主题"]},
    )

    with TestClient(app) as client:
        for index in range(5):
            client.post(
                "/api/cards/text",
                json={"weekKey": "2026-W45", "textContent": f"导出主题原始材料 {index}", "x": 10, "y": 20},
            )
        reflection = next(item for item in client.get("/api/reflections").json() if "导出主题" in item["title"])
        client.post(f"/api/reflections/{reflection['id']}/accept")

    with Session(engine) as session:
        export_root = export_knowledge_bundle(session, tmp_path)
        target_page = session.exec(select(KnowledgePage).where(KnowledgePage.title == "导出主题")).one()

    assert (export_root / "manifest.json").exists()
    assert (export_root / "index.md").exists()
    assert (export_root / "items.jsonl").exists()
    assert (export_root / "provenance.jsonl").exists()
    assert (export_root / "wiki").is_dir()
    assert (export_root / "sources").is_dir()

    manifest = json.loads((export_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contents"]["wiki"] == "wiki/"
    assert manifest["counts"]["knowledgePages"] >= 1
    assert manifest["counts"]["knowledgeItems"] >= 5
    assert manifest["counts"]["sourceItems"] >= 5

    wiki_files = list((export_root / "wiki").glob("*.md"))
    wiki_text = next(path.read_text(encoding="utf-8") for path in wiki_files if target_page.id in path.read_text(encoding="utf-8"))
    assert wiki_text.startswith("---\n")
    assert f'id: "{target_page.id}"' in wiki_text
    assert f'title: "{target_page.title}"' in wiki_text
    assert "status:" in wiki_text
    assert "updatedAt:" in wiki_text
    assert "sourceRefs:" in wiki_text
    assert "itemRefs:" in wiki_text
    assert f"# {target_page.title}" in wiki_text
    assert "## Related Knowledge Items" in wiki_text
    assert "`item:" in wiki_text
    assert "`source:" in wiki_text

    item_lines = [json.loads(line) for line in (export_root / "items.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(item["summary"].startswith("导出主题证据") for item in item_lines)

    provenance_lines = [
        json.loads(line) for line in (export_root / "provenance.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(line["type"] == "derived_from" for line in provenance_lines)
    assert any(line["type"] == "included_in_page" and line["to"] == f"page:{target_page.id}" for line in provenance_lines)

    source_dirs = [path for path in (export_root / "sources").iterdir() if path.is_dir()]
    assert source_dirs
    assert any((path / "metadata.json").exists() and (path / "content.txt").exists() for path in source_dirs)

def test_export_bundle_contains_task_capsule_files(tmp_path) -> None:
    import json

    from sqlmodel import Session

    from server.app.database import engine
    from server.app.export.bundle import export_knowledge_bundle

    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={"title": "Export task files", "userGoal": "导出新增任务文件"},
        ).json()["task"]
        client.post(
            f"/api/tasks/{task['id']}/events",
            json={"type": "agent_action", "summary": "写入导出事件"},
        )
        client.post(
            f"/api/tasks/{task['id']}/checkpoints",
            json={"title": "导出检查点", "summary": "checkpoint 应进入 jsonl"},
        )
        client.post(f"/api/tasks/{task['id']}/handoff", params={"format": "markdown"})
        client.post(f"/api/tasks/{task['id']}/close")

    with Session(engine) as session:
        export_root = export_knowledge_bundle(session, tmp_path)

    assert (export_root / "task_sessions.jsonl").exists()
    assert (export_root / "task_events.jsonl").exists()
    assert (export_root / "task_checkpoints.jsonl").exists()
    assert (export_root / "memory_proposals.jsonl").exists()
    assert (export_root / "memory_decisions.jsonl").exists()
    assert (export_root / "handoff_packs").is_dir()
    assert (export_root / "handoff_packs" / "index.jsonl").exists()

    manifest = json.loads((export_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contents"]["taskSessions"] == "task_sessions.jsonl"
    assert manifest["contents"]["taskEvents"] == "task_events.jsonl"
    assert manifest["contents"]["taskCheckpoints"] == "task_checkpoints.jsonl"
    assert manifest["contents"]["memoryProposals"] == "memory_proposals.jsonl"
    assert manifest["contents"]["memoryDecisions"] == "memory_decisions.jsonl"
    assert manifest["contents"]["handoffPacks"] == "handoff_packs/"
    assert manifest["counts"]["taskSessions"] >= 1
    assert manifest["counts"]["taskEvents"] >= 1
    assert manifest["counts"]["taskCheckpoints"] >= 1
    assert manifest["counts"]["memoryProposals"] >= 1
    assert manifest["counts"]["memoryDecisions"] >= 1
    assert manifest["counts"]["handoffPacks"] >= 1

def test_export_accepted_proposal_provenance_is_correct(tmp_path) -> None:
    import json

    from sqlmodel import Session

    from server.app.database import engine
    from server.app.export.bundle import export_knowledge_bundle
    from server.app.memory_kernel.proposals import accept_memory_proposal, create_memory_proposal

    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={"title": "Accepted proposal provenance", "userGoal": "验证 proposal provenance"},
        ).json()["task"]

    with Session(engine) as session:
        proposal = create_memory_proposal(
            session,
            proposal_type="technical_decision",
            title="导出 proposal provenance 标题",
            body="accepted proposal 应连到 task、source 和 knowledge item。",
            evidence_refs=["test:export-accepted-proposal"],
            task_session_id=task["id"],
        )
        accept_memory_proposal(session, proposal)
        session.commit()
        proposal_id = proposal.id
        source_item_id = proposal.source_item_id
        knowledge_item_id = proposal.knowledge_item_id

        export_root = export_knowledge_bundle(session, tmp_path)

    provenance = [json.loads(line) for line in (export_root / "provenance.jsonl").read_text(encoding="utf-8").splitlines()]
    decisions = [json.loads(line) for line in (export_root / "memory_decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    proposals = [json.loads(line) for line in (export_root / "memory_proposals.jsonl").read_text(encoding="utf-8").splitlines()]
    proposal_payload = next(item for item in proposals if item["id"] == proposal_id)
    assert proposal_payload["targetStore"] == "semantic_knowledge"
    assert proposal_payload["decisionRef"]
    assert any(item["decisionType"] == "proposal_accepted" and item["targetRef"] == f"proposal:{proposal_id}" for item in decisions)
    assert any(line["type"] == "proposal_routed" and line["from"] == f"proposal:{proposal_id}" for line in provenance)
    assert any(item["type"] == "proposal_for_task" and item["from"] == f"proposal:{proposal_id}" and item["to"] == f"task:{task['id']}" for item in provenance)
    assert any(
        item["type"] == "proposal_created_source"
        and item["from"] == f"proposal:{proposal_id}"
        and item["to"] == f"source:{source_item_id}"
        for item in provenance
    )
    assert any(
        item["type"] == "accepted_proposal_created_item"
        and item["from"] == f"proposal:{proposal_id}"
        and item["to"] == f"item:{knowledge_item_id}"
        for item in provenance
    )

def test_export_accepted_page_update_proposal_provenance_is_correct(tmp_path) -> None:
    import json

    from sqlmodel import Session

    from server.app.database import engine
    from server.app.export.bundle import export_knowledge_bundle
    from server.app.memory_kernel.proposals import accept_memory_proposal, create_memory_proposal

    with Session(engine) as session:
        proposal = create_memory_proposal(
            session,
            proposal_type="page_update",
            title="导出 page proposal provenance",
            body="page_update proposal 应连到 knowledge page。",
            structured_payload={"body": "页面正文来自 reviewed proposal。"},
            evidence_refs=["test:export-page-proposal"],
            review_note="接受为主题页",
        )
        accept_memory_proposal(session, proposal)
        session.commit()
        proposal_id = proposal.id
        page_id = proposal.page_id

        export_root = export_knowledge_bundle(session, tmp_path)

    proposals = [json.loads(line) for line in (export_root / "memory_proposals.jsonl").read_text(encoding="utf-8").splitlines()]
    decisions = [json.loads(line) for line in (export_root / "memory_decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    provenance = [json.loads(line) for line in (export_root / "provenance.jsonl").read_text(encoding="utf-8").splitlines()]
    proposal_payload = next(item for item in proposals if item["id"] == proposal_id)

    assert proposal_payload["targetStore"] == "semantic_knowledge"
    assert proposal_payload["pageId"] == page_id
    assert proposal_payload["knowledgeItemId"] is None
    assert any(
        item["decisionType"] == "proposal_accepted"
        and item["targetRef"] == f"proposal:{proposal_id}"
        and item["reason"] == "接受为主题页"
        for item in decisions
    )
    assert any(line["type"] == "accepted_proposal_created_page" and line["from"] == f"proposal:{proposal_id}" for line in provenance)
    assert any(
        item["type"] == "accepted_proposal_created_page"
        and item["from"] == f"proposal:{proposal_id}"
        and item["to"] == f"page:{page_id}"
        for item in provenance
    )

def test_export_task_checkpoint_handoff_and_dismissed_proposal(tmp_path) -> None:
    import json

    from sqlmodel import Session

    from server.app.database import engine
    from server.app.export.bundle import export_knowledge_bundle
    from server.app.memory_kernel.proposals import create_memory_proposal, dismiss_memory_proposal

    marker = "dismissed proposal export only"
    with TestClient(app) as client:
        task = client.post(
            "/api/tasks",
            json={"title": "Task checkpoint handoff export", "userGoal": "验证任务相关导出"},
        ).json()["task"]
        checkpoint = client.post(
            f"/api/tasks/{task['id']}/checkpoints",
            json={"title": "任务导出检查点", "summary": "checkpoint provenance 应连到 task"},
        ).json()
        handoff = client.post(f"/api/tasks/{task['id']}/handoff", params={"format": "markdown"}).json()

    with Session(engine) as session:
        proposal = create_memory_proposal(
            session,
            proposal_type="pitfall",
            title=f"{marker} 标题",
            body=f"{marker} 正文",
            evidence_refs=["test:export-dismissed-proposal"],
            task_session_id=task["id"],
        )
        dismiss_memory_proposal(session, proposal)
        session.commit()
        proposal_id = proposal.id

        export_root = export_knowledge_bundle(session, tmp_path)

    task_sessions = [json.loads(line) for line in (export_root / "task_sessions.jsonl").read_text(encoding="utf-8").splitlines()]
    checkpoints = [json.loads(line) for line in (export_root / "task_checkpoints.jsonl").read_text(encoding="utf-8").splitlines()]
    proposals = [json.loads(line) for line in (export_root / "memory_proposals.jsonl").read_text(encoding="utf-8").splitlines()]
    decisions = [json.loads(line) for line in (export_root / "memory_decisions.jsonl").read_text(encoding="utf-8").splitlines()]
    provenance = [json.loads(line) for line in (export_root / "provenance.jsonl").read_text(encoding="utf-8").splitlines()]
    handoff_index = [json.loads(line) for line in (export_root / "handoff_packs" / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    item_text = (export_root / "items.jsonl").read_text(encoding="utf-8")

    assert any(item["id"] == task["id"] for item in task_sessions)
    assert any(item["id"] == checkpoint["id"] and item["taskSessionId"] == task["id"] for item in checkpoints)
    assert any(item["id"] == handoff["id"] and item["taskSessionId"] == task["id"] for item in handoff_index)
    assert (export_root / "handoff_packs" / f"{handoff['id']}.md").exists()
    assert any(item["id"] == proposal_id and item["status"] == "dismissed" and item["targetStore"] == "procedure_lesson" for item in proposals)
    assert any(item["decisionType"] == "proposal_dismissed" and item["targetRef"] == f"proposal:{proposal_id}" for item in decisions)
    assert any(item["type"] == "proposal_dismissed" and item["from"] == f"proposal:{proposal_id}" for item in provenance)
    assert marker not in item_text
    assert any(
        item["type"] == "checkpoint_for_task"
        and item["from"] == f"checkpoint:{checkpoint['id']}"
        and item["to"] == f"task:{task['id']}"
        for item in provenance
    )
    assert any(
        item["type"] == "handoff_for_task"
        and item["from"] == f"handoff:{handoff['id']}"
        and item["to"] == f"task:{task['id']}"
        for item in provenance
    )
