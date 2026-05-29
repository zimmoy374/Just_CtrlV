# Memory Fabric Plan

This document is the direction-setting plan for upgrading Just Ctrl V into a second-brain memory kernel with pluggable memory strategies and stable external protocols.

The goal is not to force every memory into one database shape. The goal is to keep the protocol stable while allowing different memory stores to evolve, be replaced, or be optimized independently.

## North Star

Just Ctrl V should become a local-first second brain that preserves user-owned evidence, turns reviewed experience into durable memory, and gives future agents budgeted, citeable, task-aware context without letting any one model, index, graph, or agent runtime become the source of truth.

The durable promise is:

```text
If the app, model provider, search engine, graph backend, or agent client changes,
the user's original evidence, reviewed memories, task history, provenance, and exports still survive.
```

## Current Judgment

The current codebase is partially decoupled, but not yet a true memory fabric.

Already good:

- `SourceItem` preserves original evidence.
- `KnowledgeItem` and `KnowledgePage` separate formal knowledge from capture cards.
- `TaskSession`, `TaskEvent`, checkpoints, and `HandoffPack` create working memory for agent continuation.
- `MemoryProposal` creates a review gate before long-term memory writes.
- Accepted `MemoryProposal` records now route through `MemoryRouter.accept_proposal` into `semantic_knowledge`, `rule_preference`, or `procedure_lesson`.
- `MemoryDecision` and `ProvenanceEvent` provide a first durable proposal decision/provenance ledger.
- `ContextPack` already avoids full-library dumps.
- `MemoryRef`, `MemorySlice`, `MemoryStore`, `MemoryRouter`, `SemanticKnowledgeStore`, and `TaskMemoryStore` establish the first protocol skeleton.
- `RetrievalEngine` is beginning to hide the underlying index.
- Export already includes knowledge, sources, task capsules, memory proposals, memory decisions, handoff packs, and provenance.

Still missing:

- Rule/preference and procedure/lesson stores still start as typed `KnowledgeItem` projections rather than independent durable stores.
- There is no explicit `Entity`, `MemoryFact`, `MemoryRelation`, temporal validity window, or supersession model.
- Context composition mostly reads semantic knowledge and pages, not a blend of profile facts, rules, task state, and source excerpts.
- The stable `MemoryStore` interface is present, but only the first read-only stores are implemented.
- Meta-memory currently covers proposal creation/routing/acceptance/dismissal, not supersession, invalidation, conflict, or context exposure.
- Privacy, visibility, and capability boundaries are implied by budgeted context, but not yet represented as first-class memory protocol fields.
- Provenance is durable for proposal lifecycle events, but not yet hash-linked or extended across every future memory lifecycle.

The next architecture move is therefore not "add Graphiti" or "add vectors". It is to make the Context Composer truly compose protocol `MemorySlice` results from multiple stores, while preserving budget, citation, scope, and privacy boundaries.

## Core Principles

1. Evidence is the root asset.
   Every durable memory should be traceable back to a `SourceItem`, `TaskEvent`, external import, file reference, or explicit user decision.

2. Memories have different shapes.
   A screenshot, a long note, a user preference, a project fact, a task checkpoint, and a workflow lesson should not be forced into one record model.

3. Stores are replaceable, envelopes are stable.
   Internal stores can change. External inputs and outputs should remain stable through shared envelopes such as `MemoryEpisodeInput`, `MemoryProposal`, `MemorySlice`, and `ContextPack`.

4. Agent writes are never silent long-term writes.
   Agents may append task events, create checkpoints, and propose memories. User-confirmed or policy-approved review is required before writing durable long-term memory.

5. Derived indexes are disposable.
   FTS, vectors, graph projections, rerankers, and caches can be rebuilt from durable stores. They are not the memory source of truth.

6. Temporal memory should preserve history.
   User profile facts and project-state facts should support `valid_at`, `invalid_at`, and `superseded_by`. Old facts should be invalidated, not deleted, unless the user explicitly purges them.

