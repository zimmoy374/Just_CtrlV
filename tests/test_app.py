from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f"
    b"\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def load_app(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CTRLV_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    for name in ["server.app", "server.ai", "server.db", "server.desktop_capture", "server.settings", "server.config"]:
        if name in sys.modules:
            del sys.modules[name]
    package = sys.modules.get("server")
    if package:
        for child in ["app", "ai", "db", "desktop_capture", "settings", "config"]:
            if hasattr(package, child):
                delattr(package, child)
    module = importlib.import_module("server.app")
    monkeypatch.setattr(
        module.ai,
        "call_provider",
        lambda _card: {
            "summary": "自动摘要",
            "keywords": ["粘贴", "整理", "白板", "归档", "回看", "不会保存"],
        },
    )
    return module


def test_text_card_uses_one_table(tmp_path, monkeypatch) -> None:
    module = load_app(tmp_path, monkeypatch)
    with TestClient(module.app) as client:
        created = client.post(
            "/api/cards/text",
            json={"dayKey": "2026-07-21", "textContent": "一段内容", "x": 0.2, "y": 0.3},
        )
        assert created.status_code == 200
        cards = client.get("/api/days/2026-07-21/cards").json()
        assert cards[0]["summary"] == "自动摘要"
        assert cards[0]["keywords"] == ["粘贴", "整理", "白板", "归档", "回看"]

    with module.db.connect() as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert tables == ["cards"]


def test_card_move_retry_and_delete(tmp_path, monkeypatch) -> None:
    module = load_app(tmp_path, monkeypatch)
    with TestClient(module.app) as client:
        card_id = client.post(
            "/api/cards/text",
            json={"dayKey": "2026-07-21", "textContent": "可移动", "x": 0.1, "y": 0.1},
        ).json()["id"]
        moved = client.patch(f"/api/cards/{card_id}", json={"x": 0.4, "y": 0.5})
        assert moved.json()["x"] == 0.4
        outside = client.patch(f"/api/cards/{card_id}", json={"x": -0.2, "y": 1.4})
        assert outside.status_code == 200
        assert outside.json()["x"] == -0.2
        assert outside.json()["y"] == 1.4
        assert outside.json()["positionSpace"] == "world"
        assert client.patch(f"/api/cards/{card_id}", json={"x": 100_001}).status_code == 422
        assert client.patch(
            f"/api/cards/{card_id}",
            json={"keywords": ["一", "二", "三", "四", "五", "六"]},
        ).status_code == 422
        assert client.post(f"/api/cards/{card_id}/analyze").status_code == 200
        assert client.delete(f"/api/cards/{card_id}").status_code == 204
        assert client.get("/api/days/2026-07-21/cards").json() == []


def test_link_image_and_static_site(tmp_path, monkeypatch) -> None:
    module = load_app(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "fetch_preview",
        lambda _url: {
            "url": "https://example.com/article",
            "title": "示例文章",
            "description": "文章说明",
            "content": "文章正文",
        },
    )
    with TestClient(module.app) as client:
        link = client.post(
            "/api/cards/link",
            json={"dayKey": "2026-07-21", "url": "https://example.com/article", "x": 0.1, "y": 0.2},
        )
        image = client.post(
            "/api/cards/image",
            data={
                "dayKey": "2026-07-21",
                "x": "0.3",
                "y": "0.4",
                "cutout": "true",
                "displayWidth": "86",
                "displayHeight": "64",
            },
            files={"file": ("capture.png", PNG_1X1, "image/png")},
        )

        assert link.status_code == 200 and link.json()["sourceTitle"] == "示例文章"
        assert image.status_code == 200 and image.json()["imageUrl"].startswith("/uploads/")
        assert image.json()["isCutout"] is True
        assert image.json()["mediaWidth"] == 86
        assert image.json()["mediaHeight"] == 64
        assert image.json()["width"] == 86
        assert image.json()["positionSpace"] == "world"
        assert image.json()["aiStatus"] == "done"
        assert image.json()["summary"] is None
        assert image.json()["keywords"] == []
        assert client.get("/").status_code == 200
        assert "./src/app.js" in client.get("/").text
        app_source = client.get("/src/app.js")
        assert app_source.status_code == 200
        assert "await createImage(image, point)" in app_source.text
        assert "CARD_VIEWPORT_RATIO" in app_source.text
        assert "keepBoardElementInViewport" in app_source.text
        assert "--card-readability-scale" in app_source.text
        assert "article.style.left = `${card.x}px`" in app_source.text
        assert 'article.addEventListener("pointercancel"' in app_source.text
        assert "openCropper" not in app_source.text
        styles = client.get("/src/styles.css").text
        assert "cropper-" not in styles
        assert ".capture-card:not(.cutout-piece)" in styles
        assert "--card-action-scale" in styles
        assert client.get("/img/memory-paper-plane.png").status_code == 200
        assert client.get("/vendor/gsap.min.js").status_code == 200


