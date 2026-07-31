from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from .support import PNG_1X1, app

from server.app.analysis.jobs import run_recoverable_analysis_jobs
from server.app.database import engine
from server.app.models import AnalysisJob, Card


DAY_KEY = "2026-07-21"


def configure_fake_ai(monkeypatch, *, summary: str = "自动提炼结果", keywords: list[str] | None = None) -> None:
    from server.app import ai

    monkeypatch.setattr(ai.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(ai.settings, "openai_base_url", "https://example.test/v1")
    monkeypatch.setattr(ai.settings, "openai_model", "test-model")
    monkeypatch.setattr(
        ai,
        "_analyze_with_provider",
        lambda _card: {"summary": summary, "keywords": keywords or ["提炼", "白板"]},
    )


def test_text_card_is_created_and_analyzed(monkeypatch) -> None:
    configure_fake_ai(monkeypatch)

    with TestClient(app) as client:
        response = client.post(
            "/api/cards/text",
            json={"dayKey": DAY_KEY, "textContent": "粘贴进来的文本", "x": 0.12, "y": 0.16},
        )
        assert response.status_code == 200
        card_id = response.json()["id"]

        cards = client.get(f"/api/days/{DAY_KEY}/cards").json()
        card = next(item for item in cards if item["id"] == card_id)

    assert card["textContent"] == "粘贴进来的文本"
    assert card["summary"] == "自动提炼结果"
    assert card["keywords"] == ["提炼", "白板"]
    assert card["aiStatus"] == "done"
    assert card["rotation"] == 0
    assert card["dayKey"] == DAY_KEY
    assert DAY_KEY in client.get("/api/days").json()


def test_link_card_keeps_preview_and_analysis(monkeypatch) -> None:
    configure_fake_ai(monkeypatch, summary="链接摘要", keywords=["链接"])
    monkeypatch.setattr(
        "server.app.routes.cards.fetch_link_preview",
        lambda _url: {
            "url": "https://example.com/article",
            "title": "示例文章",
            "description": "文章说明",
            "content": "文章正文",
        },
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/cards/link",
            json={"dayKey": DAY_KEY, "url": "https://example.com/article", "x": 0.1, "y": 0.2},
        )
        assert response.status_code == 200
        card_id = response.json()["id"]
        card = next(item for item in client.get(f"/api/days/{DAY_KEY}/cards").json() if item["id"] == card_id)

    assert card["sourceTitle"] == "示例文章"
    assert card["sourceDescription"] == "文章说明"
    assert card["summary"] == "链接摘要"


def test_image_card_accepts_supported_images(monkeypatch) -> None:
    configure_fake_ai(monkeypatch, summary="图片摘要", keywords=["截图"])

    with TestClient(app) as client:
        response = client.post(
            "/api/cards/image",
            data={"dayKey": DAY_KEY, "x": "0.28", "y": "0.31"},
            files={"file": ("capture.png", PNG_1X1, "image/png")},
        )
        assert response.status_code == 200
        card_id = response.json()["id"]
        card = next(item for item in client.get(f"/api/days/{DAY_KEY}/cards").json() if item["id"] == card_id)

    assert card["type"] == "image"
    assert card["imageUrl"].startswith("/uploads/")
    assert card["x"] == 0.28
    assert card["y"] == 0.31
    assert card["summary"] == "图片摘要"


def test_card_can_be_moved_edited_and_deleted(monkeypatch) -> None:
    configure_fake_ai(monkeypatch)
    delete_day = "2026-07-19"

    with TestClient(app) as client:
        card_id = client.post(
            "/api/cards/text",
            json={"dayKey": delete_day, "textContent": "可编辑卡片", "x": 0.1, "y": 0.2},
        ).json()["id"]
        patched = client.patch(f"/api/cards/{card_id}", json={"x": 0.3, "y": 0.42, "keywords": ["保留"]})
        assert patched.status_code == 200
        assert patched.json()["x"] == 0.3
        assert patched.json()["keywords"] == ["保留"]

        deleted = client.delete(f"/api/cards/{card_id}")
        assert deleted.status_code == 204
        assert all(item["id"] != card_id for item in client.get(f"/api/days/{delete_day}/cards").json())
        assert delete_day not in client.get("/api/days").json()


def test_interrupted_analysis_job_recovers(monkeypatch) -> None:
    configure_fake_ai(monkeypatch, summary="恢复后完成", keywords=["恢复"])
    card_id = str(uuid4())
    job_id = str(uuid4())

    with Session(engine) as session:
        session.add(
            Card(
                id=card_id,
                day_key=DAY_KEY,
                type="text",
                text_content="进程中断前的内容",
                style_seed="recover",
                ai_status="generating",
                keywords=[],
            ),
        )
        session.add(AnalysisJob(id=job_id, card_id=card_id, status="running", reason="test", attempts=1))
        session.commit()

    assert run_recoverable_analysis_jobs() >= 1

    with Session(engine) as session:
        card = session.get(Card, card_id)
        job = session.exec(select(AnalysisJob).where(AnalysisJob.id == job_id)).one()

    assert card and card.ai_status == "done" and card.summary == "恢复后完成"
    assert job.status == "succeeded" and job.attempts == 2


def test_days_only_lists_dates_with_cards(monkeypatch) -> None:
    configure_fake_ai(monkeypatch)

    with TestClient(app) as client:
        assert client.get("/api/days/2026-07-20/cards").json() == []
        assert "2026-07-20" not in client.get("/api/days").json()
        created = client.post(
            "/api/cards/text",
            json={"dayKey": "2026-07-20", "textContent": "昨天的记录", "x": 0.2, "y": 0.2},
        )
        assert created.status_code == 200
        assert "2026-07-20" in client.get("/api/days").json()


def test_card_creation_rejects_invalid_day_and_position() -> None:
    with TestClient(app) as client:
        invalid_day = client.post(
            "/api/cards/text",
            json={"dayKey": "not-a-date", "textContent": "内容", "x": 0.2, "y": 0.2},
        )
        invalid_position = client.post(
            "/api/cards/text",
            json={"dayKey": DAY_KEY, "textContent": "内容", "x": 2, "y": 0.2},
        )

    assert invalid_day.status_code == 400
    assert invalid_position.status_code == 422
