from __future__ import annotations

import os
import tempfile

os.environ["SECOND_BRAIN_DATA_DIR"] = tempfile.mkdtemp(prefix="second-brain-test-")
os.environ["OPENAI_API_KEY"] = ""

from fastapi.testclient import TestClient

from server.app.main import app


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f"
    b"\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_text_card_crud_without_api_key() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W21", "textContent": "一段关于温暖便签的知识材料", "x": 10, "y": 20},
        )
        assert created.status_code == 200
        card = created.json()
        assert card["type"] == "text"

        cards = client.get("/api/weeks/2026-W21/cards").json()
        assert len(cards) == 1
        assert cards[0]["aiStatus"] == "failed"
        assert "OPENAI_API_KEY" in cards[0]["aiError"]

        patched = client.patch(f"/api/cards/{card['id']}", json={"x": 42, "keywords": ["琥珀", "便签"]})
        assert patched.status_code == 200
        assert patched.json()["x"] == 42
        assert patched.json()["keywords"] == ["琥珀", "便签"]


def test_text_card_without_api_key_keeps_source_without_searchable_knowledge_item() -> None:
    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.models import KnowledgeItem, SourceItem

    with TestClient(app) as client:
        created = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W20", "textContent": "只应保留原始来源的待分析材料", "x": 10, "y": 20},
        ).json()

        results = client.get("/api/knowledge/search", params={"q": "待分析材料"}).json()
        assert results == []

    with Session(engine) as session:
        source_item = session.exec(select(SourceItem).where(SourceItem.external_id == created["id"])).one()
        knowledge_items = session.exec(select(KnowledgeItem).where(KnowledgeItem.card_id == created["id"])).all()

    assert source_item.status == "active"
    assert source_item.content_text == "只应保留原始来源的待分析材料"
    assert knowledge_items == []


def test_image_card_upload_and_delete_without_api_key() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/cards/image",
            data={"weekKey": "2026-W22", "x": "14", "y": "28"},
            files={"file": ("tiny.png", PNG_1X1, "image/png")},
        )
        assert created.status_code == 200
        card = created.json()
        assert card["imageUrl"].startswith("/uploads/")

        deleted = client.delete(f"/api/cards/{card['id']}")
        assert deleted.status_code == 204
        assert client.get("/api/weeks/2026-W22/cards").json() == []


def test_knowledge_search_indexes_successfully_analyzed_card(monkeypatch) -> None:
    from server.app import ai

    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai.settings, "openai_model", "test-model")
    monkeypatch.setattr(
        ai,
        "_analyze_with_provider",
        lambda _card: {"summary": "用于检验全文索引同步", "keywords": ["索引同步验收"]},
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W40", "textContent": "这个片段包含统一知识工作台线索", "x": 10, "y": 20},
        ).json()

        text_results = client.get("/api/knowledge/search", params={"q": "用于检验全文索引同步"}).json()
        assert any(result["card"]["id"] == created["id"] for result in text_results if result.get("card"))

        keyword_results = client.get("/api/knowledge/search", params={"q": "索引同步验收"}).json()
        assert keyword_results[0]["card"]["id"] == created["id"]
        assert "关键词：索引同步验收" in keyword_results[0]["matchedFields"]
        assert keyword_results[0]["excerpt"]
        assert keyword_results[0]["reason"]
        assert keyword_results[0]["source"]


