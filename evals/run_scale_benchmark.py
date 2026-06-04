from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel, Session, create_engine, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server.app.database_tuning import configure_sqlite_engine
from server.app.indexing.sqlite_fts import init_knowledge_search_index, refresh_knowledge_search_index
from server.app.models import KnowledgeItem, SourceItem
from server.app.retrieval.engine import RetrievalEngine
from server.app.retrieval.vector import LocalVectorSearch


SUITE_VERSION = "scale-benchmark-v1"
TOPICS = [
    "agent handoff",
    "memory review gate",
    "context pack",
    "privacy boundary",
    "retrieval fusion",
    "profile graph",
    "source evidence",
    "task digest",
]


@dataclass(frozen=True)
class QueryCase:
    query: str
    expected_id: str | None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local SQLite scale benchmarks for the memory retrieval path.")
    parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 5000])
    parser.add_argument("--queries", type=int, default=40)
    parser.add_argument("--warmup-queries", type=int, default=10)
    parser.add_argument("--read-workers", type=int, default=2)
    parser.add_argument("--write-workers", type=int, default=2)
    parser.add_argument("--writes-per-worker", type=int, default=10)
    parser.add_argument("--sqlite-timeout-ms", type=int, default=5000)
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "evals" / "reports" / "scale_latest.md")
    parser.add_argument("--json-output", type=Path, default=ROOT_DIR / "evals" / "reports" / "scale_latest.json")
    args = parser.parse_args()

    reports = []
    with tempfile.TemporaryDirectory(prefix="second-brain-scale-") as temp_dir:
        temp_root = Path(temp_dir)
        for size in args.sizes:
            reports.append(run_size_benchmark(size=size, temp_root=temp_root, args=args))

    payload = {
        "suiteVersion": SUITE_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "benchmarkScope": "local_sqlite_single_process",
        "reports": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(payload), encoding="utf-8")
    args.json_output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(render_console(payload))


def run_size_benchmark(size: int, temp_root: Path, args: argparse.Namespace) -> dict[str, Any]:
    db_path = temp_root / f"scale_{size}.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": args.sqlite_timeout_ms / 1000},
    )
    configure_sqlite_engine(engine, busy_timeout_ms=args.sqlite_timeout_ms)
    try:
        SQLModel.metadata.create_all(engine)
        init_knowledge_search_index(engine)

        seed_started = time.perf_counter()
        with Session(engine) as session:
            seed_knowledge_items(session, size)
            session.commit()
        seed_seconds = time.perf_counter() - seed_started

        query_cases = build_query_cases(size, args.queries + args.warmup_queries)
        LocalVectorSearch.clear_cache()
        warm_retrieval_cache(engine, query_cases[: args.warmup_queries])
        measured_cases = query_cases[args.warmup_queries :]

        sequential = benchmark_sequential_reads(engine, measured_cases)
        concurrent_reads = benchmark_concurrent_reads(engine, measured_cases, workers=args.read_workers)
        concurrent_writes = benchmark_concurrent_writes(
            engine,
            start_index=size,
            workers=args.write_workers,
            writes_per_worker=args.writes_per_worker,
        )

        with Session(engine) as session:
            item_count = len(session.exec(select(KnowledgeItem)).all())

        return {
            "size": size,
            "sqliteTimeoutMs": args.sqlite_timeout_ms,
            "dbBytes": db_path.stat().st_size if db_path.exists() else 0,
            "seedSeconds": seed_seconds,
            "seedItemsPerSecond": size / seed_seconds if seed_seconds else 0.0,
            "finalItemCount": item_count,
            "sequentialReads": sequential,
            "concurrentReads": concurrent_reads,
            "concurrentWrites": concurrent_writes,
        }
    finally:
        engine.dispose()


def seed_knowledge_items(session: Session, size: int) -> None:
    for index in range(size):
        source, item = synthetic_memory_record(index)
        session.add(source)
        session.add(item)
        session.flush()
        refresh_knowledge_search_index(session, item)


def synthetic_memory_record(index: int) -> tuple[SourceItem, KnowledgeItem]:
    topic = TOPICS[index % len(TOPICS)]
    token = scale_token(index)
    source_id = f"scale-source-{index:07d}"
    item_id = f"scale-item-{index:07d}"
    shard = index % 97
    content = (
        f"{topic} benchmark memory {index}. "
        f"The unique lookup token is {token}. "
        f"This record belongs to shard-{shard:02d} and validates local-first retrieval growth. "
        "It includes source evidence, review-gated memory, and agent context recovery terms."
    )
    source = SourceItem(
        id=source_id,
        source="scale_benchmark",
        external_id=source_id,
        kind="synthetic",
        title=f"{topic.title()} source {index}",
        content_text=content,
        status="active",
    )
    item = KnowledgeItem(
        id=item_id,
        source_item_id=source_id,
        title=f"{topic.title()} memory {index}",
        summary=f"{topic} benchmark summary with {token}",
        content=content,
        keywords=[topic, token, f"shard-{shard:02d}"],
        source="scale_benchmark",
        source_ref=f"source:{source_id}",
        knowledge_type="fragment",
        status="active",
    )
    return source, item


