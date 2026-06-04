# Memory Reliability Evals

This folder contains the deterministic challenge suite for the project memory layer. It is separate from `server/tests`: tests catch product regressions, while evals produce memory-reliability metrics.

Run:

```powershell
python evals/run_memory_eval.py --output evals/reports/latest.md --json-output evals/reports/latest.json
python evals/run_scale_benchmark.py --sizes 1000 5000 --queries 120 --output evals/reports/scale_latest.md --json-output evals/reports/scale_latest.json
```

Default `challenge` mode combines JSONL seed fixtures, generated adversarial cases, privacy/scope checks, lifecycle checks, and evaluator fault injection.
The scale benchmark separately measures local SQLite growth, retrieval latency/QPS, concurrent reads, and write lock conflicts.

Full method: `docs/MEMORY_EVALUATION_PROTOCOL.md`.