def test_recoverable_analysis_job_resumes_running_work(monkeypatch) -> None:
    from uuid import uuid4

    from sqlmodel import Session, select

    from server.app import ai
    from server.app.analysis.jobs import run_recoverable_analysis_jobs
    from server.app.database import engine
    from server.app.models import AnalysisJob, Card, KnowledgeItem

    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai.settings, "openai_model", "test-model")
    monkeypatch.setattr(
        ai,
        "_analyze_with_provider",
        lambda _card: {"summary": "恢复任务生成正式知识", "keywords": ["任务恢复"]},
    )

    card_id = str(uuid4())
    job_id = str(uuid4())
    with Session(engine) as session:
        session.add(
            Card(
                id=card_id,
                week_key="2026-W48",
                type="text",
                text_content="进程中断前还没完成的材料",
                style_seed="recover",
                ai_status="generating",
                keywords=[],
            ),
        )
        session.add(AnalysisJob(id=job_id, card_id=card_id, status="running", reason="test_recovery", attempts=1))
        session.commit()

    assert run_recoverable_analysis_jobs() >= 1

    with Session(engine) as session:
        card = session.get(Card, card_id)
        job = session.get(AnalysisJob, job_id)
        knowledge_item = session.exec(select(KnowledgeItem).where(KnowledgeItem.card_id == card_id)).one()

    assert card
    assert card.ai_status == "done"
    assert job
    assert job.status == "succeeded"
    assert job.attempts == 2
    assert knowledge_item.summary == "恢复任务生成正式知识"


def test_retrieval_engine_can_search_without_route_or_sqlite_fts(monkeypatch) -> None:
    from sqlmodel import Session, select

    from server.app import ai
    from server.app.database import engine
    from server.app.models import KnowledgeItem
    from server.app.retrieval.engine import RetrievalEngine

    class FakeIndex:
        def __init__(self, knowledge_item_id: str) -> None:
            self.knowledge_item_id = knowledge_item_id

        def search_knowledge_item_ids(self, session, query: str, limit: int) -> list[str]:
            return [self.knowledge_item_id]

    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai.settings, "openai_model", "test-model")
    monkeypatch.setattr(
        ai,
        "_analyze_with_provider",
        lambda _card: {"summary": "直接调用检索引擎的摘要", "keywords": ["检索接口"]},
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W42", "textContent": "检索引擎独立测试", "x": 10, "y": 20},
        ).json()

    with Session(engine) as session:
        knowledge_item = session.exec(select(KnowledgeItem).where(KnowledgeItem.card_id == created["id"])).one()
        results = RetrievalEngine(index=FakeIndex(knowledge_item.id)).search(session, "检索接口")

    assert results[0].knowledge_item.id == knowledge_item.id
    assert results[0].score >= 60
    assert results[0].matched_fields
    assert results[0].excerpt
    assert results[0].reason


def test_card_position_patch_does_not_refresh_knowledge_item(monkeypatch) -> None:
    from server.app import ai

    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai.settings, "openai_model", "test-model")
    monkeypatch.setattr(
        ai,
        "_analyze_with_provider",
        lambda _card: {"summary": "拖动不应刷新知识索引", "keywords": ["位置保持"]},
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W39", "textContent": "拖动不应刷新知识索引", "x": 10, "y": 20},
        ).json()

        before = client.get("/api/knowledge/search", params={"q": "拖动不应刷新"}).json()[0]["knowledgeItem"]
        patched = client.patch(f"/api/cards/{created['id']}", json={"x": 333, "y": 444})
        assert patched.status_code == 200

        after = client.get("/api/knowledge/search", params={"q": "拖动不应刷新"}).json()[0]["knowledgeItem"]
        assert after["id"] == before["id"]
        assert after["updatedAt"] == before["updatedAt"]