def build_query_cases(size: int, count: int) -> list[QueryCase]:
    cases: list[QueryCase] = []
    for offset in range(count):
        if offset % 10 == 9:
            cases.append(QueryCase(query=f"zzqv-unseen-nomatch-{offset:07d}", expected_id=None))
            continue
        index = (offset * 37) % size
        cases.append(QueryCase(query=scale_token(index), expected_id=f"scale-item-{index:07d}"))
    return cases


def warm_retrieval_cache(engine, cases: list[QueryCase]) -> None:
    if not cases:
        return
    with Session(engine) as session:
        retrieval = RetrievalEngine(mode="hybrid")
        for case in cases:
            retrieval.search(session, case.query, limit=10)


def benchmark_sequential_reads(engine, cases: list[QueryCase]) -> dict[str, Any]:
    latencies: list[float] = []
    hits = 0
    negative_hits = 0
    with Session(engine) as session:
        retrieval = RetrievalEngine(mode="hybrid")
        wall_started = time.perf_counter()
        for case in cases:
            latency_ms, returned_ids = run_retrieval(session, retrieval, case.query)
            latencies.append(latency_ms)
            hits += is_expected_hit(case, returned_ids)
            negative_hits += is_expected_negative(case, returned_ids)
        wall_seconds = time.perf_counter() - wall_started
    return read_metrics(cases, latencies, hits, negative_hits, wall_seconds, errors=0)


def benchmark_concurrent_reads(engine, cases: list[QueryCase], *, workers: int) -> dict[str, Any]:
    latencies: list[float] = []
    hits = 0
    negative_hits = 0
    errors = 0
    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(read_once, engine, case) for case in cases]
        for future in as_completed(futures):
            try:
                case, latency_ms, returned_ids = future.result()
            except Exception:
                errors += 1
                continue
            latencies.append(latency_ms)
            hits += is_expected_hit(case, returned_ids)
            negative_hits += is_expected_negative(case, returned_ids)
    wall_seconds = time.perf_counter() - wall_started
    return read_metrics(cases, latencies, hits, negative_hits, wall_seconds, errors=errors) | {"workers": workers}


def read_once(engine, case: QueryCase) -> tuple[QueryCase, float, list[str]]:
    with Session(engine) as session:
        retrieval = RetrievalEngine(mode="hybrid")
        latency_ms, returned_ids = run_retrieval(session, retrieval, case.query)
    return case, latency_ms, returned_ids


def run_retrieval(session: Session, retrieval: RetrievalEngine, query: str) -> tuple[float, list[str]]:
    started = time.perf_counter()
    results = retrieval.search(session, query, limit=10)
    latency_ms = (time.perf_counter() - started) * 1000
    return latency_ms, [result.knowledge_item.id for result in results]


def benchmark_concurrent_writes(engine, *, start_index: int, workers: int, writes_per_worker: int) -> dict[str, Any]:
    total_writes = max(0, workers * writes_per_worker)
    latencies: list[float] = []
    lock_conflicts = 0
    other_errors = 0
    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(write_once, engine, start_index + offset) for offset in range(total_writes)]
        for future in as_completed(futures):
            status, latency_ms = future.result()
            if status == "ok":
                latencies.append(latency_ms)
            elif status == "locked":
                lock_conflicts += 1
            else:
                other_errors += 1
    wall_seconds = time.perf_counter() - wall_started
    successes = len(latencies)
    return {
        "workers": workers,
        "attemptedWrites": total_writes,
        "successfulWrites": successes,
        "lockConflicts": lock_conflicts,
        "otherErrors": other_errors,
        "writesPerSecond": successes / wall_seconds if wall_seconds else 0.0,
        "latencyMsP50": percentile(latencies, 50),
        "latencyMsP95": percentile(latencies, 95),
        "latencyMsP99": percentile(latencies, 99),
    }


def write_once(engine, index: int) -> tuple[str, float]:
    started = time.perf_counter()
    with Session(engine) as session:
        try:
            source, item = synthetic_memory_record(index)
            session.add(source)
            session.add(item)
            session.flush()
            refresh_knowledge_search_index(session, item)
            session.commit()
            return "ok", (time.perf_counter() - started) * 1000
        except OperationalError as exc:
            session.rollback()
            message = str(exc).lower()
            return ("locked" if "locked" in message or "busy" in message else "error"), 0.0
        except Exception:
            session.rollback()
            return "error", 0.0


