from __future__ import annotations

from fastapi.testclient import TestClient

from server.tests.support import PNG_1X1, app


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
