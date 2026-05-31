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
                    target_store VARCHAR NOT NULL,
                    type VARCHAR NOT NULL,
                    title VARCHAR NOT NULL,
                    body TEXT NOT NULL,
                    structured_payload JSON NOT NULL,
                    scope VARCHAR NOT NULL,
                    evidence_refs JSON NOT NULL,
                    confidence FLOAT,
                    review_note TEXT NOT NULL,
                    status VARCHAR NOT NULL,
                    source_item_id VARCHAR,
                    knowledge_item_id VARCHAR,
                    page_id VARCHAR,
                    decision_ref VARCHAR,
                    created_at DATETIME NOT NULL,
                    resolved_at DATETIME
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_task_session_id ON memory_proposals(task_session_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_target_store ON memory_proposals(target_store)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_type ON memory_proposals(type)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_scope ON memory_proposals(scope)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_status ON memory_proposals(status)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_source_item_id ON memory_proposals(source_item_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_knowledge_item_id ON memory_proposals(knowledge_item_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_page_id ON memory_proposals(page_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_proposals_decision_ref ON memory_proposals(decision_ref)"))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS memory_decisions (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    decision_type VARCHAR NOT NULL,
                    target_ref VARCHAR NOT NULL,
                    actor VARCHAR NOT NULL,
                    reason TEXT NOT NULL,
                    policy VARCHAR NOT NULL,
                    evidence_refs JSON NOT NULL,
                    confidence FLOAT,
                    scope VARCHAR NOT NULL,
                    metadata JSON NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_decisions_decision_type ON memory_decisions(decision_type)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_decisions_target_ref ON memory_decisions(target_ref)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_decisions_actor ON memory_decisions(actor)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_decisions_scope ON memory_decisions(scope)"))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS provenance_events (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    event_type VARCHAR NOT NULL,
                    from_ref VARCHAR,
                    to_ref VARCHAR,
                    actor VARCHAR NOT NULL,
                    reason TEXT NOT NULL,
                    evidence_refs JSON NOT NULL,
                    payload JSON NOT NULL,
                    occurred_at DATETIME NOT NULL
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_provenance_events_event_type ON provenance_events(event_type)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_provenance_events_from_ref ON provenance_events(from_ref)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_provenance_events_to_ref ON provenance_events(to_ref)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_provenance_events_actor ON provenance_events(actor)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_provenance_events_occurred_at ON provenance_events(occurred_at)"))


def _create_profile_graph_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS entities (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    type VARCHAR NOT NULL,
                    name VARCHAR NOT NULL,
                    aliases JSON NOT NULL,
                    source_refs JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_entities_type ON entities(type)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_entities_name ON entities(name)"))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS memory_facts (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    subject_entity_id VARCHAR NOT NULL,
                    predicate VARCHAR NOT NULL,
                    object_value TEXT NOT NULL,
                    object_entity_id VARCHAR,
                    confidence FLOAT,
                    valid_at DATETIME NOT NULL,
                    invalid_at DATETIME,
                    superseded_by VARCHAR,
                    evidence_refs JSON NOT NULL,
                    status VARCHAR NOT NULL,
                    scope VARCHAR NOT NULL,
                    source_proposal_id VARCHAR,
                    decision_ref VARCHAR,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_facts_subject_entity_id ON memory_facts(subject_entity_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_facts_predicate ON memory_facts(predicate)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_facts_object_entity_id ON memory_facts(object_entity_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_facts_valid_at ON memory_facts(valid_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_facts_invalid_at ON memory_facts(invalid_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_facts_superseded_by ON memory_facts(superseded_by)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_facts_status ON memory_facts(status)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_facts_scope ON memory_facts(scope)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_facts_source_proposal_id ON memory_facts(source_proposal_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_facts_decision_ref ON memory_facts(decision_ref)"))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS memory_relations (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    from_entity_id VARCHAR NOT NULL,
                    relation_type VARCHAR NOT NULL,
                    to_entity_id VARCHAR NOT NULL,
                    confidence FLOAT,
                    valid_at DATETIME NOT NULL,
                    invalid_at DATETIME,
                    superseded_by VARCHAR,
                    evidence_refs JSON NOT NULL,
                    status VARCHAR NOT NULL,
                    scope VARCHAR NOT NULL,
                    source_proposal_id VARCHAR,
                    decision_ref VARCHAR,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_relations_from_entity_id ON memory_relations(from_entity_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_relations_relation_type ON memory_relations(relation_type)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_relations_to_entity_id ON memory_relations(to_entity_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_relations_valid_at ON memory_relations(valid_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_relations_invalid_at ON memory_relations(invalid_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_relations_superseded_by ON memory_relations(superseded_by)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_relations_status ON memory_relations(status)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_relations_scope ON memory_relations(scope)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_relations_source_proposal_id ON memory_relations(source_proposal_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_relations_decision_ref ON memory_relations(decision_ref)"))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS memory_conflicts (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    conflict_type VARCHAR NOT NULL,
                    fact_ids JSON NOT NULL,
                    relation_ids JSON NOT NULL,
                    reason TEXT NOT NULL,
                    status VARCHAR NOT NULL,
                    resolution TEXT NOT NULL,
                    scope VARCHAR NOT NULL,
                    decision_ref VARCHAR,
                    created_at DATETIME NOT NULL,
                    resolved_at DATETIME
                )
                """,
            ),
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_conflicts_conflict_type ON memory_conflicts(conflict_type)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_conflicts_status ON memory_conflicts(status)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_conflicts_scope ON memory_conflicts(scope)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memory_conflicts_decision_ref ON memory_conflicts(decision_ref)"))


def _create_task_digest_table(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_digests (
                    task_session_id VARCHAR NOT NULL PRIMARY KEY,
                    summary TEXT NOT NULL,
                    done JSON NOT NULL,
                    decisions JSON NOT NULL,
                    open_questions JSON NOT NULL,
                    risks JSON NOT NULL,
                    files_touched JSON NOT NULL,
                    source_refs JSON NOT NULL,
                    event_from_id VARCHAR,
                    event_to_id VARCHAR,
                    event_count INTEGER NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """,
            ),
        )


MIGRATIONS: list[Migration] = [
    ("001_create_analysis_jobs", _create_analysis_jobs),
    ("002_create_memory_and_task_tables", _create_memory_and_task_tables),
    ("003_create_profile_graph_tables", _create_profile_graph_tables),
    ("004_create_task_digest_table", _create_task_digest_table),
]