def read_metrics(
    cases: list[QueryCase],
    latencies: list[float],
    hits: int,
    negative_hits: int,
    wall_seconds: float,
    *,
    errors: int,
) -> dict[str, Any]:
    expected_cases = [case for case in cases if case.expected_id]
    negative_cases = [case for case in cases if not case.expected_id]
    return {
        "queries": len(cases),
        "errors": errors,
        "qps": len(latencies) / wall_seconds if wall_seconds else 0.0,
        "hitRate": hits / len(expected_cases) if expected_cases else 1.0,
        "negativeAccuracy": negative_hits / len(negative_cases) if negative_cases else 1.0,
        "latencyMsP50": percentile(latencies, 50),
        "latencyMsP95": percentile(latencies, 95),
        "latencyMsP99": percentile(latencies, 99),
    }


def is_expected_hit(case: QueryCase, returned_ids: list[str]) -> int:
    return int(bool(case.expected_id and case.expected_id in returned_ids))


def is_expected_negative(case: QueryCase, returned_ids: list[str]) -> int:
    return int(case.expected_id is None and not returned_ids)


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def scale_token(index: int) -> str:
    return f"scale-token-{index:07d}"


def render_console(payload: dict[str, Any]) -> str:
    lines = [
        f"Scale benchmark ({payload['suiteVersion']}, {payload['benchmarkScope']})",
    ]
    for report in payload["reports"]:
        sequential = report["sequentialReads"]
        concurrent = report["concurrentReads"]
        writes = report["concurrentWrites"]
        lines.append(
            f"- {report['size']} items: seq p95 {sequential['latencyMsP95']:.1f} ms, "
            f"seq qps {sequential['qps']:.1f}, concurrent qps {concurrent['qps']:.1f}, "
            f"write locks {writes['lockConflicts']}/{writes['attemptedWrites']}",
        )
    return "\n".join(lines)


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Local Scale Benchmark Report",
        "",
        f"Generated: `{payload['generatedAt']}`",
        f"Suite: `{payload['suiteVersion']}`",
        f"Scope: `{payload['benchmarkScope']}`",
        "",
        "## Claim Boundary",
        "",
        "This benchmark measures a local SQLite + FTS + hybrid retrieval process. It is useful for regression tracking and resume discussion, but it is not a distributed production QPS claim.",
        "",
        "## Growth",
        "",
        "| Items | DB MB | Seed sec | Seed items/sec | Final items |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for report in payload["reports"]:
        lines.append(
            f"| {report['size']} | {report['dbBytes'] / 1024 / 1024:.2f} | {report['seedSeconds']:.2f} | "
            f"{report['seedItemsPerSecond']:.1f} | {report['finalItemCount']} |",
        )

    lines.extend(
        [
            "",
            "## Sequential Reads",
            "",
            "| Items | Queries | Hit rate | Negative accuracy | QPS | p50 ms | p95 ms | p99 ms | Errors |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ],
    )
    for report in payload["reports"]:
        metrics = report["sequentialReads"]
        lines.append(read_row(report["size"], metrics))

    lines.extend(
        [
            "",
            "## Concurrent Reads",
            "",
            "| Items | Workers | Queries | Hit rate | Negative accuracy | QPS | p50 ms | p95 ms | p99 ms | Errors |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ],
    )
    for report in payload["reports"]:
        metrics = report["concurrentReads"]
        lines.append(read_row(report["size"], metrics, include_workers=True))

    lines.extend(
        [
            "",
            "## Concurrent Writes",
            "",
            "| Items before | Workers | Attempted | Successful | Lock conflicts | Other errors | Writes/sec | p50 ms | p95 ms | p99 ms |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ],
    )
    for report in payload["reports"]:
        metrics = report["concurrentWrites"]
        lines.append(
            f"| {report['size']} | {metrics['workers']} | {metrics['attemptedWrites']} | {metrics['successfulWrites']} | "
            f"{metrics['lockConflicts']} | {metrics['otherErrors']} | {metrics['writesPerSecond']:.1f} | "
            f"{metrics['latencyMsP50']:.1f} | {metrics['latencyMsP95']:.1f} | {metrics['latencyMsP99']:.1f} |",
        )
    return "\n".join(lines) + "\n"


def read_row(size: int, metrics: dict[str, Any], *, include_workers: bool = False) -> str:
    prefix = f"| {size} | "
    if include_workers:
        prefix += f"{metrics['workers']} | "
    return (
        f"{prefix}{metrics['queries']} | {metrics['hitRate'] * 100:.1f}% | {metrics['negativeAccuracy'] * 100:.1f}% | "
        f"{metrics['qps']:.1f} | {metrics['latencyMsP50']:.1f} | {metrics['latencyMsP95']:.1f} | "
        f"{metrics['latencyMsP99']:.1f} | {metrics['errors']} |"
    )


if __name__ == "__main__":
    main()
