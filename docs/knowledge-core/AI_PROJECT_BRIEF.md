# Just Ctrl V AI Project Brief

This file is the first document an AI coding assistant should read before changing this project.

For the longer-term plan to make Just Ctrl V a future-agent-compatible personal memory substrate with task handoff, working memory, long-term memory promotion, agent protocols, and export/migration guarantees, also read `docs/knowledge-core/AGENT_MEMORY_HANDOFF_PLAN.md`.

## Product Purpose

Just Ctrl V is a local personal knowledge tool. Its job is to let the user paste or save text, images, and links, preserve the original source, organize confirmed knowledge, search it, export it, and provide budgeted context packs to external AI tools.

It is not a built-in chat product. Do not add a chat panel or a chat API.

## Current Core Model

`Card`
: UI capture object. Cards support the board experience: text, image, link, week position, size, summary, keywords, and AI status. A card is not the core knowledge asset.

`SourceItem`
: Original material. It preserves user text, link content, image reference, external AI selected text, source system, external ID, metadata, status, and timestamps. SourceItem must be saved even when AI analysis fails.

`KnowledgeItem`
: Formal atomic knowledge. It is created only after AI analysis succeeds, user edits confirm the knowledge fields, or external AI sends a user-confirmed import. Only active KnowledgeItem records are searchable by default.

`KnowledgePage`
: Long-lived topic page compiled from related KnowledgeItems. Suggestions can create or update pages, but the system should not secretly rewrite important page content without user action.

`KnowledgePageItemLink`
: Relationship between a KnowledgePage and its KnowledgeItems.

`Reflection`
: User-facing organization suggestion. It stores pending, accepted, and dismissed suggestions such as "these items share a topic".

`AnalysisJob`
: Durable AI analysis work item for a Card. It stores pending, running, succeeded, failed, and canceled execution state so analysis can be retried or resumed after process interruption.

`knowledge_search_fts`
: SQLite FTS derived index. It can be rebuilt. It is not a knowledge asset.

## Main Backend Paths

`server/app/main.py`
: FastAPI app, CORS, static uploads, router registration, database initialization, and startup recovery for interrupted analysis jobs.

`server/app/models.py`
: SQLModel database models. Keep this file limited to persistence structure.

`server/app/migrations.py`
: Lightweight schema migration runner. Add forward-only migrations here when persistence structure changes.

`server/app/routes/cards.py`
: Capture API. Handles card create, update, retry analysis, delete, and card listing.

`server/app/routes/knowledge.py`
: Knowledge protocol API. Handles knowledge search, external confirmed import, context packs, knowledge pages, export, and reflection actions.

`server/app/capture/cards_service.py`
: Adapts Card objects into SourceItem and KnowledgeItem records.

`server/app/analysis/jobs.py`
: Durable analysis job orchestration. Routes enqueue work here; this module owns running and recovering AI analysis jobs.

`server/app/knowledge_core/source_items.py`
: SourceItem validation and upsert.

`server/app/knowledge_core/knowledge_items.py`
: KnowledgeItem validation, upsert, and archive.

`server/app/knowledge_core/lifecycle.py`
: Orchestrates KnowledgeItem commits. This is where KnowledgeItem persistence triggers index refresh and suggestion generation.

`server/app/indexing/sqlite_fts.py`
: SQLite FTS implementation for KnowledgeItem search.

`server/app/retrieval/engine.py`
: RetrievalEngine. Routes and UI should use this instead of touching FTS directly.

`server/app/organization/suggestions.py`
: Suggestion generation, accept, and dismiss logic.

`server/app/wiki/pages.py`
: KnowledgePage upsert and item linking.

`server/app/context/packs.py`
: ContextPack generation for external AI. It must stay budgeted and must not return the whole library.

`server/app/export/bundle.py`
: Export bundle generation: manifest, index, wiki pages, items JSONL, sources, and provenance.

`server/app/ai.py`
: OpenAI-compatible card analysis provider. AI is a replaceable analysis capability, not the system controller.

## Main Frontend Paths

`client/src/App.tsx`
: Thin composition layer for board, knowledge workspace, topbar, overlays, and notifications.

`client/src/hooks/useBoardController.ts`
: Board workflow controller for week loading, paste capture, card movement, retry/delete, canvas pan/zoom, and image preview state.

`client/src/hooks/useKnowledgeWorkspace.ts`
: Knowledge workspace controller for search, graph loading, reflections, and cross-view state.

`client/src/pages/BoardPage.tsx`
: Capture board UI.

`client/src/pages/SearchPage.tsx`
: Knowledge search page.

`client/src/pages/KnowledgeMapPage.tsx`
: Knowledge graph and KnowledgePage summary list.

`client/src/components/suggestions-panel.tsx`
: Suggestion panel wrapper.