def test_reflection_trigger_acceptance_creates_knowledge_page_with_item_links(monkeypatch) -> None:
    from sqlmodel import Session, select

    from server.app import ai
    from server.app.database import engine
    from server.app.models import KnowledgePage, KnowledgePageItemLink, KnowledgeItem

    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai.settings, "openai_model", "test-model")

    def fake_analyze(card):
        return {"summary": f"整理建议内容 {card.text_content}", "keywords": ["阶段一反思主题"]}

    monkeypatch.setattr(ai, "_analyze_with_provider", fake_analyze)

    with TestClient(app) as client:
        for index in range(5):
            client.post(
                "/api/cards/text",
                json={"weekKey": "2026-W41", "textContent": f"第 {index} 条反思触发内容", "x": 10, "y": 20},
            ).json()

        reflections = client.get("/api/reflections").json()
        target = next(item for item in reflections if "阶段一反思主题" in item["title"])
        accept = client.post(f"/api/reflections/{target['id']}/accept")
        assert accept.status_code == 200
        assert accept.json()["status"] == "accepted"

        pending_after = client.get("/api/reflections").json()
        assert all(item["id"] != target["id"] for item in pending_after)

        pages = client.get("/api/knowledge/pages")
        assert pages.status_code == 200
        page_payload = next(item for item in pages.json() if item["title"] == "阶段一反思主题")
        assert page_payload["itemCount"] == 5

    with Session(engine) as session:
        page = session.exec(select(KnowledgePage).where(KnowledgePage.title == "阶段一反思主题")).one()
        links = session.exec(select(KnowledgePageItemLink).where(KnowledgePageItemLink.page_id == page.id)).all()
        linked_knowledge_item_ids = {link.knowledge_item_id for link in links}
        knowledge_items = session.exec(select(KnowledgeItem).where(KnowledgeItem.id.in_(linked_knowledge_item_ids))).all()

    assert page.status == "draft"
    assert page.title == "阶段一反思主题"
    assert page.summary == target["reason"]
    assert "阶段一反思主题" in page.keywords
    assert len(links) == 5
    assert len(knowledge_items) == 5
    assert all(knowledge_item.status == "active" for knowledge_item in knowledge_items)


def test_deleting_linked_cards_updates_page_evidence_and_context(monkeypatch) -> None:
    from sqlmodel import Session, select

    from server.app import ai
    from server.app.database import engine
    from server.app.models import KnowledgeItem, KnowledgePage, SourceItem

    topic = "删除联动主题"

    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai.settings, "openai_model", "test-model")
    monkeypatch.setattr(
        ai,
        "_analyze_with_provider",
        lambda card: {"summary": f"{topic} 证据 {card.text_content}", "keywords": [topic]},
    )

    with TestClient(app) as client:
        cards = [
            client.post(
                "/api/cards/text",
                json={"weekKey": "2026-W46", "textContent": f"{topic} 原始材料 {index}", "x": 10, "y": 20},
            ).json()
            for index in range(5)
        ]
        card_ids = [card["id"] for card in cards]

        reflection = next(item for item in client.get("/api/reflections").json() if topic in item["title"])
        client.post(f"/api/reflections/{reflection['id']}/accept")

        first_knowledge_item_id: str
        with Session(engine) as session:
            first_knowledge_item_id = session.exec(
                select(KnowledgeItem).where(KnowledgeItem.card_id == card_ids[0]),
            ).one().id

        assert client.delete(f"/api/cards/{card_ids[0]}").status_code == 204

        page_payload = next(item for item in client.get("/api/knowledge/pages").json() if item["title"] == topic)
        assert page_payload["status"] == "stale"
        assert page_payload["itemCount"] == 4

        context = client.get(
            "/api/knowledge/context",
            params={"q": topic, "itemLimit": "10", "pageLimit": "2", "sourceExcerptLimit": "5"},
        ).json()
        assert all(item["id"] != first_knowledge_item_id for item in context["relatedItems"])
        assert all(f"item:{first_knowledge_item_id}" not in page["itemRefs"] for page in context["relatedPages"])

        for card_id in card_ids[1:]:
            assert client.delete(f"/api/cards/{card_id}").status_code == 204

        assert all(item["title"] != topic for item in client.get("/api/knowledge/pages").json())
        final_context = client.get("/api/knowledge/context", params={"q": topic, "itemLimit": "10", "pageLimit": "2"}).json()
        assert final_context["relatedItems"] == []
        assert final_context["relatedPages"] == []

    with Session(engine) as session:
        page = session.exec(select(KnowledgePage).where(KnowledgePage.title == topic)).one()
        knowledge_items = session.exec(select(KnowledgeItem).where(KnowledgeItem.card_id.in_(card_ids))).all()
        source_items = session.exec(select(SourceItem).where(SourceItem.external_id.in_(card_ids))).all()

    assert page.status == "archived"
    assert len(knowledge_items) == 5
    assert all(knowledge_item.status == "archived" for knowledge_item in knowledge_items)
    assert len(source_items) == 5
    assert all(source_item.status == "active" for source_item in source_items)


