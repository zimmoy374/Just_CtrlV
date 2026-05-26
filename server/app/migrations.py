from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, text


Migration = tuple[str, Callable[[Engine], None]]


def run_migrations(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """,
            ),
        )
        applied = {str(row[0]) for row in connection.execute(text("SELECT id FROM schema_migrations"))}

    for migration_id, migration in MIGRATIONS:
        if migration_id in applied:
            continue
        migration(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO schema_migrations(id) VALUES (:id)"), {"id": migration_id})


def _create_analysis_jobs(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    card_id VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    reason VARCHAR NOT NULL,
                    error TEXT,
                    attempts INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    started_at DATETIME,
                    finished_at DATETIME
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_analysis_jobs_card_id ON analysis_jobs(card_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_analysis_jobs_status ON analysis_jobs(status)"))


def _create_memory_and_task_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_sessions (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    title VARCHAR NOT NULL,
                    user_goal TEXT NOT NULL,
                    status VARCHAR NOT NULL,
                    active_agent VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    last_event_at DATETIME,
                    closed_at DATETIME,
                    expires_at DATETIME
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_task_sessions_title ON task_sessions(title)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_task_sessions_status ON task_sessions(status)"))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_events (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    task_session_id VARCHAR NOT NULL,
                    type VARCHAR NOT NULL,
                    summary TEXT NOT NULL,
                    payload JSON NOT NULL,
                    source VARCHAR NOT NULL,
                    source_ref VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_task_events_task_session_id ON task_events(task_session_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_task_events_type ON task_events(type)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_task_events_source ON task_events(source)"))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_states (
                    task_session_id VARCHAR NOT NULL PRIMARY KEY,
                    current_goal TEXT NOT NULL,
                    done JSON NOT NULL,
                    in_progress JSON NOT NULL,
                    next_steps JSON NOT NULL,
                    open_questions JSON NOT NULL,
                    constraints JSON NOT NULL,
                    risks JSON NOT NULL,
                    decisions JSON NOT NULL,
                    files_touched JSON NOT NULL,
                    confidence FLOAT NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """,
            ),
        )

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_checkpoints (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    task_session_id VARCHAR NOT NULL,
                    title VARCHAR NOT NULL,
                    summary TEXT NOT NULL,
                    state_snapshot JSON NOT NULL,
                    event_from_id VARCHAR,
                    event_to_id VARCHAR,
                    created_at DATETIME NOT NULL
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_task_checkpoints_task_session_id ON task_checkpoints(task_session_id)"))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS handoff_packs (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    task_session_id VARCHAR NOT NULL,
                    format VARCHAR NOT NULL,
                    content TEXT NOT NULL,
                    budget JSON NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_handoff_packs_task_session_id ON handoff_packs(task_session_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_handoff_packs_format ON handoff_packs(format)"))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS memory_proposals (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    task_session_id VARCHAR,
                    type VARCHAR NOT NULL,
                    title VARCHAR NOT NULL,
                    body TEXT NOT NULL,
                    evidence_refs JSON NOT NULL,
                    status VARCHAR NOT NULL,
                    source_item_id VARCHAR,
                    knowledge_item_id VARCHAR,
                    page_id VARCHAR,
                    created_at DATETIME NOT NULL,
                    resolved_at DATETIME
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_task_session_id ON memory_proposals(task_session_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_type ON memory_proposals(type)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_status ON memory_proposals(status)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_source_item_id ON memory_proposals(source_item_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_knowledge_item_id ON memory_proposals(knowledge_item_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_page_id ON memory_proposals(page_id)"))


MIGRATIONS: list[Migration] = [
    ("001_create_analysis_jobs", _create_analysis_jobs),
    ("002_create_memory_and_task_tables", _create_memory_and_task_tables),
]
