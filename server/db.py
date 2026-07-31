from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .config import DATABASE_PATH, DATA_DIR, UPLOAD_DIR


CARD_FIELDS = {
    "day_key",
    "type",
    "text_content",
    "image_filename",
    "media_width",
    "media_height",
    "position_space",
    "source_url",
    "source_title",
    "source_description",
    "source_app",
    "source_file",
    "source_kind",
    "source_captured_at",
    "source_confidence",
    "summary",
    "keywords",
    "x",
    "y",
    "style_seed",
    "ai_status",
    "ai_error",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cards (
                id TEXT PRIMARY KEY,
                day_key TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('text', 'link', 'image')),
                text_content TEXT,
                image_filename TEXT,
                media_width REAL,
                media_height REAL,
                position_space TEXT,
                source_url TEXT,
                source_title TEXT,
                source_description TEXT,
                summary TEXT,
                keywords TEXT NOT NULL DEFAULT '[]',
                x REAL NOT NULL,
                y REAL NOT NULL,
                style_seed TEXT NOT NULL,
                ai_status TEXT NOT NULL DEFAULT 'pending',
                ai_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS cards_day_key ON cards(day_key);
            """
        )
        existing_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(cards)").fetchall()
        }
        for name in [
            "media_width",
            "media_height",
            "position_space",
            "source_app",
            "source_file",
            "source_kind",
            "source_captured_at",
            "source_confidence",
        ]:
            if name not in existing_columns:
                column_type = "REAL" if name in {"media_width", "media_height"} else "TEXT"
                connection.execute(f"ALTER TABLE cards ADD COLUMN {name} {column_type}")
        connection.execute(
            """
            UPDATE cards
            SET summary = NULL, keywords = '[]', ai_status = 'done', ai_error = NULL
            WHERE image_filename LIKE 'cutout-%'
            """
        )
        missing_sizes = connection.execute(
            """
            SELECT id, image_filename
            FROM cards
            WHERE image_filename LIKE 'cutout-%'
              AND (media_width IS NULL OR media_height IS NULL)
            """
        ).fetchall()
        if missing_sizes:
            from PIL import Image

            for row in missing_sizes:
                path = UPLOAD_DIR / row["image_filename"]
                try:
                    with Image.open(path) as image:
                        width, height = image.size
                    connection.execute(
                        "UPDATE cards SET media_width = ?, media_height = ? WHERE id = ?",
                        (width, height, row["id"]),
                    )
                except (OSError, ValueError):
                    continue


def insert_card(card: dict[str, Any]) -> dict[str, Any]:
    timestamp = now()
    values = {**card, "keywords": json.dumps(card.get("keywords", []), ensure_ascii=False), "created_at": timestamp, "updated_at": timestamp}
    columns = ", ".join(values)
    placeholders = ", ".join(f":{key}" for key in values)
    with connect() as connection:
        connection.execute(f"INSERT INTO cards ({columns}) VALUES ({placeholders})", values)
    return get_card(card["id"])


def get_card(card_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    return serialize(row) if row else None


def list_cards(day_key: str) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM cards WHERE day_key = ? ORDER BY created_at",
            (day_key,),
        ).fetchall()
    return [serialize(row) for row in rows]


def list_days() -> list[str]:
    with connect() as connection:
        rows = connection.execute("SELECT DISTINCT day_key FROM cards ORDER BY day_key").fetchall()
    return [row["day_key"] for row in rows]


def update_card(card_id: str, **changes: Any) -> dict[str, Any] | None:
    updates = {key: value for key, value in changes.items() if key in CARD_FIELDS}
    if "keywords" in updates:
        updates["keywords"] = json.dumps(updates["keywords"], ensure_ascii=False)
    updates["updated_at"] = now()
    assignments = ", ".join(f"{key} = :{key}" for key in updates)
    with connect() as connection:
        cursor = connection.execute(
            f"UPDATE cards SET {assignments} WHERE id = :card_id",
            {**updates, "card_id": card_id},
        )
    return get_card(card_id) if cursor.rowcount else None


def delete_card(card_id: str) -> dict[str, Any] | None:
    card = get_card(card_id)
    if not card:
        return None
    with connect() as connection:
        connection.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    return card


def unfinished_card_ids() -> list[str]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM cards WHERE ai_status IN ('pending', 'generating') ORDER BY created_at"
        ).fetchall()
    return [row["id"] for row in rows]


def serialize(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    card_type = data["type"]
    is_cutout = bool(data["image_filename"] and data["image_filename"].startswith("cutout-"))
    media_width = data.get("media_width")
    media_height = data.get("media_height")
    if is_cutout and media_width:
        display_width = max(24, min(720, round(media_width)))
    else:
        display_width = 320 if card_type == "link" else 300 if card_type == "text" else 280
    keywords = json.loads(data["keywords"] or "[]")[:5]
    return {
        "id": data["id"],
        "dayKey": data["day_key"],
        "type": card_type,
        "textContent": data["text_content"],
        "imageUrl": f"/uploads/{data['image_filename']}" if data["image_filename"] else None,
        "isCutout": is_cutout,
        "mediaWidth": media_width,
        "mediaHeight": media_height,
        "positionSpace": data.get("position_space"),
        "sourceUrl": data["source_url"],
        "sourceTitle": data["source_title"],
        "sourceDescription": data["source_description"],
        "sourceApp": data.get("source_app"),
        "sourceFile": data.get("source_file"),
        "sourceKind": data.get("source_kind"),
        "sourceCapturedAt": data.get("source_captured_at"),
        "sourceConfidence": data.get("source_confidence"),
        "summary": data["summary"],
        "keywords": keywords,
        "x": data["x"],
        "y": data["y"],
        "width": display_width,
        "rotation": 0,
        "styleSeed": data["style_seed"],
        "aiStatus": data["ai_status"],
        "aiError": data["ai_error"],
        "createdAt": data["created_at"],
        "updatedAt": data["updated_at"],
        "imageFilename": data["image_filename"],
    }