def test_deleting_card_before_accepting_reflection_dismisses_stale_suggestion(monkeypatch) -> None:
    from server.app import ai

    topic = "待接受建议动态失效"

    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai.settings, "openai_model", "test-model")
    monkeypatch.setattr(
        ai,
        "_analyze_with_provider",
        lambda card: {"summary": f"{topic} 证据 {card.text_content}", "keywords": [topic]},
    )

    with TestClient(app) as client:
        cards = [
            client.post(
                "/api/cards/text",
                json={"weekKey": "2026-W47", "textContent": f"{topic} 原始材料 {index}", "x": 10, "y": 20},
            ).json()
            for index in range(5)
        ]
        reflection = next(item for item in client.get("/api/reflections").json() if topic in item["title"])

        assert client.delete(f"/api/cards/{cards[0]['id']}").status_code == 204

        assert all(item["id"] != reflection["id"] for item in client.get("/api/reflections").json())
        all_reflections = client.get("/api/reflections", params={"status": "all"}).json()
        stale_reflection = next(item for item in all_reflections if item["id"] == reflection["id"])
        assert stale_reflection["status"] == "dismissed"


def test_context_pack_returns_budgeted_related_content_not_full_library(monkeypatch) -> None:
    from server.app import ai

    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai.settings, "openai_model", "test-model")

    def fake_analyze(card):
        if "灯塔协议" in (card.text_content or ""):
            return {"summary": f"灯塔协议证据 {card.text_content}", "keywords": ["灯塔协议"]}
        return {"summary": f"无关知识 {card.text_content}", "keywords": ["无关主题"]}

    monkeypatch.setattr(ai, "_analyze_with_provider", fake_analyze)

    with TestClient(app) as client:
        for index in range(5):
            client.post(
                "/api/cards/text",
                json={"weekKey": "2026-W43", "textContent": f"灯塔协议相关知识 {index}", "x": 10, "y": 20},
            )
        for index in range(3):
            client.post(
                "/api/cards/text",
                json={"weekKey": "2026-W44", "textContent": f"完全无关材料 {index}", "x": 10, "y": 20},
            )

        reflection = next(item for item in client.get("/api/reflections").json() if "灯塔协议" in item["title"])
        client.post(f"/api/reflections/{reflection['id']}/accept")

        response = client.get(
            "/api/knowledge/context",
            params={"q": "灯塔协议", "itemLimit": "2", "pageLimit": "1", "sourceExcerptLimit": "1", "maxChars": "2500"},
        )
        assert response.status_code == 200
        pack = response.json()

    assert pack["query"] == "灯塔协议"
    assert len(pack["relatedItems"]) == 2
    assert len(pack["relatedPages"]) <= 1
    assert len(pack["sourceExcerpts"]) <= 1
    assert pack["budget"]["maxItems"] == 2
    assert pack["budget"]["truncated"] is True
    assert all("灯塔协议" in item["summary"] or "灯塔协议" in item["excerpt"] for item in pack["relatedItems"])
    assert all("无关" not in item["summary"] for item in pack["relatedItems"])
    assert pack["citationRefs"]
    assert any("不要当成聊天接口" in line for line in pack["protocolReminder"])


