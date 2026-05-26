# Agent Memory And Handoff Plan

This document defines a practical plan for turning Just Ctrl V from a personal knowledge base into a local-first memory substrate for agents.

The goal is not to build another chat product. The goal is to let different agents understand the user, continue task work without full re-explanation, and distill completed work into long-term knowledge.

## 1. Feasibility Judgment

This is feasible, but only if the system is honest about what can and cannot be captured.

What can be captured reliably:

- User-stated task goals, constraints, preferences, and corrections.
- Agent-visible events: decisions, summaries, tool outputs, file references, errors, test results, and checkpoints.
- User actions in our app: start task, pause task, request handoff, close task, promote memory, archive task.
- Agent-written structured updates through an API, MCP tool, CLI command, or pasted handoff text.
- Durable source references: cards, source items, task events, knowledge items, files, exports.

What cannot be captured reliably:

- A model's hidden reasoning state.
- A third-party agent's private internal scratchpad unless the agent explicitly writes a summary/event.
- Whether a task is truly complete in the user's mind without user or external system confirmation.
- Whether old task context is still relevant unless freshness, status, and scope are tracked.

Therefore, the design must be based on explicit task state, append-only events, checkpoints, and user-controlled closure. Automatic inference can suggest state changes, but must not silently mark work complete or promote short-term content into long-term memory.

## 2. External Patterns To Borrow

LangGraph's useful idea is thread-scoped persistence: a `thread_id` identifies a sequence of checkpoints that let an agent resume state across interactions. Borrow the thread/checkpoint model, but do not bind the product to LangGraph execution. Source: [LangGraph persistence](https://docs.langchain.com/oss/javascript/langgraph/persistence).

OpenHands' useful idea is conversation persistence as base state plus append-only event files. Borrow event-sourcing and incremental access, because it gives better recovery and handoff than one giant summary. Source: [OpenHands conversation persistence](https://docs.openhands.dev/sdk/guides/convo-persistence).

