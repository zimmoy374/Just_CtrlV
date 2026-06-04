# Memory Evaluation Protocol

This project uses an internal deterministic challenge suite for agent-memory reliability. The goal is not to claim public SOTA. The goal is to make a resume/interview claim that is reproducible, falsifiable, and honest about its evidence tier.

For measuring whether external agents actually benefit from connecting to this memory system, see `docs/AGENT_USEFULNESS_EVALUATION.md`. This document evaluates internal memory correctness; the usefulness protocol evaluates task-continuation lift against baselines.

## Claim Boundary

Allowed claim:

> Built a deterministic agent-memory reliability benchmark covering ContextPack retrieval, cross-agent handoff recovery, privacy/scope isolation, review-gated lifecycle correctness, and evaluator fault sensitivity.

Updated claim after the ContextPack trace work:

> Built a deterministic agent-memory reliability benchmark covering hybrid retrieval, budgeted ContextPack selection trace, cross-agent handoff recovery, privacy/scope isolation, review-gated lifecycle correctness, and evaluator fault sensitivity.

Not allowed yet:

- "SOTA memory system"
- "100% memory accuracy"
- "Public benchmark winner"

Current evidence tier is `interview_ready_internal_challenge_not_sota`: strong enough to discuss in an interview because it is reproducible and adversarial, but it is still not a public benchmark result.

## Suite Design

The default command runs the `challenge` profile:

```powershell
python evals/run_memory_eval.py --output evals/reports/latest.md --json-output evals/reports/latest.json
```

The suite combines:

- JSONL seed fixtures in `evals/datasets/`.
- Deterministically generated challenge cases in `evals/run_memory_eval.py`.
- Fault-injection checks that prove the evaluator catches bad outcomes.

The runner uses real service-layer code and an in-memory SQLite database. It does not call external LLM APIs, so the result is deterministic and cheap to reproduce.

## Evaluation Axes

### 1. ContextPack Retrieval

Measures whether the memory system retrieves the right knowledge under distractors and negative queries.

Metrics:

- `recallAtK`
- `mrr`
- `precisionAtK`
- `negativeAccuracy`
- `forbiddenReturnRate`
- `citationCoverage`
- `budgetAdherence`
- `selectionTraceCoverage`

Why it matters: a memory system that retrieves the right item but floods irrelevant context is still expensive and brittle.

### 1.5. Retrieval Ablation

Measures whether the hybrid retriever actually improves over single-channel baselines.

Modes:

- `lexical`: SQLite FTS and field/keyword scoring only.
- `vector`: local deterministic vector recall only.
- `hybrid`: lexical + vector candidates fused with RRF and lightweight reranking.

Metrics:

- `lexicalRecallAtK`
- `vectorRecallAtK`
- `hybridRecallAtK`
- `lexicalMrr`
- `vectorMrr`
- `hybridMrr`
- `hybridRecallLift`
- `hybridMrrLift`
- `hybridNdcgAtK`
- `hybridLatencyMsAvg`

### 2. Cross-Agent Handoff Recovery

Measures whether a new agent can recover useful work state from task handoff data.

Metrics:

- `recoveryRate`
- `digestCoverage`

Checked fields include current goal, done work, next steps, decisions, risks, touched files, handoff content, source refs, and TaskDigest coverage.

### 3. Privacy and Scope Isolation

Measures whether default `work` retrieval leaks private/profile/capability-gated/task-scoped memory.

Metrics:

- `privacyLeakRate`
- `privacyIsolationScore`
- `capabilityRetrievalRate`

The suite includes private source memory, profile facts, capability-required records, and task-scope boundaries.

### 4. Review-Gated Lifecycle

Measures whether long-term memory remains review-gated.

Metrics:

- `lifecycleAccuracy`
- `agentToolSurfaceSafety`

Checked behavior:

- pending proposals are not searchable,
- accepted proposals become searchable,
- decisions and provenance are recorded,
- invalid target stores are rejected,
- agent tools do not expose direct accept/purge/conflict-resolution APIs.

### 5. Evaluator Sensitivity

Measures whether the evaluator itself can catch injected failures.

Faults injected:

- missing expected retrieval,
- forbidden retrieval,
- lost handoff digest,
- privacy leak,
- lifecycle bypass,
- missing provenance.

This prevents the report from becoming a rubber-stamp scorecard.

## Report Fields

- `functionalChallengeScore`: weighted functional score across retrieval, handoff, privacy, and lifecycle.
- `evaluationRigorScore`: case volume, category breadth, adversarial coverage, evaluator sensitivity, reproducibility, and public benchmark status.
- `evidenceLevel`: the claim boundary this report supports.
- `publicBenchmarkStatus`: currently `not_run`.
- `privacyLeakRate`: lower is better; target is 0%.

## Local Scale Benchmark

`evals/run_scale_benchmark.py` is separate from the functional memory benchmark so scale evidence does not bloat the correctness suite. It creates temporary SQLite databases, seeds synthetic `SourceItem` and `KnowledgeItem` records, builds the real FTS projection, and exercises the actual hybrid `RetrievalEngine`.

It reports:

- database size growth,
- seed throughput,
- sequential retrieval QPS and p50/p95/p99 latency,
- concurrent retrieval QPS and latency,
- concurrent write success count, lock conflicts, errors, throughput, and p95 latency.

Recommended resume/interview command:

```powershell
python evals/run_scale_benchmark.py --sizes 1000 5000 --queries 40 --read-workers 2 --write-workers 2 --writes-per-worker 10 --output evals/reports/scale_latest.md --json-output evals/reports/scale_latest.json
```

Claim boundary: this is local single-process SQLite evidence. It supports statements about measured local-first scale and regression tracking, not distributed production QPS.

## Next Evidence Tier

To move beyond internal challenge-suite evidence:

- adapt a public long-memory benchmark such as LongMemEval or LoCoMo into this runner,
- add larger held-out cases not tuned during development,
- track scale benchmark trends across commits and machine profiles,
- record token-budget distributions for real ContextPack requests,
- run mutation tests against intentionally weakened memory filters,
- publish the benchmark report alongside the code.