def test_confirmed_external_ai_import_creates_formal_knowledge_and_page_suggestion() -> None:
    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.models import KnowledgePage, KnowledgeItem, SourceItem

    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge/import-confirmed",
            json={
                "title": "KnowledgeItem 与 KnowledgePage 边界",
                "summary": "KnowledgeItem 是原子证据，KnowledgePage 是主题编译成果。",
                "body": "外部 AI 已经展示给用户并由用户确认，因此可以直接进入正式知识库。",
                "keywords": ["外部 AI 写入", "知识边界"],
                "selectedOriginalText": "用户和外部 AI 讨论后确认：原子证据和主题页需要分层维护。",
                "sourceTitle": "Claude 整理片段",
                "sourceUrl": "https://example.test/session/42",
                "externalId": "claude-session-42",
                "proposedPages": ["个人知识库设计原则"],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["sourceItemId"]
        assert payload["knowledgeItem"]["status"] == "active"
        assert payload["knowledgeItem"]["cardId"] is None
        assert payload["suggestionIds"]

        search = client.get("/api/knowledge/search", params={"q": "知识边界"}).json()
        assert search
        assert search[0]["knowledgeItem"]["id"] == payload["knowledgeItem"]["id"]

        reflections = client.get("/api/reflections").json()
        assert any(item["id"] in payload["suggestionIds"] and "个人知识库设计原则" in item["title"] for item in reflections)

    with Session(engine) as session:
        source_item = session.exec(select(SourceItem).where(SourceItem.id == payload["sourceItemId"])).one()
        knowledge_item = session.exec(select(KnowledgeItem).where(KnowledgeItem.id == payload["knowledgeItem"]["id"])).one()
        pages = session.exec(select(KnowledgePage).where(KnowledgePage.title == "个人知识库设计原则")).all()

    assert source_item.source == "external_ai"
    assert source_item.kind == "external_ai_note"
    assert source_item.content_text.startswith("用户和外部 AI 讨论后确认")
    assert knowledge_item.source_item_id == source_item.id
    assert knowledge_item.source_ref == "https://example.test/session/42"
    assert pages == []


def test_confirmed_external_ai_import_trims_external_id_and_keeps_original_text_as_content() -> None:
    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.models import KnowledgeItem, SourceItem

    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge/import-confirmed",
            json={
                "title": "外部导入正文回退",
                "keywords": ["正文回退"],
                "selectedOriginalText": "这段原文应在没有 summary/body 时成为正式知识内容。",
                "externalId": "  external-original-text-1  ",
            },
        )
        assert response.status_code == 200
        payload = response.json()

        search = client.get("/api/knowledge/search", params={"q": "正文回退"}).json()
        assert search[0]["knowledgeItem"]["content"] == "这段原文应在没有 summary/body 时成为正式知识内容。"

    with Session(engine) as session:
        source_item = session.exec(select(SourceItem).where(SourceItem.id == payload["sourceItemId"])).one()
        knowledge_item = session.exec(select(KnowledgeItem).where(KnowledgeItem.id == payload["knowledgeItem"]["id"])).one()

    assert source_item.external_id == "external-original-text-1"
    assert knowledge_item.content == source_item.content_text


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


