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


def test_keyword_search_matches_global_keywords_only() -> None:
    with TestClient(app) as client:
        warm_card = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W23", "textContent": "摘要里写了星图，但关键词不包含它", "x": 10, "y": 20},
        ).json()
        exact_card = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W24", "textContent": "一段真正的检索测试内容", "x": 20, "y": 30},
        ).json()
        fuzzy_card = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W25", "textContent": "另一段跨周测试内容", "x": 30, "y": 40},
        ).json()

        client.patch(f"/api/cards/{warm_card['id']}", json={"keywords": ["旁路标签"]})
        client.patch(f"/api/cards/{exact_card['id']}", json={"keywords": ["星图结构", "独特索引"]})
        client.patch(f"/api/cards/{fuzzy_card['id']}", json={"keywords": ["星图结构变体"]})

        empty = client.get("/api/search", params={"q": "   "})
        assert empty.status_code == 200
        assert empty.json() == []

        exact = client.get("/api/search", params={"q": "星图结构"})
        assert exact.status_code == 200
        exact_results = exact.json()
        assert exact_results[0]["card"]["id"] == exact_card["id"]
        assert exact_results[0]["matchedKeywords"] == ["星图结构"]
        assert all(result["card"]["id"] != warm_card["id"] for result in exact_results)

        partial = client.get("/api/search", params={"q": "星图"})
        assert partial.status_code == 200
        partial_ids = {result["card"]["id"] for result in partial.json()}
        assert {exact_card["id"], fuzzy_card["id"]}.issubset(partial_ids)


def test_knowledge_graph_hides_isolated_cards() -> None:
    with TestClient(app) as client:
        first = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W31", "textContent": "第一张有关联的卡片", "x": 10, "y": 20},
        ).json()
        second = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W32", "textContent": "第二张有关联的卡片", "x": 20, "y": 30},
        ).json()
        isolated = client.post(
            "/api/cards/text",
            json={"weekKey": "2026-W33", "textContent": "孤立卡片", "x": 30, "y": 40},
        ).json()

        client.patch(f"/api/cards/{first['id']}", json={"keywords": ["共享主题", "第一"]})
        client.patch(f"/api/cards/{second['id']}", json={"keywords": ["共享主题", "第二"]})
        client.patch(f"/api/cards/{isolated['id']}", json={"keywords": ["孤立主题"]})

        response = client.get("/api/graph")
        assert response.status_code == 200
        graph = response.json()
        node_ids = {node["id"] for node in graph["nodes"]}

        assert "keyword:共享主题" in node_ids
        assert f"card:{first['id']}" in node_ids
        assert f"card:{second['id']}" in node_ids
        assert f"card:{isolated['id']}" not in node_ids
        assert len(graph["edges"]) >= 2