def test_global_capture_settings(tmp_path, monkeypatch) -> None:
    module = load_app(tmp_path, monkeypatch)
    with TestClient(module.app) as client:
        setup = client.get("/api/settings/capture")
        assert setup.status_code == 200
        assert setup.json()["hotkey"] == "ctrl+shift+x"

        updated = client.patch(
            "/api/settings/capture",
            json={"dayMode": "current", "lastDay": "2026-07-20", "hotkey": "Alt + Shift + A"},
        )
        assert updated.status_code == 200
        assert updated.json()["lastDay"] == "2026-07-20"
        assert updated.json()["hotkey"] == "alt+shift+a"
        invalid = client.patch("/api/settings/capture", json={"hotkey": "x"})
        assert invalid.status_code == 400

        card_id = module.desktop_capture._save_piece(
            Image.new("RGBA", (12, 10), "white"),
            {
                "source_title": "测试窗口",
                "source_app": "Google Chrome",
                "source_url": "https://example.com/source",
                "source_kind": "webpage",
                "source_captured_at": "2026-07-24T10:20:30+08:00",
                "source_confidence": "exact",
            },
        )
        card = module.db.get_card(card_id)
        assert card["dayKey"] == "2026-07-20"
        assert card["sourceTitle"] == "测试窗口"
        assert card["sourceApp"] == "Google Chrome"
        assert card["sourceUrl"] == "https://example.com/source"
        assert card["sourceKind"] == "webpage"
        assert card["sourceConfidence"] == "exact"
        assert card["isCutout"] is True
        assert card["mediaWidth"] == 12
        assert card["mediaHeight"] == 10
        assert card["width"] == 24
        assert card["positionSpace"] == "world"
        assert card["x"] == 3000
        assert card["y"] == 2000
        assert card["aiStatus"] == "done"
        assert card["summary"] is None
        assert card["keywords"] == []


def test_selection_uses_topmost_window_under_cutout_center(tmp_path, monkeypatch) -> None:
    module = load_app(tmp_path, monkeypatch)
    snapshots = [
        {"handle": 12, "rect": (200, 100, 700, 600), "title": "上层窗口"},
        {"handle": 20, "rect": (0, 0, 1200, 900), "title": "底层窗口"},
    ]
    monkeypatch.setattr(
        module.desktop_capture,
        "_window_source_context",
        lambda snapshot, captured_at: {
            "source_title": snapshot["title"],
            "source_captured_at": captured_at,
        },
    )
    source = module.desktop_capture._source_context_for_selection(
        snapshots,
        20,
        (250, 180, 350, 280),
        0,
        0,
        "2026-07-24T10:20:30+08:00",
    )
    assert source["source_title"] == "上层窗口"


def test_capture_scissors_turns_smoothly_and_toolbar_stays_near_selection(tmp_path, monkeypatch) -> None:
    module = load_app(tmp_path, monkeypatch)

    scissors = module.desktop_capture._make_scissors_icon(Image, ImageDraw)
    assert scissors.size == (52, 52)
    assert {
        scissors.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False).size
        for angle in range(0, 360, 5)
    } == {(52, 52)}

    wrapped = module.desktop_capture._approach_angle(359, 1)
    limited = module.desktop_capture._approach_angle(10, 150)
    assert 359 < wrapped < 360
    assert limited == 22

    below = module.desktop_capture._selection_toolbar_position(
        (400, 180, 600, 360),
        (300, 50),
        (1000, 720),
    )
    above = module.desktop_capture._selection_toolbar_position(
        (400, 650, 600, 705),
        (300, 50),
        (1000, 720),
    )
    assert below == (350, 372)
    assert above == (350, 588)