def test_task_capsule_core_api_lifecycle() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={
                "title": "Task Capsule 后端闭环",
                "userGoal": "实现任务胶囊核心 API",
                "activeAgent": "codex",
            },
        )
        assert created.status_code == 200
        task_detail = created.json()
        task_id = task_detail["task"]["id"]
        initial_last_event_at = task_detail["task"]["lastEventAt"]

        active_tasks = client.get("/api/tasks", params={"status": "active"})
        assert active_tasks.status_code == 200
        assert any(task["id"] == task_id and task["status"] == "open" for task in active_tasks.json())

        appended = client.post(
            f"/api/tasks/{task_id}/events",
            json={
                "type": "agent_action",
                "summary": "补齐 Task Capsule route",
                "payload": {"files": ["server/app/routes/tasks.py"]},
            },
        )
        assert appended.status_code == 200
        event_payload = appended.json()
        assert event_payload["summary"] == "补齐 Task Capsule route"

        refreshed = client.get(f"/api/tasks/{task_id}")
        assert refreshed.status_code == 200
        refreshed_detail = refreshed.json()
        assert refreshed_detail["task"]["lastEventAt"] == event_payload["createdAt"]
        assert refreshed_detail["task"]["lastEventAt"] != initial_last_event_at

        event_id = event_payload["id"]
        assert client.patch(f"/api/tasks/{task_id}/events/{event_id}", json={"summary": "不允许修改"}).status_code == 404
        assert client.delete(f"/api/tasks/{task_id}/events/{event_id}").status_code == 404

        patched_state = client.patch(
            f"/api/tasks/{task_id}/state",
            json={
                "currentGoal": "完成后端核心 API 和测试",
                "done": ["确认模型存在"],
                "inProgress": ["编写 route"],
                "nextSteps": ["运行 pytest"],
                "openQuestions": ["是否需要前端入口"],
                "decisions": ["事件保持 append-only"],
                "risks": ["关闭任务不能自动写入 KnowledgeItem"],
                "filesTouched": ["server/app/routes/tasks.py"],
            },
        )
        assert patched_state.status_code == 200
        assert patched_state.json()["nextSteps"] == ["运行 pytest"]

        detail_after_state = client.get(f"/api/tasks/{task_id}").json()
        assert detail_after_state["state"]["nextSteps"] == ["运行 pytest"]

        checkpoint = client.post(
            f"/api/tasks/{task_id}/checkpoints",
            json={"title": "核心 API 已完成", "summary": "任务状态、事件和检查点 API 已连通"},
        )
        assert checkpoint.status_code == 200
        checkpoint_payload = checkpoint.json()
        assert checkpoint_payload["taskSessionId"] == task_id
        assert checkpoint_payload["stateSnapshot"]["nextSteps"] == ["运行 pytest"]

        detail_after_checkpoint = client.get(f"/api/tasks/{task_id}").json()
        assert any(item["id"] == checkpoint_payload["id"] for item in detail_after_checkpoint["checkpoints"])

        closed = client.post(f"/api/tasks/{task_id}/close")
        assert closed.status_code == 200
        assert closed.json()["task"]["status"] == "closed"

        assert client.patch(f"/api/tasks/{task_id}/state", json={"nextSteps": ["不应写入"]}).status_code == 409
        assert client.post(
            f"/api/tasks/{task_id}/events",
            json={"type": "agent_action", "summary": "不应追加"},
        ).status_code == 409
        assert client.post(
            f"/api/tasks/{task_id}/checkpoints",
            json={"title": "不应创建", "summary": "终态不可变"},
        ).status_code == 409

        active_after_close = client.get("/api/tasks", params={"status": "active"}).json()
        assert all(task["id"] != task_id for task in active_after_close)

        workbench = client.get("/api/review/workbench", params={"proposalStatus": "pending"})
        assert workbench.status_code == 200
        task_proposal = next(item for item in workbench.json()["proposals"] if item["taskSessionId"] == task_id)
        assert task_proposal["status"] == "pending"
        assert task_proposal["knowledgeItemId"] is None
        assert task_proposal["sourceItemId"] is None


def test_open_task_handoff_contains_next_steps() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Handoff open task", "userGoal": "完成 handoff 协议", "activeAgent": "codex"},
        ).json()
        task_id = created["task"]["id"]

        client.patch(
            f"/api/tasks/{task_id}/state",
            json={
                "currentGoal": "交接给下一个执行者",
                "done": ["完成核心任务 API"],
                "inProgress": ["编写 handoff service"],
                "nextSteps": ["运行 handoff 后端测试"],
                "openQuestions": ["是否需要前端入口"],
                "constraints": ["不启动本地服务"],
                "decisions": ["GET 预览，POST 持久化"],
                "risks": ["closed task 默认拒绝 handoff"],
                "filesTouched": ["server/app/tasks/handoff.py"],
            },
        )
        client.post(
            f"/api/tasks/{task_id}/events",
            json={"type": "file_change", "summary": "新增 handoff service", "sourceRef": "server/app/tasks/handoff.py"},
        )
        checkpoint = client.post(
            f"/api/tasks/{task_id}/checkpoints",
            json={"title": "handoff checkpoint", "summary": "handoff 协议字段已确定"},
        ).json()

        response = client.get(f"/api/tasks/{task_id}/handoff", params={"format": "json"})
        assert response.status_code == 200
        handoff = response.json()
        pack = handoff["pack"]

        assert pack["taskId"] == task_id
        assert pack["status"] == "open"
        assert pack["freshness"]["state"] == "fresh"
        assert pack["userGoal"] == "完成 handoff 协议"
        assert pack["currentGoal"] == "交接给下一个执行者"
        assert pack["done"] == ["完成核心任务 API"]
        assert pack["inProgress"] == ["编写 handoff service"]
        assert pack["nextSteps"] == ["运行 handoff 后端测试"]
        assert pack["openQuestions"] == ["是否需要前端入口"]
        assert pack["constraints"] == ["不启动本地服务"]
        assert pack["decisions"] == ["GET 预览，POST 持久化"]
        assert pack["risks"] == ["closed task 默认拒绝 handoff"]
        assert pack["filesTouched"] == ["server/app/tasks/handoff.py"]
        assert any(ref["id"] == checkpoint["id"] for ref in pack["checkpointRefs"])
        assert any(ref["sourceRef"] == "server/app/tasks/handoff.py" for ref in pack["sourceRefs"])
        assert "运行 handoff 后端测试" in handoff["content"]


