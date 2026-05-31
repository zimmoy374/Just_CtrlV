from __future__ import annotations

import re

from sqlalchemy import Engine, text
from sqlmodel import Session, select

from ..models import KnowledgeItem

INDEXABLE_KNOWLEDGE_STATUSES = {"active"}
KNOWLEDGE_SEARCH_INDEX_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_search_fts USING fts5(
    knowledge_item_id UNINDEXED,
    title,
    summary,
    content,
    keywords_text,
    tokenize='trigram'
)
"""


def _fts_query(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    escaped = cleaned.replace('"', '""')
    return f'"{escaped}"'


class SqliteFtsIndex:
    def search_knowledge_item_ids(self, session: Session, query: str, limit: int) -> list[str]:
        trimmed = query.strip()
        if not trimmed:
            return []
        try:
            rows = session.connection().execute(
                text(
                    """
                    SELECT knowledge_item_id
                    FROM knowledge_search_fts
                    WHERE knowledge_search_fts MATCH :query
                    LIMIT :limit
                    """,
                ),
                {"query": _fts_query(trimmed), "limit": limit},
            )
            return [str(row[0]) for row in rows]
        except Exception:
            return []


def init_knowledge_search_index(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(KNOWLEDGE_SEARCH_INDEX_DDL))


def refresh_knowledge_search_index(session: Session, knowledge_item: KnowledgeItem) -> None:
    connection = session.connection()
    connection.execute(
        text("DELETE FROM knowledge_search_fts WHERE knowledge_item_id = :knowledge_item_id"),
        {"knowledge_item_id": knowledge_item.id},
    )
    if knowledge_item.status not in INDEXABLE_KNOWLEDGE_STATUSES:
        return
    connection.execute(
        text(
            """
            INSERT INTO knowledge_search_fts(knowledge_item_id, title, summary, content, keywords_text)
            VALUES (:knowledge_item_id, :title, :summary, :content, :keywords_text)
            """,
        ),
        {
            "knowledge_item_id": knowledge_item.id,
            "title": knowledge_item.title or "",
            "summary": knowledge_item.summary or "",
            "content": knowledge_item.content or "",
            "keywords_text": " ".join(knowledge_item.keywords or []),
        },
    )


def rebuild_knowledge_search_index(session: Session) -> dict:
    connection = session.connection()
    connection.execute(text("DROP TABLE IF EXISTS knowledge_search_fts"))
    connection.execute(text(KNOWLEDGE_SEARCH_INDEX_DDL))
    knowledge_items = session.exec(select(KnowledgeItem)).all()
    indexed_count = 0
    skipped_count = 0
    for knowledge_item in knowledge_items:
        refresh_knowledge_search_index(session, knowledge_item)
        if knowledge_item.status in INDEXABLE_KNOWLEDGE_STATUSES:
            indexed_count += 1
        else:
            skipped_count += 1
    session.flush()
    return {
        "projection": "knowledge_search_fts",
        "status": "rebuilt",
        "indexedCount": indexed_count,
        "skippedCount": skipped_count,
        "sourceStore": "knowledge_items",
    }