7. Context is composed, not dumped.
   Agents receive a budgeted context pack assembled from relevant stores. Normal agent workflows should never require reading the full library.

8. Meta-memory is part of memory.
   The system should remember why a durable memory exists, who or what proposed it, what evidence supported it, what policy allowed it, and why it was later accepted, rejected, invalidated, or superseded.

9. Provenance should be append-only, but user trust is not decentralized.
   Borrow ledger ideas such as append-only events, hashable exports, and tamper-evident provenance. Do not make agents co-own truth through blockchain-style consensus. The user remains the trust root.

10. Privacy and scope must travel with memory.
    Every memory-like object should eventually carry scope, visibility, privacy labels, and capability requirements so agents receive only the context they are allowed to use.

11. Conflicts are first-class outcomes.
    Conflicting memories should not be silently merged or overwritten. They should become reviewable conflicts, supersessions, invalidations, or scoped alternatives.

12. Different memory layers need different consistency guarantees.
    Source evidence and review decisions need strong durability. Retrieval projections can be eventually consistent and rebuildable. Task handoff can be stale, but must say so.

## Target Architecture

```text
Capture / Import / Agent Event
  -> Source Vault
  -> Extraction and Normalization
  -> Memory Proposal Inbox
  -> Human Review / Policy Gate
  -> Memory Router
  -> Pluggable Memory Stores
  -> Retrieval Projections
  -> Context Composer
  -> Agent Protocol / UI / Export
```

The stable center is the protocol layer:

```text
MemoryEpisodeInput
MemoryProposal
MemoryRef
MemoryDecisionRecord
ProvenanceEvent
MemorySlice
ContextPack
ExportBundle
```

The replaceable parts are:

```text
extraction model
embedding provider
FTS/vector/graph/reranker provider
temporal graph backend
agent client
MCP implementation
frontend presentation
```

## Memory Store Catalog

### Source Vault

Purpose:

- Preserve original evidence and episodes.
- Store text, image references, links, external AI selections, task events, and agent-visible observations.

Current mapping:

- `SourceItem`
- `TaskEvent` when the source is an active task episode

Durability:

- Durable and exportable.
- Should survive AI failure.
- Should remain readable even if every derived store is rebuilt.

Not for:

- Ranking.
- User-facing polished knowledge.
- Long-term user profile conclusions without review.

### Semantic Knowledge Store

Purpose:

- Store human-readable atomic knowledge and topic pages.
- Support ordinary search, review, reading, and organization.

Current mapping:

- `KnowledgeItem`
- `KnowledgePage`
- `KnowledgePageItemLink`

Best for:

- Notes.
- Extracted insights.
- Topic summaries.
- Project briefs.
- User-confirmed knowledge fragments.

Not for:

- Rapidly changing profile facts.
- Full task event history.
- Raw source dumps.

### Profile Temporal Graph Store

Purpose:

- Store user profile, preferences, entities, relationships, and changing facts as a temporal context graph.

Inspired by:

- Graphiti-style temporal context graph: entities, fact/relationship edges, source episodes, validity windows, and supersession without deleting old facts.

Future records:

```text
Entity
  id
  type
  name
  aliases
  source_refs
  created_at
  updated_at

MemoryFact
  id
  subject_entity_id
  predicate
  object_value or object_entity_id
  confidence
  valid_at
  invalid_at
  superseded_by
  evidence_refs
  status

MemoryRelation
  id
  from_entity_id
  relation_type
  to_entity_id
  confidence
  valid_at
  invalid_at
  superseded_by
  evidence_refs
  status

MemoryConflict
  id
  fact_ids
  reason
  status
  resolution
```

Best for:

- "User prefers X."
- "User is working on project Y."
- "Project A uses tool B."
- "This preference replaced an older preference."
- "This fact is true only for a period or scope."

Not for:

- Long documents.
- Screenshot bodies.
- Complete task logs.
- Wiki pages.

### Task Memory Store

Purpose:

- Preserve current work state, event history, checkpoints, and agent handoff context.

Current mapping:

- `TaskSession`
- `TaskEvent`
- `TaskState`
- `TaskCheckpoint`
- `HandoffPack`

Best for:

- Active task continuation.
- Cross-agent handoff.
- Checkpointing.
- Recovering what happened during a piece of work.

Not for:

- Long-term user identity.
- Automatically promoted lessons.
- Default knowledge search unless explicitly requested.

### Rule And Preference Store

Purpose:

- Store stable behavioral rules, product constraints, and strong user preferences that should influence agents.

Possible implementation:

- Can start as a typed subset of `MemoryProposal` accepted into `KnowledgeItem`.
- Later can become its own store with priority, scope, and conflict handling.

Best for:

- "Do not mark a task complete without user close."
- "Prefer local verification commands over launching browser tests unless needed."
- "Do not add built-in chat."

Special behavior:

- Rules should be small, high-priority, and scoped.
- Rules should be included earlier in ContextPack than ordinary notes.

### Procedure And Lesson Store

Purpose:

- Store reusable workflows, pitfalls, project-specific lessons, and technical decisions.

Best for:

- "When refactoring the memory architecture, update the architecture doc before code."
- "For export changes, verify manifest, jsonl, and provenance together."

Possible implementation:

- Can initially remain as typed `KnowledgeItem` entries.
- Later can become structured procedures with steps, prerequisites, checks, and evidence.

### Meta Memory And Decision Store

Purpose:

- Preserve why a memory exists and how its status changed.
- Record proposal, review, acceptance, dismissal, conflict resolution, supersession, invalidation, exposure, and export decisions.
- Provide audit evidence for future agents and future user review.

Future records:

```text
MemoryDecisionRecord
  id
  decision_type
  target_ref
  actor
  reason
  policy
  evidence_refs
  confidence
  created_at
  metadata

ProvenanceEvent
  id
  event_type
  from_ref
  to_ref
  actor
  reason
  occurred_at
  hash
  previous_hash
```

Best for:

- "This profile fact was accepted because the user confirmed it."
- "This rule was rejected because it was too broad."
- "This fact superseded another fact after a newer task event."
- "This ContextPack exposed these refs to this agent for this task."

Not for:

- Large source bodies.
- Ordinary user-facing notes.
- Ranking-only data.

### Privacy And Access Policy Layer

Purpose:

- Decide which memories an agent, task, export, or external tool may see.
- Keep sensitive memories from leaking through broad ContextPacks.
- Preserve user control over private evidence and long-term profile data.

Future fields on protocol envelopes:

```text
scope
visibility
privacy_labels
capability_requirements
redaction_policy
retention_policy
```

Visibility examples:

```text
private
task
project
workspace
external_agent_allowed
export_allowed
```

Rule:

- Context composition must filter by scope and capability before ranking.
- Redaction should happen before a memory slice is exposed, not after the agent has seen it.

### Retrieval Projection Store

Purpose:

- Provide fast retrieval over durable stores.

Possible projections:

- SQLite FTS.
- Vector index.
- Graph traversal index.
- Hybrid search.
- Reranker cache.

Rule:

- This store can always be deleted and rebuilt.
- It must not be the only place a memory exists.

## Stable Protocol Envelopes

### MemoryRef

Every object exposed to an agent should have a stable ref.

```text
source:{source_item_id}
item:{knowledge_item_id}
page:{knowledge_page_id}
task:{task_session_id}
task-event:{task_event_id}
checkpoint:{task_checkpoint_id}
handoff:{handoff_pack_id}
entity:{entity_id}
fact:{memory_fact_id}
relation:{memory_relation_id}
proposal:{memory_proposal_id}
decision:{memory_decision_id}
provenance:{provenance_event_id}
```

### MemoryEpisodeInput

Used when anything enters the memory system.

```text
id
source
source_ref
actor
occurred_at
kind
title
content_text
content_html
media_refs
metadata
scope
visibility
privacy_labels
retention_policy
```

Examples:

- User pastes a note.
- User imports a selection from another AI tool.
- An agent records a task event.
- A task close reflection produces review candidates.

### MemoryProposal

Used for candidate writes into long-term memory.

```text
id
target_store
proposal_type
title
body
structured_payload
scope
evidence_refs
confidence
status
review_note
created_by
decision_ref
privacy_labels
created_at
resolved_at
```

`target_store` examples:

```text
semantic_knowledge
profile_temporal_graph
task_memory
rule_preference
procedure_lesson
```

`proposal_type` examples:

```text
lesson
pitfall
user_preference
project_rule
workflow_pattern
technical_decision
environment_fact
profile_fact
entity_relation
page_update
privacy_change
conflict_resolution
memory_invalidation
```

### MemoryDecisionRecord

Used to preserve meta-memory: the reason a memory was kept, rejected, exposed, superseded, or invalidated.

```text
id
decision_type
target_ref
actor
reason
policy
evidence_refs
confidence
scope
created_at
metadata
```

`decision_type` examples:

```text
proposal_created
proposal_accepted
proposal_dismissed
fact_superseded
fact_invalidated
conflict_opened
conflict_resolved
context_exposed
privacy_changed
exported
```

### ProvenanceEvent

Used for append-only audit history. This is not a blockchain consensus layer; it is a local-first, user-owned provenance ledger that can be exported and optionally hash-linked.

```text
id
event_type
from_ref
to_ref
actor
reason
occurred_at
payload
hash
previous_hash
```

### MemorySlice

Used when any store returns context to the composer.

```text
store
kind
ref
title
summary
excerpt
score
reason
scope
valid_at
invalid_at
evidence_refs
citation_ref
decision_ref
visibility
privacy_labels
staleness
conflict_refs
metadata
```

The Context Composer should not care whether a result came from FTS, a graph, a task state, or a rules store. It should only compose `MemorySlice` objects.

### MemoryStore Interface

Each store should eventually implement the same conceptual interface.

```text
ingest_episode(input) -> refs
propose(input) -> MemoryProposal[]
accept_proposal(proposal) -> refs
dismiss_proposal(proposal) -> proposal
retrieve(query, scope, budget) -> MemorySlice[]
get(ref) -> record
record_decision(decision) -> ref
export() -> files or jsonl records
rebuild_projection() -> report
```

Not every store needs every method on day one, but the architecture should point toward this contract.

## Write Lifecycle

```text
Input arrives
  -> store original episode in Source Vault
  -> normalize metadata and scope
  -> run optional extraction
  -> create MemoryProposal records
  -> user reviews proposals
  -> write MemoryDecisionRecord and ProvenanceEvent
  -> MemoryRouter dispatches accepted proposals to target store
  -> target store writes durable memory
  -> conflicts, invalidations, or supersessions are recorded without deleting history
  -> retrieval projections update or mark rebuild needed
  -> export/provenance can explain the full path
```

Important rule:

```text
Source Vault write can be automatic.
Long-term memory write requires review or an explicit trusted policy.
```

## Read Lifecycle

```text
Agent or UI asks a question
  -> classify intent and scope
  -> check visibility and capability policy
  -> query relevant stores
  -> stores return MemorySlice objects
  -> Context Composer filters, redacts, deduplicates, ranks, budgets, and cites
  -> caller receives ContextPack
  -> caller can request specific source excerpts only when needed
```

Default read order:

```text
protocol reminders
active task state if task-scoped
high-priority rules and preferences
profile temporal facts if relevant
open conflict warnings if relevant
semantic pages and items
source excerpts only when needed
```

## ContextPack Evolution

Current ContextPack should evolve from:

```text
pages + items + source excerpts
```

to:

```text
protocolReminder
taskState
rules
profileFacts
conflicts
relatedPages
relatedItems
procedureLessons
sourceExcerpts
budget
citationRefs
decisionRefs
```

This preserves the current external idea while allowing new stores to participate.

The composer should enforce:

- maximum characters
- maximum items per store
- no full-library dumps by default
- citation refs for every factual claim
- decision refs for reviewed long-term memories when available
- visibility and capability filtering before ranking
- redaction before exposure
- conflict warnings when active facts disagree
- stale or invalid temporal facts excluded unless requested
- superseded facts shown only when history is relevant

## Conflict Lifecycle

Conflicts are expected in multi-agent memory. They can come from stale task state, ambiguous user preferences, project-specific rules, or agents extracting different conclusions from the same evidence.

```text
New proposal or fact arrives
  -> identify comparable facts by subject, predicate, scope, and time window
  -> if consistent, link evidence and keep both if useful
  -> if newer fact clearly replaces older fact, set invalid_at and superseded_by
  -> if contradiction cannot be resolved, create MemoryConflict
  -> expose conflict warning in ContextPack when relevant
  -> user or policy resolves conflict
  -> write decision/provenance events
```

Rules:

- Never silently overwrite a durable fact.
- Never hide a known active conflict from an agent that is about to rely on that memory.
- Conflicts can be scoped. "Use React for project A" and "Use Vue for project B" are not conflicts if their scopes are different.
- Supersession preserves history. Deletion is reserved for explicit user purge or retention policy.

## Privacy And Capability Lifecycle

Shared memory does not mean universally shared memory. Agent access should be explicit, scoped, and auditable.

```text
Caller asks for context
  -> identify caller, task, scope, and requested operation
  -> apply namespace and visibility filters
  -> apply capability requirements
  -> redact sensitive fields if a lower-trust context is still allowed
  -> record exposure decision when durable memory is shared
```

Rules:

- Private user evidence is not included in external-agent context unless explicitly allowed.
- Task-scoped memories should not leak into unrelated tasks by default.
- Profile facts should be treated as sensitive by default.
- Exports should preserve privacy labels so another tool does not flatten all memories into public notes.
- User purge should remove or cryptographically sever sensitive source content, while keeping minimal tombstone provenance when needed.

## Consistency And Availability Policy

There is no silver bullet memory store. Each memory layer has different durability and consistency needs.

```text
Source Vault
  strong durability; append first; survives AI failure

MemoryProposal and decisions
  strong consistency around review state; no double acceptance into conflicting stores

TaskState and HandoffPack
  can become stale; must carry freshness and checked_at

Profile temporal facts and rules
  conflict-aware consistency; never silent overwrite

Retrieval projections
  eventually consistent; rebuildable from durable stores

ContextPack
  budgeted snapshot; cite refs; include freshness/conflict/privacy signals
```

Engineering stance:

- Prefer correctness and auditability for durable memory writes.
- Prefer availability for read-only context, but label stale or partial results.
- Treat indexes, embeddings, graph projections, and reranker caches as disposable.
- Do not let a convenient projection become the source of truth.

## Agent Protocol Rules

Agents may:

- Read budgeted ContextPacks.
- Ask for source excerpts by ref.
- Append TaskEvents.
- Update TaskState through controlled fields.
- Create checkpoints.
- Create HandoffPacks.
- Create MemoryProposals.
- Ask for active task lists.

Agents may not:

- Directly write reviewed long-term memory.
- Rewrite KnowledgePage bodies without a reviewed proposal.
- Mark a task complete without explicit user close.
- Request full-library dumps for ordinary questions.
- Delete historical evidence.
- Hide low-confidence or conflicting facts.
- Bypass visibility, privacy, or capability filters.
- Resolve conflicts without a user decision or explicit trusted policy.

## Export And Migration Requirements

Every durable store must answer:

```text
Where did this come from?
Who or what proposed it?
Did the user confirm it?
What source, task, or episode supports it?
What decision caused it to be kept, rejected, invalidated, or exposed?
Is it active, superseded, invalidated, archived, rejected, or stale?
What visibility, privacy labels, and retention policy apply?
Can another tool import it without understanding our UI?
```

Future export bundle should include:

```text
manifest.json
index.md
wiki/*.md
items.jsonl
sources/
task_sessions.jsonl
task_events.jsonl
task_checkpoints.jsonl
handoff_packs/
memory_proposals.jsonl
entities.jsonl
facts.jsonl
relations.jsonl
conflicts.jsonl
rules.jsonl
procedures.jsonl
memory_decisions.jsonl
provenance.jsonl
agent-instructions/
```

## First-Version Model Mapping

First-version records map directly into the Memory Fabric stores.

```text
SourceItem
  -> Source Vault episode/source record

KnowledgeItem
  -> SemanticKnowledgeStore item

KnowledgePage
  -> SemanticKnowledgeStore page

Reflection
  -> organization proposal or page-update proposal

MemoryProposal
  -> generalized proposal envelope with target_store and structured_payload

MemoryDecisionRecord / ProvenanceEvent
  -> meta-memory and append-only provenance ledger

TaskSession / TaskEvent / TaskState / TaskCheckpoint / HandoffPack
  -> TaskMemoryStore

RetrievalEngine / SqliteFtsIndex
  -> RetrievalProjectionStore behind a provider interface
```

Build the first version directly on these stores and protocol envelopes; do not add duplicate paths for hypothetical earlier product shapes.

## Implementation Roadmap

### Stage 0: Direction Document

Goal:

- Establish this plan as the durable direction before code changes.

Expected output:

- This document.

Verification:

- The team can answer where a new memory type belongs before implementing it.
- The team can answer why a memory should exist, who can see it, and how conflicts are resolved.

### Stage 1: First-Version Protocol Skeleton

Goal:

- Introduce shared protocol types, stores, router, and composer as the first-version architecture.

Likely files:

```text
server/app/memory_core/
server/app/memory_core/protocol.py
server/app/memory_core/router.py
server/app/memory_core/stores.py
server/app/memory_core/composer.py
```

Work:

- Define `MemoryRef`, `MemoryEpisodeInput`, `MemorySlice`, and store interface.
- Include optional protocol fields for scope, visibility, evidence refs, decision refs, staleness, and conflict refs.
- Implement `SemanticKnowledgeStore` over `KnowledgeItem/Page` retrieval.
- Implement `TaskMemoryStore` over task capsule records.
- Route `/api/knowledge/context` through `MemoryContextComposer`.

Verification:

- Tests pass.
- Knowledge search and context endpoints satisfy the first-version contract.

### Stage 2: Generalized Proposal Routing

Goal:

- Make `MemoryProposal` route accepted proposals into different stores.

Work:

- Add `target_store`, `structured_payload`, `scope`, `confidence`, and `review_note`.
- Start recording decision/provenance records for proposal acceptance, dismissal, and routing.
- Replace direct accept-to-KnowledgeItem logic with `MemoryRouter.accept_proposal`.
- Start with routes for:
  - `semantic_knowledge`
  - `rule_preference`
  - `procedure_lesson`

Verification:

- Accepted semantic proposals still appear in search.
- Dismissed proposals never enter any store.
- Proposal provenance remains exportable.
- Accepted and dismissed proposals have decision records explaining why.

Status:

- Implemented in the first version. Proposal routing now goes through `MemoryRouter.accept_proposal`; proposal decisions and provenance are durable and exportable; the review inbox displays routing/review fields.

### Stage 3: Context Composer

Goal:

- Make ContextPack a composition of `MemorySlice` results from multiple stores.

Work:

- Query stores by intent and scope.
- Filter by visibility and caller capability before ranking.
- Deduplicate by evidence refs and semantic similarity.
- Budget results by priority:
  - protocol
  - task state
  - rules
  - profile facts
  - conflict warnings
  - pages/items
  - source excerpts
- Preserve current API parameters and add optional store controls later.

Verification:

- ContextPack remains budgeted.
- No full source text appears by default.
- Each returned fact has citation refs.
- Sensitive slices are filtered or redacted before exposure.
- Active conflicts relevant to the query are surfaced.

### Stage 4: Profile Temporal Graph Store

Goal:

- Add temporal user-profile memory without overloading `KnowledgeItem`.

Work:

- Add `Entity`, `MemoryFact`, `MemoryRelation`, and `MemoryConflict`.
- Add validity fields:
  - `valid_at`
  - `invalid_at`
  - `superseded_by`
  - `confidence`
  - `evidence_refs`
- Add proposal types:
  - `profile_fact`
  - `entity_relation`
  - `fact_supersession`
- Keep the first implementation local and simple.
- Do not adopt an external graph engine until the protocol is stable.
- Record conflict openings, supersessions, invalidations, and resolutions as decisions/provenance.

Verification:

- New profile fact can be accepted and retrieved.
- New contradictory fact invalidates or conflicts with the old fact without deleting it.
- Export includes entities, facts, relations, and provenance.
- Context excludes invalid facts by default and warns about unresolved conflicts.

### Stage 5: Export And Rebuild Guarantees

Goal:

- Make every store exportable and every projection rebuildable.

Work:

- Add export files for graph/profile/rules/procedures.
- Add provenance links for accepted proposals and superseded facts.
- Add `memory_decisions.jsonl` and hash-linkable provenance records.
- Add rebuild command or service for retrieval projections.

Verification:

- Deleting derived indexes and rebuilding preserves search/context behavior.
- Export can be inspected without running the app.
- Export can explain why each durable memory exists and who can see it.

### Stage 6: Agent Protocol And MCP

Goal:

- Let external agents use memory through stable tools instead of reading internal tables.

Tools:

```text
get_context_pack
get_source_excerpt
list_active_tasks
record_task_event
update_task_state
create_checkpoint
get_handoff_pack
propose_memory
list_memory_proposals
```

Verification:

- Tools cannot silently write long-term memory.
- Tools return refs and citations instead of full-library dumps.
- Handoff remains stale-aware.
- Tools respect visibility, scope, and capability filters.
- Tools can report conflicts instead of pretending one answer is canonical.

### Stage 7: Review Workbench UI

Goal:

- Give the user a clear surface for accepting, editing, routing, superseding, or rejecting memories.

Views:

```text
Memory Proposal Inbox
Profile Facts
Conflicts
Rules
Procedures
Task Capsule
Knowledge Pages
Source Evidence
```

Verification:

- User can see why a memory exists.
- User can invalidate or supersede a profile fact.
- User can inspect and resolve conflicts.
- User can adjust visibility/privacy labels.
- User can export before leaving the product.

## Design Tests For Future Features

Before adding any memory feature, answer:

1. What durable store owns this memory?
2. What evidence ref supports it?
3. Can an agent write it directly, or only propose it?
4. Is it a fact, rule, procedure, task state, note, page, source, or derived index?
5. Can it become stale, invalid, superseded, or archived?
6. Can it be exported and understood by another tool?
7. Can the retrieval/index implementation be replaced without changing the memory record?
8. Why should this memory be retained instead of staying as short-term context?
9. Who or what is allowed to read it?
10. What happens if another agent later contradicts it?
11. What consistency guarantee does this layer need?

If a feature cannot answer these questions, it is probably a UI experiment or derived projection, not a core memory feature.

## Immediate Next Steps

1. Keep this document as the architecture source for memory evolution.
2. Keep a short "read this first" pointer to this plan.
3. Implement Stage 3 before adding new graph tables.
4. Keep rule/preference and procedure/lesson as typed `KnowledgeItem` projections until composer behavior proves the store boundary.
5. Treat Graphiti as a strong reference model, not as the first dependency to install.
6. Use composer filtering to exercise scope, visibility, privacy, and capability fields before exposing new agent read paths.
7. Use append-only provenance as an audit ledger, not as a decentralized agent consensus chain.

## Summary

The target architecture is a memory fabric:

```text
many stores, one protocol
many retrieval strategies, one ContextPack contract
many agent clients, one reviewed write path
many future implementations, one user-owned evidence base
many memory decisions, one auditable provenance ledger
```

This is how Just Ctrl V can keep improving as agents and models improve, without requiring a global rewrite every time a better memory strategy appears.