def test_closed_task_handoff_is_rejected_by_default() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Closed handoff default", "userGoal": "验证 closed 默认拒绝"},
        ).json()
        task_id = created["task"]["id"]

        assert client.post(f"/api/tasks/{task_id}/close").status_code == 200

        response = client.get(f"/api/tasks/{task_id}/handoff", params={"format": "markdown"})
        assert response.status_code == 409


def test_include_closed_allows_closed_task_handoff() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Closed handoff include", "userGoal": "显式允许 closed handoff"},
        ).json()
        task_id = created["task"]["id"]
        client.post(f"/api/tasks/{task_id}/close")

        response = client.get(
            f"/api/tasks/{task_id}/handoff",
            params={"format": "json", "includeClosed": "true"},
        )
        assert response.status_code == 200
        assert response.json()["pack"]["status"] == "closed"


def test_expired_task_handoff_contains_stale_warning() -> None:
    from datetime import timedelta

    from sqlmodel import Session, select

    from server.app.database import engine
    from server.app.models import TaskSession, utc_now

    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Expired handoff", "userGoal": "验证过期 handoff 警告"},
        ).json()
        task_id = created["task"]["id"]

        with Session(engine) as session:
            task = session.get(TaskSession, task_id)
            assert task
            task.status = "expired"
            task.updated_at = utc_now() - timedelta(days=2)
            task.expires_at = utc_now() - timedelta(minutes=1)
            session.add(task)
            session.commit()

        response = client.get(f"/api/tasks/{task_id}/handoff", params={"format": "markdown"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["pack"]["freshness"]["state"] == "expired"
        assert payload["content"].startswith("> 过期提醒：")


def test_create_handoff_records_handoff_created_event() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"title": "Persist handoff", "userGoal": "POST handoff 写事件"},
        ).json()
        task_id = created["task"]["id"]

        response = client.post(f"/api/tasks/{task_id}/handoff", params={"format": "markdown"})
        assert response.status_code == 200
        handoff = response.json()
        assert handoff["id"]
        assert handoff["format"] == "markdown"

        detail = client.get(f"/api/tasks/{task_id}").json()
        handoff_event = next(event for event in detail["events"] if event["type"] == "handoff_created")
        assert handoff_event["payload"]["handoffPackId"] == handoff["id"]
        assert handoff_event["payload"]["format"] == "markdown"


def test_context_pack_can_return_directly_matched_page_without_item_match() -> None:
    from sqlmodel import Session

    from server.app.database import engine
    from server.app.wiki.pages import upsert_knowledge_page

    with Session(engine) as session:
        page = upsert_knowledge_page(
            session,
            title="直接命中的主题页",
            summary="这是一页只靠主题摘要就能命中的长期知识。",
            keywords=["主题页直达"],
            status="active",
        )
        session.commit()
        page_id = page.id

    with TestClient(app) as client:
        response = client.get("/api/knowledge/context", params={"q": "主题页直达", "itemLimit": "1", "pageLimit": "2"})
        assert response.status_code == 200
        pack = response.json()

    assert any(item["id"] == page_id for item in pack["relatedPages"])
    assert pack["relatedItems"] == []
    assert any(ref["ref"] == f"page:{page_id}" for ref in pack["citationRefs"])


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
                "subject": {"type": "user", "name": "Agent Step6 User"},
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

        allowed = client.get(
            "/api/agent/context",
            params=[("q", marker), ("caller", "agent-test"), ("capabilityProfile", "profile"), ("capability", "profile_memory")],
        )
        assert allowed.status_code == 200
        assert allowed.json()["profileFacts"][0]["ref"] == f"fact:{fact_id}"

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
