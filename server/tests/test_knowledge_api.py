from __future__ import annotations

from fastapi.testclient import TestClient

from server.tests.support import app


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
    selected_refs = {item["ref"] for item in pack["selectionTrace"] if item["status"] == "selected"}
    assert all(f"item:{item['id']}" in selected_refs for item in pack["relatedItems"])
    assert any(item["status"] in {"skipped", "truncated"} for item in pack["selectionTrace"])
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
