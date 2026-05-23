from __future__ import annotations

import os
import tempfile

os.environ["INSPIRATION_DATA_DIR"] = tempfile.mkdtemp(prefix="inspiration-test-")
os.environ["AI_PROVIDER"] = "gemini"
os.environ["GEMINI_API_KEY"] = ""

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
            json={"weekKey": "2026-W21", "textContent": "一段关于温暖便签的灵感", "x": 10, "y": 20},
        )
        assert created.status_code == 200
        card = created.json()
        assert card["type"] == "text"

        cards = client.get("/api/weeks/2026-W21/cards").json()
        assert len(cards) == 1
        assert cards[0]["aiStatus"] == "failed"
        assert "GEMINI_API_KEY" in cards[0]["aiError"]

        patched = client.patch(f"/api/cards/{card['id']}", json={"x": 42, "keywords": ["琥珀", "便签"]})
        assert patched.status_code == 200
        assert patched.json()["x"] == 42
        assert patched.json()["keywords"] == ["琥珀", "便签"]


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