`client/src/lib/api/*`
: Split frontend API clients. Do not recreate a single API barrel.

`client/src/types/*`
: Split frontend domain types. Do not recreate a single type barrel.

## Current Public API

Capture:

```text
GET    /api/weeks/{week_key}/cards
POST   /api/cards/text
POST   /api/cards/link
POST   /api/cards/image
PATCH  /api/cards/{card_id}
POST   /api/cards/{card_id}/analyze
DELETE /api/cards/{card_id}
```

Knowledge:

```text
GET  /api/knowledge/search?q=...
POST /api/knowledge/import-confirmed
GET  /api/knowledge/context?q=...
GET  /api/knowledge/pages
POST /api/knowledge/export
GET  /api/reflections
POST /api/reflections/{reflection_id}/accept
POST /api/reflections/{reflection_id}/dismiss
GET  /api/graph
```

## Required Lifecycle Rules

When the user creates a card:

```text
Card is saved.
SourceItem is saved immediately.
AnalysisJob(pending) is saved.
AI analysis is queued through the durable job runner.
```

When AI analysis fails or config is missing:

```text
Card.ai_status = failed.
SourceItem remains active.
No KnowledgeItem is created.
Nothing becomes searchable.
AnalysisJob is marked failed.
```

When AI analysis succeeds:

```text
Card gets summary and keywords.
KnowledgeItem(active) is created or updated.
knowledge_search_fts is refreshed.
Reflection suggestions may be generated.
AnalysisJob is marked succeeded.
```

When the app starts:

```text
Interrupted AnalysisJob records in pending or running state are recovered.
Running jobs are reset to pending and executed again.
Missing-card jobs are canceled.
```

When a card is deleted:

```text
Card is deleted.
Image file is deleted if present.
Linked KnowledgeItem is archived if it exists.
SourceItem remains available for traceability.
```

When external AI writes back:

```text
Only user-confirmed content may call /api/knowledge/import-confirmed.
The selected original text becomes SourceItem.
The confirmed title, summary, body, and keywords become KnowledgeItem(active).
Proposed pages create Reflection suggestions only.
```

Search:

```text
Search only formal active KnowledgeItems.
Routes call RetrievalEngine.
RetrievalEngine calls an index provider such as SqliteFtsIndex.
Routes must not query FTS tables directly.
Knowledge graph should be based on formal KnowledgeItems and KnowledgePages; Cards are only optional source navigation targets.
```

ContextPack:

```text
Return protocol reminders, related KnowledgePages, related KnowledgeItems, optional SourceItem excerpts, budget usage, truncation, and citation refs.
Do not return the whole library for normal queries.
Do not include full SourceItem text by default.
```

Export:

```text
Generate manifest.json, index.md, wiki/*.md, items.jsonl, sources/, provenance.jsonl.
Markdown frontmatter must preserve ids, status, updatedAt, sourceRefs, and itemRefs.
```

## Design Boundaries

Do not restore old compatibility APIs or single-file frontend barrels.

Do not add built-in chat.

Do not put FTS logic in routes or knowledge asset modules.

Do not create KnowledgeItem records from failed analysis.

Do not let public card patch requests directly write ai_status or ai_error.

Do not make SourceItem searchable by default.

Do not auto-rewrite KnowledgePage body without a suggestion or user action.

Do not treat the card board as the core knowledge model. It is a capture UI.

## Safe Places To Modify By Task

Search ranking or recall:

```text
server/app/retrieval/engine.py
server/app/indexing/sqlite_fts.py
server/tests/test_cards.py
```

Card capture behavior:

```text
server/app/routes/cards.py
server/app/capture/cards_service.py
server/app/analysis/jobs.py
client/src/pages/BoardPage.tsx
client/src/hooks/useBoardController.ts
client/src/lib/api/cards.ts
```

Knowledge lifecycle:

```text
server/app/knowledge_core/source_items.py
server/app/knowledge_core/knowledge_items.py
server/app/knowledge_core/lifecycle.py
server/app/analysis/jobs.py
```

Organization suggestions:

```text
server/app/organization/suggestions.py
server/app/wiki/pages.py
client/src/components/suggestions-panel.tsx
client/src/hooks/useKnowledgeWorkspace.ts
```

External AI access:

```text
server/app/context/packs.py
server/app/routes/knowledge.py
client/src/lib/api/context.ts
```

Export:

```text
server/app/export/bundle.py
server/tests/test_cards.py
```

## Verification Commands

Run these before finishing meaningful changes:

```powershell
python -m pytest -q
cd client
npm run lint
npm run build
```

Also scan for forbidden regressions: no built-in chat surface, no removed write/search endpoints, no retired model names, and no single-file frontend API/type barrels should reappear.
