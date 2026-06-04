from __future__ import annotations

from sqlmodel import SQLModel, Session, create_engine

from server.app.indexing.sqlite_fts import init_knowledge_search_index, refresh_knowledge_search_index
from server.app.models import KnowledgeItem, SourceItem, utc_now
from server.app.retrieval.engine import RetrievalEngine
from server.app.retrieval.vector import LocalVectorSearch


def test_hybrid_retrieval_recovers_word_order_variants() -> None:
    with retrieval_session() as session:
        target = insert_item(
            session,
            item_id="target-word-order",
            title="Review gate memory",
            summary="The canonical phrase is agent memory review gate.",
            content="agent memory review gate protects long-term memory writes.",
            keywords=["agent memory review gate"],
        )
        insert_item(
            session,
            item_id="partial-distractor",
            title="Review gate distractor",
            summary="A partial note about review gates.",
            content="review gate appears here without the full memory phrase.",
            keywords=["review gate"],
        )
        session.commit()

        lexical_results = RetrievalEngine(mode="lexical").search(session, "review gate memory agent", limit=5)
        hybrid_results = RetrievalEngine(mode="hybrid").search(session, "review gate memory agent", limit=5)

    assert target.id not in [result.knowledge_item.id for result in lexical_results[:1]]
    assert hybrid_results[0].knowledge_item.id == target.id
    assert "向量召回" in hybrid_results[0].matched_fields


def test_exact_keyword_stays_above_vector_overlap() -> None:
    with retrieval_session() as session:
        target = insert_item(
            session,
            item_id="target-exact",
            title="Capability scoped ContextPack",
            summary="Exact target for capability scoped ContextPack.",
            content="capability scoped ContextPack should stay first for exact queries.",
            keywords=["capability scoped ContextPack"],
        )
        insert_item(
            session,
            item_id="overlap-distractor",
            title="Capability scope notes",
            summary="A related but incomplete note about capability and scope.",
            content="capability scope privacy agent memory context appears in this distractor.",
            keywords=["capability scope privacy"],
        )
        session.commit()

        results = RetrievalEngine(mode="hybrid").search(session, "capability scoped ContextPack", limit=5)

    assert results[0].knowledge_item.id == target.id
    assert any(field.startswith("关键词：") for field in results[0].matched_fields)


def test_local_vector_cache_invalidates_when_item_text_changes() -> None:
    item = KnowledgeItem(
        id="cache-target",
        source_item_id="source-cache-target",
        title="Alpha memory",
        summary="Alpha beta retrieval note.",
        content="alpha beta should be discoverable first.",
        keywords=["alpha beta"],
        source="test",
        knowledge_type="fragment",
        status="active",
    )
    search = LocalVectorSearch()

    assert search.search([item], "alpha beta", limit=1)[0].knowledge_item_id == item.id

    item.title = "Gamma memory"
    item.summary = "Gamma delta retrieval note."
    item.content = "gamma delta should be discoverable after edit."
    item.keywords = ["gamma delta"]

    assert search.search([item], "gamma delta", limit=1)[0].knowledge_item_id == item.id


def test_retrieval_snapshot_refreshes_when_item_is_updated() -> None:
    with retrieval_session() as session:
        item = insert_item(
            session,
            item_id="snapshot-target",
            title="Original note",
            summary="Original searchable text.",
            content="original searchable text",
            keywords=["original searchable"],
        )
        session.commit()
        engine = RetrievalEngine()

        assert engine.search(session, "original searchable", limit=1)[0].knowledge_item.id == item.id

        item.title = "Updated note"
        item.summary = "Fresh snapshot text."
        item.content = "fresh snapshot text"
        item.keywords = ["fresh snapshot"]
        item.updated_at = utc_now()
        refresh_knowledge_search_index(session, item)
        session.commit()

        assert engine.search(session, "fresh snapshot", limit=1)[0].knowledge_item.id == item.id


def retrieval_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    init_knowledge_search_index(engine)
    return Session(engine)


def insert_item(
    session: Session,
    *,
    item_id: str,
    title: str,
    summary: str,
    content: str,
    keywords: list[str],
) -> KnowledgeItem:
    source = SourceItem(
        id=f"source-{item_id}",
        source="test",
        external_id=f"source-{item_id}",
        kind="test",
        title=f"{title} source",
        content_text=content,
        status="active",
    )
    item = KnowledgeItem(
        id=item_id,
        source_item_id=source.id,
        title=title,
        summary=summary,
        content=content,
        keywords=keywords,
        source="test",
        source_ref=source.external_id,
        knowledge_type="fragment",
        status="active",
    )
    session.add(source)
    session.add(item)
    session.flush()
    refresh_knowledge_search_index(session, item)
    return item
