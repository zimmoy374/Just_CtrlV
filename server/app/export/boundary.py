from __future__ import annotations


EXPORT_VERSION = "0.2"

DURABLE_EXPORT_CONTENTS = {
    "index": "index.md",
    "wiki": "wiki/",
    "pages": "pages.jsonl",
    "pageItemLinks": "page_item_links.jsonl",
    "items": "items.jsonl",
    "rules": "rules.jsonl",
    "procedures": "procedures.jsonl",
    "sources": "sources/",
    "taskSessions": "task_sessions.jsonl",
    "taskEvents": "task_events.jsonl",
    "taskCheckpoints": "task_checkpoints.jsonl",
    "taskDigests": "task_digests.jsonl",
    "memoryProposals": "memory_proposals.jsonl",
    "memoryDecisions": "memory_decisions.jsonl",
    "entities": "entities.jsonl",
    "facts": "facts.jsonl",
    "relations": "relations.jsonl",
    "conflicts": "conflicts.jsonl",
    "handoffPacks": "handoff_packs/",
    "provenance": "provenance.jsonl",
}

DERIVED_PROJECTIONS = [
    {
        "name": "knowledge_search_fts",
        "owner": "retrieval_projection",
        "sourceStores": ["knowledge_items"],
        "exported": False,
        "rebuild": "MemoryRouter.rebuild_projections",
    },
]