Claude Code and Codex show that agents work better when stable project instructions are in small, predictable files, with deeper context loaded on demand. Borrow progressive disclosure: protocol first, handoff summary second, detailed events and sources only when needed. Sources: [Claude Code memory](https://code.claude.com/docs/en/memory), [AGENTS.md](https://github.com/openai/agents.md).

Claude Code sessions also show that resume/export are first-class workflows. Borrow explicit session continuity and transcript export, but make the exported handoff budgeted and structured rather than a raw conversation dump. Source: [Claude Code sessions](https://code.claude.com/docs/en/sessions).

## 3. Product Principle

Just Ctrl V should have three memory tiers:

```text
Working Memory
  Short-lived task state used for current agent work and cross-agent handoff.

Episodic Memory
  Archived task event history and provenance. Searchable when requested, not injected by default.

Long-Term Memory
  User-confirmed knowledge, lessons, preferences, pitfalls, and reusable principles.
```

Working memory should be easy to forget. Long-term memory should be hard to pollute.

## 4. Core Concept: Task Capsule

A `TaskCapsule` is the short-term memory container for one task.

It should not replace `SourceItem`, `KnowledgeItem`, or `KnowledgePage`. It sits beside the knowledge core and may later produce long-term memory proposals.

### TaskSession

Purpose:

- Represents one unit of work, such as "refactor knowledge architecture" or "prepare interview project story".

Durability:

- Durable while active or archived.
- Excluded from default knowledge search unless explicitly requested.

Key states:

```text
open
paused
handoff_ready
waiting_user
closing_review
closed
archived
expired
```

Important fields:

```text
id
title
user_goal
status
active_agent
created_at
updated_at
last_event_at
closed_at
expiry_policy
source_refs
```

### TaskEvent

Purpose:

- Append-only event log for observable task progress.

Durability:

- Durable while the task is retained.
- Can be compacted into checkpoints and archived.

Event types:

```text
user_goal
user_constraint
agent_observation
agent_action
decision
file_change
test_result
blocker
question
handoff_created
checkpoint_created
memory_candidate
task_closed
```

Rules:

- Events are append-only.
- Events should contain summaries and references, not hidden chain-of-thought.
- Tool output should be summarized unless the exact output is needed as evidence.

### TaskState

Purpose:

- Current projection of the task, like a living `git status`.

Fields:

```text
current_goal
done
in_progress
next_steps
open_questions
constraints
risks
decisions
files_touched
blocked_by
freshness
```

Rules:

- It can be updated by agents, but user-visible UI must show it.
- It is derived from events plus explicit updates.
- It must include `updated_at` and `confidence`.

### TaskCheckpoint

Purpose:

- Git-like checkpoint that summarizes task state at a meaningful boundary.

Analogy:

```text
git commit -> TaskCheckpoint
git reflog -> TaskEvent log
git branch -> TaskBranch or alternate TaskSession path
git merge  -> user-reviewed reconciliation
```

Rules:

- A checkpoint captures what changed, why it changed, what remains, and how to resume.
- Checkpoints are better handoff anchors than raw event history.

### HandoffPack

Purpose:

- Budgeted, structured context for another agent.

It should include:

```text
task id and status
freshness timestamp
user goal
non-negotiable constraints
completed work
current state
open questions
important decisions
known failed attempts
files/artifacts touched
next recommended action
relevant long-term memories
source refs
checkpoint refs
```

Rules:

- A handoff pack must never claim the task is complete unless the task is actually closed.
- A handoff pack must say if it is stale.
- A handoff pack must be short by default and support drill-down.

### MemoryPromotion

Purpose:

- Candidate long-term memory distilled from a completed or paused task.

Promotion types:

```text
lesson
pitfall
user_preference
project_rule
workflow_pattern
technical_decision
environment_fact
```

Rules:

- Promotions are not automatically inserted into long-term knowledge.
- The user must accept, edit, or reject them.
- Accepted promotions become `KnowledgeItem`, `MemoryFact`, or a `KnowledgePage` update.
- Rejected promotions remain as task history only.

## 5. Completion And Staleness

Task completion cannot be fully automatic.

The system should support three signals:

```text
Explicit user close
  The strongest signal. User clicks "Finish task" or says the task is done.

Agent proposed close
  Agent says tests passed / deliverable is complete / next action is review. The UI shows a close suggestion.

Dormancy expiry
  Task has no events for N days. It becomes stale or expired, but not completed.
```

Default behavior:

- New agents receive only active tasks selected by the user or explicitly referenced.
- Stale tasks are not injected silently.
- Closed tasks are excluded from handoff by default.
- Archived task events are available through explicit search.

UI controls required:

```text
Start Task
Pause Task
Request Handoff
Mark Handoff Ready
Finish Task
Archive Task
Promote Lessons
Discard Working Memory
```

This is necessary. Without user-controlled closure, the product will eventually feed stale context into new agents and make them worse.

## 6. Agent Integration Model

There should be three integration levels.

### Level 1: Copy/Paste Handoff

For any agent with no plugin support:

- User clicks "Copy Handoff".
- Handoff is Markdown plus compact JSON refs.
- Agent can continue manually.

This is the minimum viable version.

### Level 2: MCP Tools

For Claude Code, Codex-like tools, Cursor-like agents, and future agent clients:

```text
start_task
record_task_event
update_task_state
create_checkpoint
get_handoff_pack
list_active_tasks
close_task
propose_memory
search_long_term_memory
get_source_excerpt
```

Write tools should create events and proposals, not silently mutate long-term knowledge.

### Level 3: Native Agent Plugins

For richer integrations:

- Auto-detect project/workspace.
- Attach file refs and command results.
- Show active task status inside the agent.
- Ask the user before close/promote.

The native plugin can be replaced without changing the memory core.

## 7. How Short-Term Memory Becomes Long-Term Memory

Task close should trigger a reflection pipeline:

```text
TaskSession closed or paused for review
-> collect TaskState, checkpoints, important events, source refs
-> generate MemoryPromotion proposals
-> classify proposal type
-> attach evidence refs
-> user reviews proposals
-> accepted proposals become formal long-term knowledge
-> task working memory is archived or expired
```

Examples:

```text
Pitfall:
  "Do not rely on browser smoke tests for this project unless explicitly requested; they can stall the workflow."

User preference:
  "User prefers code-level verification over launching local services for this app."

Workflow pattern:
  "For architecture refactors, update AI_PROJECT_BRIEF.md alongside code boundaries."

Technical decision:
  "Use durable AnalysisJob records for recoverable AI analysis instead of bare background tasks."
```

The important distinction:

- Task events preserve what happened.
- Memory promotions preserve what should matter next time.

## 8. Proposed Data Model

Add these tables after the current knowledge-core foundation:

```text
task_sessions
task_events
task_states
task_checkpoints
handoff_packs
memory_promotions
task_source_links
```

Do not overload `KnowledgeItem` for task state. Task state is working memory, not long-term knowledge.

## 9. Proposed API

```text
POST   /api/tasks
GET    /api/tasks?status=open
GET    /api/tasks/{task_id}
PATCH  /api/tasks/{task_id}/state
POST   /api/tasks/{task_id}/events
POST   /api/tasks/{task_id}/checkpoints
GET    /api/tasks/{task_id}/handoff
POST   /api/tasks/{task_id}/handoff
POST   /api/tasks/{task_id}/close
POST   /api/tasks/{task_id}/archive
GET    /api/memory-promotions?status=pending
POST   /api/memory-promotions/{promotion_id}/accept
POST   /api/memory-promotions/{promotion_id}/dismiss
```

The API should keep these boundaries:

- Task APIs manage working memory.
- Knowledge APIs manage confirmed long-term knowledge.
- Promotion APIs bridge the two with user review.

## 10. Frontend Plan

Add a new "Task Workbench" view.

Core areas:

```text
Active task selector
Task status and freshness
Current goal
Done / doing / next
Open questions
Decision log
Checkpoints
Copy handoff
Finish task
Memory promotion inbox
```

Important UX rules:

- The user must always see which task is active.
- If a task is stale, show it visibly.
- Starting a new task should not silently reuse the previous task.
- Finishing a task should open the memory promotion review flow.

## 11. Packaging And Delivery

The project should support one-command local setup:

```text
npx just-ctrl-v
```

or:

```text
uvx just-ctrl-v
```

Initial delivery can keep the existing local FastAPI + Vite + SQLite stack, then package it behind a single launcher.

Package outputs:

```text
Local web app
SQLite data directory
MCP server
Agent instruction files
Export bundle
```

Agent setup should generate optional files:

```text
AGENTS.md
CLAUDE.md snippet
MCP config snippet
```

These files should not contain large memory dumps. They should only teach the agent how to request task handoff and memory context.

## 12. Implementation Roadmap

### Stage 1: Task Capsule Backend

Goal:

- Add working-memory persistence without changing current knowledge search behavior.

Files:

```text
server/app/models.py
server/app/migrations.py
server/app/tasks/*
server/app/routes/tasks.py
server/tests/test_cards.py or server/tests/test_tasks.py
```

Verification:

- Create task.
- Append events.
- Update state.
- Generate handoff.
- Closed tasks excluded from active list.

### Stage 2: Task Workbench UI

Goal:

- Let users manually control active task, handoff, close, and archive.

Files:

```text
client/src/hooks/useTaskWorkspace.ts
client/src/pages/TaskWorkbenchPage.tsx
client/src/lib/api/tasks.ts
client/src/types/tasks.ts
client/src/App.tsx
```

Verification:

- Type check, lint, build.
- No local service launch required unless explicitly requested.

### Stage 3: Handoff Pack Protocol

Goal:

- Make cross-agent transfer reliable and budgeted.

Features:

- Markdown handoff.
- JSON handoff.
- Freshness and status warnings.
- Source refs and checkpoint refs.

Verification:

- Handoff for open task includes next steps.
- Handoff for stale task includes stale warning.
- Handoff for closed task is not returned by default.

### Stage 4: Memory Promotion Pipeline

Goal:

- Convert task experience into reviewed long-term memory.

Features:

- Generate promotions from task close.
- User accepts/edits/rejects.
- Accepted promotions create `KnowledgeItem` or update `KnowledgePage`.

Verification:

- Rejected promotion does not enter search.
- Accepted promotion appears in knowledge search and export.

### Stage 5: MCP Server

Goal:

- Let external agents use Just Ctrl V as memory substrate.

Tools:

```text
list_active_tasks
get_handoff_pack
record_task_event
create_checkpoint
propose_memory
search_memory
get_context_pack
```

Verification:

- MCP tools cannot write long-term knowledge directly.
- MCP write tools create events or pending promotions.

### Stage 6: One-Command Packaging

Goal:

- Make installation and agent setup simple enough for external users.

Verification:

- Fresh machine path creates data dir, installs dependencies, launches app.
- Agent config snippets are generated but memory dumps are not embedded in instruction files.

## 13. Risks And Controls

Risk: stale context is fed into a new agent.

Control:

- Active task selection, freshness labels, closed-task exclusion, stale warnings.

Risk: task event log grows without limit.

Control:

- Checkpoint compaction, archive policy, expiry policy, explicit export.

Risk: low-quality AI summaries pollute long-term memory.

Control:

- MemoryPromotion review. No automatic promotion to `KnowledgeItem`.

Risk: agent integrations write inconsistent state.

Control:

- Append-only events, state projection, source refs, user-visible audit log.

Risk: hidden agent reasoning is expected but unavailable.

Control:

- Document that only observable task events and agent-provided summaries are captured.

## 14. North Star

Just Ctrl V should become:

```text
A local-first personal memory system that preserves source evidence, carries short-term task state across agents, and distills completed work into user-reviewed long-term knowledge.
```

The product wins only if it helps users avoid re-explaining themselves while still keeping them in control of what is remembered, forgotten, and promoted.

## 15. Future-Agent Knowledge Operating System

The broader product ambition is larger than task handoff:

```text
Just Ctrl V should become a personal knowledge operating system that any future agent can use, update, verify, and migrate.
```

This matters because model and agent capabilities are improving quickly. If a future product combines personal knowledge and agent execution better than this project, Just Ctrl V only remains useful if its architecture can absorb, replace, or interoperate with that new capability without losing the user's knowledge.

### Stable Core

These assets must remain stable even if models, agent clients, indexes, databases, or UI frameworks change:

```text
Source evidence
User-confirmed knowledge
Task capsules
Provenance links
Review decisions
Exportable records
```

These capabilities must remain replaceable:

```text
AI extraction provider
Embedding provider
FTS/vector/graph index
Reranker
Agent client
MCP implementation
Frontend shell
```

The project should never let a model provider, agent product, or search index become the source of truth.

### Architecture Layers

The long-term architecture should be layered like this:

```text
Source Vault
  Durable original evidence: text, image refs, links, external selections, task events.

Memory Kernel
  Confirmed KnowledgeItems, KnowledgePages, future Entity/Fact/Relation records, provenance, status.

Processing Pipeline
  Analysis jobs, extraction, deduplication, confidence checks, merge/supersede suggestions.

Retrieval Engine
  FTS, vector, graph, reranker, and context-pack orchestration behind replaceable providers.

Agent Protocol
  MCP/tools/API for search, context packs, task handoff, event recording, and memory proposals.

Human Review Workbench
  User confirmation for imports, task closure, memory promotions, page updates, and conflicts.

Export/Migration Layer
  Markdown, JSONL, provenance, source bundles, task capsules, and agent instruction snippets.
```

This is the difference between a knowledge app and a knowledge operating system.

### External Systems To Adapt, Not Copy

Graphiti/Zep style temporal knowledge graphs are useful for future `Entity`, `Fact`, and `Relation` modeling. The key idea is that facts can change over time and should remain traceable to source episodes.

Mem0-style memory APIs are useful for agent integration. The key idea is that memory should be an independent service agents can retrieve from and update through, not a hidden part of one chat UI.

Letta-style stateful agents are useful as a warning and an inspiration. Agents may have state, but Just Ctrl V should own the user's durable memory rather than becoming dependent on one agent runtime.

Claude Code, Codex, and similar coding agents show that small project instruction files work better than giant context dumps. The project should generate `AGENTS.md`, `CLAUDE.md` snippets, or MCP config snippets that teach agents how to ask Just Ctrl V for memory, not embed the memory itself.

### Future Domain Model Additions

After Task Capsule support exists, the next memory-kernel expansion should add:

```text
Entity
  A person, project, tool, product, concept, company, file, or system the user repeatedly refers to.

MemoryFact
  A user-confirmed factual statement with provenance, confidence, status, and optional validity window.

MemoryRelation
  A relationship between entities or facts, such as "uses", "prefers", "blocked_by", "replaces", "depends_on".

MemoryConflict
  A detected contradiction or outdated fact that requires review.

MemoryProposal
  A pending write suggested by an agent, analysis job, or task close reflection.
```

These records should not replace `KnowledgeItem` immediately. They should grow alongside it:

```text
KnowledgeItem
  Human-readable atomic knowledge.

MemoryFact / MemoryRelation
  Machine-usable structured memory for agents.

KnowledgePage
  Long-lived topic page compiled from confirmed items and facts.
```

### Agent Write Rules

Any future agent integration must follow these rules:

```text
Agents may read budgeted context.
Agents may append task events.
Agents may create checkpoints.
Agents may propose memory.
Agents may not silently create long-term knowledge.
Agents may not rewrite KnowledgePage bodies without review.
Agents may not request full-library dumps by default.
```

This keeps the system useful for agents without letting them pollute the user's second brain.

### Verification And Migration Requirements

Every durable memory record should answer:

```text
Where did this come from?
Who or what proposed it?
Did the user confirm it?
What task or source produced it?
Is it active, superseded, archived, rejected, or stale?
Can it be exported and re-imported elsewhere?
```

Export should eventually include:

```text
manifest.json
index.md
wiki/*.md
items.jsonl
entities.jsonl
facts.jsonl
relations.jsonl
task_sessions.jsonl
task_events.jsonl
checkpoints/
sources/
provenance.jsonl
agent-instructions/
```

The migration promise is simple:

```text
If Just Ctrl V disappears, the user's knowledge and task history should still be readable, attributable, and usable by another agent or tool.
```

### Implementation Implication

Do not implement future memory features as UI-only conveniences.

Each new feature should map to one of these durable layers:

```text
source evidence
working task memory
reviewed long-term memory
derived index/cache
agent protocol
export/migration
```

If it does not fit one of those layers, it is probably a temporary experiment and should not become core architecture.
