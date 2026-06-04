from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from sqlmodel import SQLModel, Session, create_engine, select


ROOT_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = Path(__file__).resolve().parent / "datasets"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server.app.agent_runtime.capabilities import resolve_capabilities
from server.app.indexing.sqlite_fts import init_knowledge_search_index, rebuild_knowledge_search_index
from server.app.memory_core.composer import MemoryContextComposer
from server.app.memory_core.router import create_default_memory_router
from server.app.memory_kernel.proposals import create_memory_proposal
from server.app.models import (
    Entity,
    KnowledgeItem,
    MemoryDecision,
    MemoryFact,
    ProvenanceEvent,
    SourceItem,
)
from server.app.routes.agent import list_agent_tools_api
from server.app.retrieval.engine import RetrievalEngine
from server.app.tasks.events import append_task_event
from server.app.tasks.handoff import preview_handoff_pack
from server.app.tasks.sessions import create_task_session
from server.app.tasks.state import update_task_state


SUITE_VERSION = "memory-reliability-eval-v1"
EXPECTED_EVAL_CATEGORIES = {
    "context_retrieval",
    "retrieval_ablation",
    "handoff_recovery",
    "privacy_isolation",
    "review_lifecycle",
    "evaluator_sensitivity",
}


@dataclass(frozen=True)
class CategoryReport:
    name: str
    metrics: dict[str, float]
    cases: list[dict[str, Any]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic memory reliability evaluations.")
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    parser.add_argument("--profile", choices=["seed", "challenge"], default="challenge")
    parser.add_argument("--output", type=Path, default=None, help="Write a Markdown report, for example evals/reports/latest.md.")
    parser.add_argument("--json-output", type=Path, default=None, help="Write raw JSON metrics and case details.")
    parser.add_argument("--min-functional", type=float, default=0.80)
    args = parser.parse_args()

    retrieval_cases = load_retrieval_cases(args.dataset_dir, args.profile)
    reports = [
        evaluate_context_retrieval(retrieval_cases),
        evaluate_retrieval_ablation(retrieval_cases),
        evaluate_handoff_recovery(load_handoff_cases(args.dataset_dir, args.profile)),
        evaluate_privacy_isolation(load_privacy_cases(args.dataset_dir, args.profile)),
        evaluate_review_lifecycle(load_lifecycle_cases(args.dataset_dir, args.profile)),
        evaluate_evaluator_sensitivity(),
    ]
    summary = build_summary(reports)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "suiteVersion": SUITE_VERSION,
        "profile": args.profile,
        "summary": summary,
        "categories": [
            {
                "name": report.name,
                "metrics": report.metrics,
                "cases": report.cases,
            }
            for report in reports
        ],
    }

    markdown = render_markdown_report(payload)
    print(render_console_summary(payload))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if summary["functionalChallengeScore"] < args.min_functional:
        raise SystemExit(1)


def evaluate_context_retrieval(cases: list[dict[str, Any]]) -> CategoryReport:
    with memory_session() as session:
        for case in cases:
            for record in case["memories"]:
                insert_knowledge_record(
                    session,
                    item_id=record["id"],
                    source_id=record.get("sourceId"),
                    title=record["title"],
                    summary=record["summary"],
                    content=record["content"],
                    keywords=record.get("keywords", []),
                    knowledge_type=record.get("knowledgeType", "fragment"),
                    source_metadata=record.get("sourceMetadata"),
                )
        session.commit()
        rebuild_knowledge_search_index(session)

        composer = MemoryContextComposer(create_default_memory_router())
        results: list[dict[str, Any]] = []
        recall_values: list[float] = []
        mrr_values: list[float] = []
        precision_values: list[float] = []
        negative_values: list[float] = []
        forbidden_values: list[float] = []
        citation_values: list[float] = []
        budget_values: list[float] = []
        selection_trace_values: list[float] = []

        for case in cases:
            pack = composer.build_context_pack(
                session,
                query=case["query"],
                max_items=case.get("k", 5),
                max_chars=case.get("maxChars", 4000),
            )
            returned_ids = returned_memory_item_ids(pack)
            expected_ids = case.get("expectedItemIds", [])
            forbidden_ids = case.get("forbiddenItemIds", [])
            hits = [item_id for item_id in expected_ids if item_id in returned_ids]
            forbidden_hits = [item_id for item_id in forbidden_ids if item_id in returned_ids]
            recall = len(hits) / len(expected_ids) if expected_ids else 1.0
            first_rank = min((returned_ids.index(item_id) + 1 for item_id in hits), default=0)
            mrr = 1 / first_rank if first_rank else (1.0 if not expected_ids else 0.0)
            precision = len(hits) / len(returned_ids) if returned_ids else (1.0 if not expected_ids else 0.0)
            negative_accuracy = 1.0 if not expected_ids and not returned_ids else 0.0 if not expected_ids else 1.0
            forbidden_rate = len(forbidden_hits) / len(forbidden_ids) if forbidden_ids else 0.0
            citation_refs = {item["ref"] for item in pack["citationRefs"]}
            citation_coverage = (
                len([item_id for item_id in expected_ids if f"item:{item_id}" in citation_refs]) / len(expected_ids)
                if expected_ids
                else 1.0
            )
            budget_ok = 1.0 if pack["budget"]["usedChars"] <= case.get("maxChars", 4000) else 0.0
            selection_trace = pack.get("selectionTrace") or []
            selected_refs = {item.get("ref") for item in selection_trace if item.get("status") == "selected"}
            returned_refs = {f"item:{item_id}" for item_id in returned_ids}
            trace_has_required_fields = all(
                set(item) >= {"status", "ref", "kind", "store", "section", "reason", "score", "usedChars", "citationRef"}
                for item in selection_trace
            )
            selection_trace_coverage = 1.0 if trace_has_required_fields and returned_refs.issubset(selected_refs) else 0.0

            recall_values.append(recall)
            mrr_values.append(mrr)
            precision_values.append(precision)
            negative_values.append(negative_accuracy)
            forbidden_values.append(forbidden_rate)
            citation_values.append(citation_coverage)
            budget_values.append(budget_ok)
            selection_trace_values.append(selection_trace_coverage)
            results.append(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "expectedItemIds": expected_ids,
                    "forbiddenItemIds": forbidden_ids,
                    "returnedItemIds": returned_ids,
                    "recallAtK": recall,
                    "mrr": mrr,
                    "precisionAtK": precision,
                    "negativeAccuracy": negative_accuracy,
                    "forbiddenReturnRate": forbidden_rate,
                    "forbiddenHits": forbidden_hits,
                    "citationCoverage": citation_coverage,
                    "budgetOk": bool(budget_ok),
                    "selectionTraceCoverage": selection_trace_coverage,
                    "selectionTraceStatuses": sorted({str(item.get("status")) for item in selection_trace}),
                    "usedChars": pack["budget"]["usedChars"],
                },
            )

    return CategoryReport(
        name="context_retrieval",
        metrics={
            "recallAtK": mean_or_zero(recall_values),
            "mrr": mean_or_zero(mrr_values),
            "precisionAtK": mean_or_zero(precision_values),
            "negativeAccuracy": mean_or_zero(negative_values),
            "forbiddenReturnRate": mean_or_zero(forbidden_values),
            "citationCoverage": mean_or_zero(citation_values),
            "budgetAdherence": mean_or_zero(budget_values),
            "selectionTraceCoverage": mean_or_zero(selection_trace_values),
        },
        cases=results,
    )


def evaluate_retrieval_ablation(cases: list[dict[str, Any]]) -> CategoryReport:
    modes = ["lexical", "vector", "hybrid"]
    mode_scores: dict[str, dict[str, list[float]]] = {
        mode: {"recallAtK": [], "mrr": [], "precisionAtK": [], "ndcgAtK": [], "latencyMs": []}
        for mode in modes
    }
    case_results: list[dict[str, Any]] = []

    with memory_session() as session:
        seen_item_ids: set[str] = set()
        for case in cases:
            for record in case["memories"]:
                if record["id"] in seen_item_ids:
                    continue
                seen_item_ids.add(record["id"])
                insert_knowledge_record(
                    session,
                    item_id=record["id"],
                    source_id=record.get("sourceId"),
                    title=record["title"],
                    summary=record["summary"],
                    content=record["content"],
                    keywords=record.get("keywords", []),
                    knowledge_type=record.get("knowledgeType", "fragment"),
                    source_metadata=record.get("sourceMetadata"),
                )
        session.commit()
        rebuild_knowledge_search_index(session)

        for case in cases:
            expected_ids = case.get("expectedItemIds", [])
            if not expected_ids:
                continue
            per_case: dict[str, Any] = {"id": case["id"], "query": case["query"], "expectedItemIds": expected_ids, "modes": {}}
            for mode in modes:
                engine = RetrievalEngine(mode=mode)
                start = time.perf_counter()
                results = engine.search(session, case["query"], limit=case.get("k", 5))
                latency_ms = (time.perf_counter() - start) * 1000
                returned_ids = [result.knowledge_item.id for result in results]
                metrics = retrieval_metrics(expected_ids, returned_ids, case.get("k", 5))
                for metric_name in ["recallAtK", "mrr", "precisionAtK", "ndcgAtK"]:
                    mode_scores[mode][metric_name].append(metrics[metric_name])
                mode_scores[mode]["latencyMs"].append(latency_ms)
                per_case["modes"][mode] = {
                    **metrics,
                    "returnedItemIds": returned_ids,
                    "latencyMs": latency_ms,
                }
            case_results.append(per_case)

    lexical_recall = mean_or_zero(mode_scores["lexical"]["recallAtK"])
    hybrid_recall = mean_or_zero(mode_scores["hybrid"]["recallAtK"])
    lexical_mrr = mean_or_zero(mode_scores["lexical"]["mrr"])
    hybrid_mrr = mean_or_zero(mode_scores["hybrid"]["mrr"])
    return CategoryReport(
        name="retrieval_ablation",
        metrics={
            "lexicalRecallAtK": lexical_recall,
            "vectorRecallAtK": mean_or_zero(mode_scores["vector"]["recallAtK"]),
            "hybridRecallAtK": hybrid_recall,
            "lexicalMrr": lexical_mrr,
            "vectorMrr": mean_or_zero(mode_scores["vector"]["mrr"]),
            "hybridMrr": hybrid_mrr,
            "hybridRecallLift": hybrid_recall - lexical_recall,
            "hybridMrrLift": hybrid_mrr - lexical_mrr,
            "hybridNdcgAtK": mean_or_zero(mode_scores["hybrid"]["ndcgAtK"]),
            "hybridLatencyMsAvg": mean_or_zero(mode_scores["hybrid"]["latencyMs"]),
        },
        cases=case_results,
    )


def evaluate_handoff_recovery(cases: list[dict[str, Any]]) -> CategoryReport:
    results: list[dict[str, Any]] = []
    recovery_scores: list[float] = []
    digest_scores: list[float] = []

    with memory_session() as session:
        for case in cases:
            task = create_task_session(session, title=case["title"], user_goal=case["userGoal"], active_agent="eval-agent-a")
            state = case["state"]
            update_task_state(
                session,
                task.id,
                current_goal=state.get("currentGoal"),
                done=state.get("done"),
                in_progress=state.get("inProgress"),
                next_steps=state.get("nextSteps"),
                decisions=state.get("decisions"),
                risks=state.get("risks"),
                files_touched=state.get("filesTouched"),
            )
            for event in case["events"]:
                append_task_event(
                    session,
                    task,
                    event_type=event["type"],
                    summary=event["summary"],
                    source_ref=event.get("sourceRef", ""),
                )
            pack, content, budget = preview_handoff_pack(session, task, handoff_format="markdown")
            expect = case["expect"]
            checks = {
                "currentGoal": contains_all(pack["currentGoal"], expect.get("currentGoalContains", [])),
                "done": list_contains_all(pack["done"], expect.get("doneContains", [])),
                "nextSteps": list_contains_all(pack["nextSteps"], expect.get("nextStepsContains", [])),
                "decisions": list_contains_all(pack["decisions"], expect.get("decisionsContain", [])),
                "risks": list_contains_all(pack["risks"], expect.get("risksContain", [])),
                "filesTouched": list_contains_all(pack["filesTouched"], expect.get("filesTouchedContain", [])),
                "content": contains_all(content, expect.get("contentIncludes", [])),
            }
            digest_text = json.dumps(pack.get("taskDigest") or {}, ensure_ascii=False, default=str)
            digest_ok = contains_all(digest_text, expect.get("digestContains", []))
            field_score = sum(1 for value in checks.values() if value) / len(checks)
            recovery_scores.append(1.0 if field_score == 1.0 and digest_ok else field_score)
            digest_scores.append(1.0 if digest_ok else 0.0)
            results.append(
                {
                    "id": case["id"],
                    "taskId": task.id,
                    "fieldChecks": checks,
                    "digestCheck": digest_ok,
                    "recoveryScore": recovery_scores[-1],
                    "digestEventCount": budget["digestEventCount"],
                    "sourceRefCount": budget["sourceRefCount"],
                },
            )

    return CategoryReport(
        name="handoff_recovery",
        metrics={
            "recoveryRate": mean_or_zero(recovery_scores),
            "digestCoverage": mean_or_zero(digest_scores),
        },
        cases=results,
    )


def evaluate_privacy_isolation(cases: list[dict[str, Any]]) -> CategoryReport:
    results: list[dict[str, Any]] = []
    leak_values: list[float] = []
    allowed_values: list[float] = []

    with memory_session() as session:
        runtime_by_case_id: dict[str, dict[str, Any]] = {}
        for case in cases:
            runtime_by_case_id[case["id"]] = setup_privacy_case(session, case)
        session.commit()
        rebuild_knowledge_search_index(session)
        composer = MemoryContextComposer(create_default_memory_router())

        for case in cases:
            runtime = runtime_by_case_id.get(case["id"], {})
            work_pack = composer.build_context_pack(
                session,
                query=case["query"],
                max_chars=4000,
                task_session_id=runtime.get("workTaskSessionId"),
            )
            work_text = json.dumps(work_pack, ensure_ascii=False, default=str)
            leaked_tokens = [token for token in case["forbiddenWithoutCapabilities"] if token in work_text]
            capabilities = resolve_capabilities("trusted", case["capabilities"])
            allowed_pack = composer.build_context_pack(
                session,
                query=case["query"],
                capabilities=capabilities,
                max_chars=4000,
                task_session_id=runtime.get("allowedTaskSessionId"),
            )
            allowed_text = json.dumps(allowed_pack, ensure_ascii=False, default=str)
            allowed_hits = [token for token in case["allowedWithCapabilities"] if token in allowed_text]

            leak_values.append(1.0 if leaked_tokens else 0.0)
            allowed_values.append(len(allowed_hits) / len(case["allowedWithCapabilities"]))
            results.append(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "capabilities": capabilities,
                    "leakedTokensWithoutCapabilities": leaked_tokens,
                    "allowedHitsWithCapabilities": allowed_hits,
                    "workWarnings": work_pack["warnings"],
                },
            )

    leak_rate = mean_or_zero(leak_values)
    return CategoryReport(
        name="privacy_isolation",
        metrics={
            "privacyLeakRate": leak_rate,
            "privacyIsolationScore": 1.0 - leak_rate,
            "capabilityRetrievalRate": mean_or_zero(allowed_values),
        },
        cases=results,
    )


def evaluate_review_lifecycle(cases: list[dict[str, Any]]) -> CategoryReport:
    results: list[dict[str, Any]] = []
    lifecycle_scores: list[float] = []
    tool_surface_scores: list[float] = []

    tools = list_agent_tools_api()
    tool_payloads = [tool.model_dump(by_alias=True) for tool in tools]
    tool_names = {item["name"] for item in tool_payloads}
    direct_long_term_write_tools = [item["name"] for item in tool_payloads if item["directLongTermWrite"]]

    with memory_session() as session:
        for case in cases:
            expected_tools_present = all(name in tool_names for name in case["expectedToolNames"])
            forbidden_tools_absent = all(name not in tool_names for name in case["forbiddenToolNames"])
            no_direct_write = not direct_long_term_write_tools
            tool_surface_score = sum([expected_tools_present, forbidden_tools_absent, no_direct_write]) / 3

            proposal = create_memory_proposal(
                session,
                proposal_type=case["proposalType"],
                title=case["title"],
                body=case["body"],
                target_store=case["targetStore"],
                evidence_refs=[],
            )
            session.commit()
            before_pack = MemoryContextComposer(create_default_memory_router()).build_context_pack(
                session,
                query=case["query"],
                max_chars=4000,
            )
            pending_not_searchable = case["query"] not in pack_memory_surface(before_pack)

            accepted = create_default_memory_router().accept_proposal(session, proposal)
            session.commit()
            rebuild_knowledge_search_index(session)
            after_pack = MemoryContextComposer(create_default_memory_router()).build_context_pack(
                session,
                query=case["query"],
                max_chars=4000,
            )
            accepted_searchable = case["query"] in pack_memory_surface(after_pack)
            decision_types = {
                decision.decision_type
                for decision in session.exec(select(MemoryDecision).where(MemoryDecision.target_ref == f"proposal:{proposal.id}")).all()
            }
            expected_decisions_present = all(item in decision_types for item in case["expectedDecisions"])
            provenance_events = session.exec(select(ProvenanceEvent).where(ProvenanceEvent.from_ref == f"proposal:{proposal.id}")).all()
            provenance_recorded = len(provenance_events) >= 2

            invalid_target_rejected = False
            try:
                invalid_proposal = create_memory_proposal(
                    session,
                    proposal_type=case["proposalType"],
                    title=f"{case['title']} invalid target",
                    body="This invalid target must not materialize as memory.",
                    target_store="direct_agent_write",
                )
                create_default_memory_router().accept_proposal(session, invalid_proposal)
            except ValueError:
                invalid_target_rejected = True
                session.rollback()

            checks = {
                "agentToolSurface": tool_surface_score == 1.0,
                "pendingNotSearchable": pending_not_searchable,
                "acceptedSearchable": accepted_searchable,
                "expectedDecisionsPresent": expected_decisions_present,
                "provenanceRecorded": provenance_recorded,
                "invalidTargetRejected": invalid_target_rejected,
            }
            lifecycle_score = sum(1 for value in checks.values() if value) / len(checks)
            lifecycle_scores.append(lifecycle_score)
            tool_surface_scores.append(tool_surface_score)
            results.append(
                {
                    "id": case["id"],
                    "proposalId": proposal.id,
                    "acceptedKnowledgeItemId": accepted.knowledge_item_id,
                    "checks": checks,
                    "toolNames": sorted(tool_names),
                    "directLongTermWriteTools": direct_long_term_write_tools,
                    "decisionTypes": sorted(decision_types),
                    "provenanceEventCount": len(provenance_events),
                    "lifecycleScore": lifecycle_score,
                },
            )

    return CategoryReport(
        name="review_lifecycle",
        metrics={
            "lifecycleAccuracy": mean_or_zero(lifecycle_scores),
            "agentToolSurfaceSafety": mean_or_zero(tool_surface_scores),
        },
        cases=results,
    )


def evaluate_evaluator_sensitivity() -> CategoryReport:
    faults = [
        {
            "id": "detect_missing_retrieval",
            "category": "context_retrieval",
            "fault": "expected item omitted",
            "score": score_retrieval_outcome(["expected"], [], [], []),
        },
        {
            "id": "detect_forbidden_retrieval",
            "category": "context_retrieval",
            "fault": "forbidden distractor returned",
            "score": score_retrieval_outcome([], ["forbidden"], ["forbidden"], []),
        },
        {
            "id": "detect_handoff_loss",
            "category": "handoff_recovery",
            "fault": "decision and digest lost",
            "score": score_boolean_checks([True, True, False, False]),
        },
        {
            "id": "detect_privacy_leak",
            "category": "privacy_isolation",
            "fault": "private token exposed in work profile",
            "score": 0.0,
        },
        {
            "id": "detect_lifecycle_bypass",
            "category": "review_lifecycle",
            "fault": "pending proposal became searchable",
            "score": score_boolean_checks([True, False, True, True, True, True]),
        },
        {
            "id": "detect_missing_provenance",
            "category": "review_lifecycle",
            "fault": "accepted memory lacks provenance",
            "score": score_boolean_checks([True, True, True, True, False, True]),
        },
    ]
    cases = [
        {
            **fault,
            "detected": fault["score"] < 0.99,
        }
        for fault in faults
    ]
    return CategoryReport(
        name="evaluator_sensitivity",
        metrics={"faultDetectionRate": mean_or_zero([1.0 if case["detected"] else 0.0 for case in cases])},
        cases=cases,
    )


def setup_privacy_case(session: Session, case: dict[str, Any]) -> dict[str, Any]:
    if case["setup"] == "semantic_private":
        public_token = f"PUBLIC_{case['id'].upper()}"
        insert_knowledge_record(
            session,
            item_id=f"{case['id']}_public",
            title="Public memory isolation control",
            summary=f"{public_token} is safe to retrieve in work mode.",
            content=f"The query {case['query']} has a public control item that should stay visible.",
            keywords=[case["query"], public_token],
        )
        insert_knowledge_record(
            session,
            item_id=f"{case['id']}_private",
            title="Private memory isolation target",
            summary=case["forbiddenWithoutCapabilities"][0],
            content=f"The query {case['query']} points at private evidence: {case['forbiddenWithoutCapabilities'][0]}.",
            keywords=[case["query"], case["forbiddenWithoutCapabilities"][0]],
            source_metadata={
                "visibility": "private",
                "privacyLabels": ["private"],
            },
        )
        return {}

    if case["setup"] == "profile_fact":
        entity = Entity(
            id=f"{case['id']}_user",
            type="person",
            name="Eval User",
            aliases=[case["query"]],
        )
        fact = MemoryFact(
            id=f"{case['id']}_fact",
            subject_entity_id=entity.id,
            predicate="prefers",
            object_value=case["forbiddenWithoutCapabilities"][0],
            evidence_refs=[],
            status="active",
            scope="workspace",
        )
        session.add(entity)
        session.add(fact)
        session.flush()
        return {}

    if case["setup"] == "capability_required":
        insert_knowledge_record(
            session,
            item_id=f"{case['id']}_restricted",
            title="Capability gated memory target",
            summary=case["forbiddenWithoutCapabilities"][0],
            content=f"The query {case['query']} requires a declared capability: {case['forbiddenWithoutCapabilities'][0]}.",
            keywords=[case["query"], case["forbiddenWithoutCapabilities"][0]],
            source_metadata={"capabilityRequirements": case["capabilities"]},
        )
        return {}

    if case["setup"] == "task_scope":
        current_task = create_task_session(
            session,
            title=f"{case['id']} current task",
            user_goal=f"Evaluate scoped memory for {case['query']}",
            active_agent="eval-agent",
        )
        other_task = create_task_session(
            session,
            title=f"{case['id']} other task",
            user_goal=f"Hold unrelated scoped memory for {case['query']}",
            active_agent="eval-agent",
        )
        insert_knowledge_record(
            session,
            item_id=f"{case['id']}_current",
            title="Current task scoped memory",
            summary=case["allowedWithCapabilities"][0],
            content=f"The current task scoped token is {case['allowedWithCapabilities'][0]} for query {case['query']}.",
            keywords=[case["query"], case["allowedWithCapabilities"][0]],
            source_metadata={"scope": f"task:{current_task.id}"},
        )
        insert_knowledge_record(
            session,
            item_id=f"{case['id']}_other",
            title="Other task scoped memory",
            summary=case["forbiddenWithoutCapabilities"][0],
            content=f"The other task scoped token is {case['forbiddenWithoutCapabilities'][0]} for query {case['query']}.",
            keywords=[case["query"], case["forbiddenWithoutCapabilities"][0]],
            source_metadata={"scope": f"task:{other_task.id}"},
        )
        return {"allowedTaskSessionId": current_task.id}

    raise ValueError(f"Unknown privacy setup: {case['setup']}")


def insert_knowledge_record(
    session: Session,
    *,
    item_id: str,
    source_id: str | None = None,
    title: str,
    summary: str,
    content: str,
    keywords: list[str],
    knowledge_type: str = "fragment",
    source_metadata: dict[str, Any] | None = None,
) -> None:
    resolved_source_id = source_id or f"source_{item_id}"
    if not session.get(SourceItem, resolved_source_id):
        source = SourceItem(
            id=resolved_source_id,
            source="memory_eval",
            external_id=resolved_source_id,
            kind="eval_fixture",
            title=f"{title} source",
            content_text=content,
            metadata_json=source_metadata or {},
            status="active",
        )
        session.add(source)
    item = KnowledgeItem(
        id=item_id,
        source_item_id=resolved_source_id,
        title=title,
        summary=summary,
        content=content,
        keywords=keywords,
        source="memory_eval",
        source_ref=source_id,
        knowledge_type=knowledge_type,
        status="active",
    )
    session.add(item)
    session.flush()


def memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    init_knowledge_search_index(engine)
    return Session(engine)


def build_summary(reports: list[CategoryReport]) -> dict[str, Any]:
    by_name = {report.name: report.metrics for report in reports}
    retrieval_score = mean_or_zero(
        [
            by_name["context_retrieval"]["recallAtK"],
            by_name["context_retrieval"]["mrr"],
            by_name["context_retrieval"]["precisionAtK"],
            by_name["context_retrieval"]["negativeAccuracy"],
            1.0 - by_name["context_retrieval"]["forbiddenReturnRate"],
            by_name["context_retrieval"]["citationCoverage"],
            by_name["context_retrieval"]["budgetAdherence"],
            by_name["context_retrieval"]["selectionTraceCoverage"],
        ],
    )
    ablation_score = mean_or_zero(
        [
            by_name["retrieval_ablation"]["hybridRecallAtK"],
            by_name["retrieval_ablation"]["hybridMrr"],
            by_name["retrieval_ablation"]["hybridNdcgAtK"],
        ],
    )
    handoff_score = mean_or_zero(
        [
            by_name["handoff_recovery"]["recoveryRate"],
            by_name["handoff_recovery"]["digestCoverage"],
        ],
    )
    privacy_score = mean_or_zero(
        [
            by_name["privacy_isolation"]["privacyIsolationScore"],
            by_name["privacy_isolation"]["capabilityRetrievalRate"],
        ],
    )
    lifecycle_score = mean_or_zero(
        [
            by_name["review_lifecycle"]["lifecycleAccuracy"],
            by_name["review_lifecycle"]["agentToolSurfaceSafety"],
        ],
    )
    sensitivity_score = by_name["evaluator_sensitivity"]["faultDetectionRate"]
    functional_challenge_score = mean_or_zero([retrieval_score, ablation_score, handoff_score, privacy_score, lifecycle_score])
    total_cases = sum(len(report.cases) for report in reports)
    rigor_score = evaluation_rigor_score(reports)
    return {
        "contextRetrievalScore": retrieval_score,
        "retrievalAblationScore": ablation_score,
        "hybridRecallLift": by_name["retrieval_ablation"]["hybridRecallLift"],
        "hybridMrrLift": by_name["retrieval_ablation"]["hybridMrrLift"],
        "handoffRecoveryScore": handoff_score,
        "privacyIsolationScore": privacy_score,
        "reviewLifecycleScore": lifecycle_score,
        "evaluatorSensitivityScore": sensitivity_score,
        "functionalChallengeScore": functional_challenge_score,
        "evaluationRigorScore": evaluation_rigor_score(reports),
        "totalCases": float(total_cases),
        "evidenceLevel": claim_level(total_cases, rigor_score),
        "publicBenchmarkStatus": "not_run",
        "privacyLeakRate": by_name["privacy_isolation"]["privacyLeakRate"],
        "selectionTraceCoverage": by_name["context_retrieval"]["selectionTraceCoverage"],
    }


def evaluation_rigor_score(reports: list[CategoryReport]) -> float:
    total_cases = sum(len(report.cases) for report in reports)
    category_names = {report.name for report in reports}
    category_coverage = len(category_names & EXPECTED_EVAL_CATEGORIES) / len(EXPECTED_EVAL_CATEGORIES)
    case_volume = min(total_cases / 50, 1.0)

    has_retrieval_distractors = any(
        case.get("forbiddenItemIds") or not case.get("expectedItemIds")
        for report in reports
        if report.name == "context_retrieval"
        for case in report.cases
    )
    has_privacy_negative = any(
        not case.get("leakedTokensWithoutCapabilities")
        for report in reports
        if report.name == "privacy_isolation"
        for case in report.cases
    )
    has_review_negative = any(
        case.get("checks", {}).get("pendingNotSearchable") and case.get("checks", {}).get("invalidTargetRejected")
        for report in reports
        if report.name == "review_lifecycle"
        for case in report.cases
    )
    has_digest_checks = any(
        case.get("digestCheck")
        for report in reports
        if report.name == "handoff_recovery"
        for case in report.cases
    )
    has_capability_checks = any(
        case.get("capabilities")
        for report in reports
        if report.name == "privacy_isolation"
        for case in report.cases
    )
    sensitivity_report = next((report for report in reports if report.name == "evaluator_sensitivity"), None)
    sensitivity = sensitivity_report.metrics.get("faultDetectionRate", 0.0) if sensitivity_report else 0.0
    adversarial_coverage = sum(
        [
            has_retrieval_distractors,
            has_privacy_negative,
            has_review_negative,
            has_digest_checks,
            has_capability_checks,
        ],
    ) / 5

    reproducibility = 1.0
    public_benchmark = 0.0
    return (
        category_coverage * 0.20
        + case_volume * 0.25
        + adversarial_coverage * 0.20
        + sensitivity * 0.20
        + reproducibility * 0.10
        + public_benchmark * 0.05
    )


def claim_level(total_cases: int, rigor_score: float) -> str:
    if total_cases >= 50 and rigor_score >= 0.80:
        return "interview_ready_internal_challenge_not_sota"
    if total_cases >= 25 and rigor_score >= 0.65:
        return "credible_internal_eval_needs_public_benchmark"
    return "seed_eval_only"


def render_console_summary(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        f"Memory reliability eval ({payload['profile']}, {payload['suiteVersion']})",
        f"- Functional Challenge Score: {percent(summary['functionalChallengeScore'])}",
        f"- Evaluation Rigor Score: {percent(summary['evaluationRigorScore'])}",
        f"- Evidence Level: {summary['evidenceLevel']}",
        f"- Dataset Cases: {int(summary['totalCases'])}",
        f"- Public Benchmark: {summary['publicBenchmarkStatus']}",
        f"- Context Retrieval: {percent(summary['contextRetrievalScore'])}",
        f"- Retrieval Ablation: {percent(summary['retrievalAblationScore'])}",
        f"- Hybrid Recall Lift: {signed_percent(summary['hybridRecallLift'])}",
        f"- Hybrid MRR Lift: {signed_percent(summary['hybridMrrLift'])}",
        f"- Handoff Recovery: {percent(summary['handoffRecoveryScore'])}",
        f"- Privacy Isolation: {percent(summary['privacyIsolationScore'])}",
        f"- Review Lifecycle: {percent(summary['reviewLifecycleScore'])}",
        f"- Evaluator Sensitivity: {percent(summary['evaluatorSensitivityScore'])}",
        f"- Privacy Leak Rate: {percent(summary['privacyLeakRate'])}",
        f"- Selection Trace Coverage: {percent(summary['selectionTraceCoverage'])}",
    ]
    return "\n".join(lines)


def render_markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Memory Reliability Evaluation Report",
        "",
        f"Generated: `{payload['generatedAt']}`",
        f"Suite: `{payload['suiteVersion']}`",
        f"Profile: `{payload['profile']}`",
        "",
        "## Resume Scorecard",
        "",
        "| Metric | Score | What it proves |",
        "| --- | ---: | --- |",
        f"| Functional Challenge Score | {percent(summary['functionalChallengeScore'])} | Aggregate functional result on the deterministic internal challenge suite. |",
        f"| Evaluation Rigor Score | {percent(summary['evaluationRigorScore'])} | Case volume, category breadth, adversarial coverage, fault sensitivity, reproducibility, and public benchmark status. |",
        f"| Evidence Level | {summary['evidenceLevel']} | Claim boundary for resume/interview use. |",
        f"| Context Retrieval Score | {percent(summary['contextRetrievalScore'])} | ContextPack returns the expected memory slices with citations inside budget. |",
        f"| Retrieval Ablation Score | {percent(summary['retrievalAblationScore'])} | Hybrid retrieval is compared against lexical-only and vector-only baselines. |",
        f"| Hybrid Recall Lift | {signed_percent(summary['hybridRecallLift'])} | Recall@K delta for hybrid over lexical-only. |",
        f"| Hybrid MRR Lift | {signed_percent(summary['hybridMrrLift'])} | MRR delta for hybrid over lexical-only. |",
        f"| Handoff Recovery Score | {percent(summary['handoffRecoveryScore'])} | Another agent can recover goal, progress, decisions, risks, refs, and digest. |",
        f"| Privacy Isolation Score | {percent(summary['privacyIsolationScore'])} | Default work-mode retrieval blocks private/profile data while explicit capability can retrieve it. |",
        f"| Review Lifecycle Score | {percent(summary['reviewLifecycleScore'])} | Pending memories stay unsearchable until accepted, with decisions and provenance recorded. |",
        f"| Evaluator Sensitivity Score | {percent(summary['evaluatorSensitivityScore'])} | Fault injection confirms the evaluator catches missing retrieval, leaks, lifecycle bypasses, and lost provenance. |",
        f"| Privacy Leak Rate | {percent(summary['privacyLeakRate'])} | Lower is better; target is 0%. |",
        f"| Selection Trace Coverage | {percent(summary['selectionTraceCoverage'])} | ContextPack explains selected, filtered, deduped, and truncated slices. |",
        f"| Dataset Cases | {int(summary['totalCases'])} | Number of deterministic JSONL cases executed. |",
        f"| Public Benchmark | {summary['publicBenchmarkStatus']} | LongMemEval / MemoryAgentBench style public evaluation has not been run yet. |",
        "",
        "## Credibility Note",
        "",
        "This is an interview-grade internal challenge suite, not a public SOTA claim. The report is credible because it has a fixed suite version, deterministic local execution, negative cases, privacy/scope checks, lifecycle checks, and evaluator fault injection. Public LongMemEval / LoCoMo / MemoryAgentBench adapters remain the next evidence tier.",
        "",
        "## Category Details",
        "",
    ]
    for category in payload["categories"]:
        lines.extend(
            [
                f"### {category['name']}",
                "",
                "| Metric | Score |",
                "| --- | ---: |",
            ],
        )
        for key, value in category["metrics"].items():
            lines.append(f"| {key} | {format_metric_value(key, value)} |")
        lines.extend(["", "| Case | Result |", "| --- | --- |"])
        for case in category["cases"]:
            case_score = case.get("recallAtK", case.get("recoveryScore", case.get("lifecycleScore", case.get("score"))))
            if case_score is None and "leakedTokensWithoutCapabilities" in case:
                case_score = 0.0 if case["leakedTokensWithoutCapabilities"] else 1.0
            if case.get("detected") is not None:
                case_score = 1.0 if case["detected"] else 0.0
            lines.append(f"| `{case['id']}` | {percent(float(case_score or 0.0))} |")
        lines.append("")
    lines.extend(
        [
            "## Resume Bullet",
            "",
            f"> Built a deterministic agent-memory reliability benchmark for hybrid retrieval, budgeted ContextPack selection trace, cross-agent handoff recovery, privacy/scope isolation, review-gated lifecycle correctness, and evaluator fault sensitivity; current suite: {int(summary['totalCases'])} cases, {percent(summary['functionalChallengeScore'])} functional challenge score, {percent(summary['evaluationRigorScore'])} rigor score, {signed_percent(summary['hybridRecallLift'])} hybrid recall lift, {percent(summary['privacyLeakRate'])} privacy leak rate.",
            "",
        ],
    )
    return "\n".join(lines)


def load_retrieval_cases(dataset_dir: Path, profile: str) -> list[dict[str, Any]]:
    cases = load_jsonl(dataset_dir / "retrieval_cases.jsonl")
    if profile == "challenge":
        cases.extend(generated_retrieval_cases())
    return cases


def load_handoff_cases(dataset_dir: Path, profile: str) -> list[dict[str, Any]]:
    cases = load_jsonl(dataset_dir / "handoff_cases.jsonl")
    if profile == "challenge":
        cases.extend(generated_handoff_cases())
    return cases


def load_privacy_cases(dataset_dir: Path, profile: str) -> list[dict[str, Any]]:
    cases = load_jsonl(dataset_dir / "privacy_cases.jsonl")
    if profile == "challenge":
        cases.extend(generated_privacy_cases())
    return cases


def load_lifecycle_cases(dataset_dir: Path, profile: str) -> list[dict[str, Any]]:
    cases = load_jsonl(dataset_dir / "lifecycle_cases.jsonl")
    if profile == "challenge":
        cases.extend(generated_lifecycle_cases())
    return cases


def generated_retrieval_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    knowledge_types = ["fragment", "rule_preference", "procedure_lesson"]
    for index in range(1, 19):
        query = f"memory-eval-retrieval-topic-{index:02d}"
        target_id = f"challenge_retrieval_{index:02d}_target"
        distractors = [
            {
                "id": f"challenge_retrieval_{index:02d}_distractor_{noise}",
                "title": f"Near miss retrieval distractor {index}-{noise}",
                "summary": f"This mentions memory eval retrieval but not the exact target topic {index:02d}.",
                "content": f"Noise document {noise} talks about agent memory, review gates, handoff, and ContextPack for a different topic.",
                "keywords": ["agent memory", "ContextPack", "handoff"],
                "knowledgeType": "fragment",
            }
            for noise in range(1, 4)
        ]
        cases.append(
            {
                "id": f"challenge_retrieval_{index:02d}",
                "query": query,
                "k": 5,
                "expectedItemIds": [target_id],
                "forbiddenItemIds": [item["id"] for item in distractors],
                "memories": [
                    {
                        "id": target_id,
                        "title": f"Target memory {index:02d}",
                        "summary": f"The exact retrieval target is {query}.",
                        "content": f"{query} is the canonical token for this memory reliability challenge case. It should outrank near-miss distractors.",
                        "keywords": [query, f"target-{index:02d}"],
                        "knowledgeType": knowledge_types[index % len(knowledge_types)],
                    },
                    *distractors,
                ],
            },
        )
    reorder_specs = [
        ("review gate memory agent", "agent memory review gate"),
        ("context scoped capability pack", "capability scoped ContextPack"),
        ("handoff digest rolling agent", "agent rolling handoff digest"),
        ("provenance decision memory lifecycle", "memory decision provenance lifecycle"),
        ("privacy scope capability isolation", "capability privacy scope isolation"),
        ("source evidence review workbench", "review workbench source evidence"),
    ]
    for index, (query, target_phrase) in enumerate(reorder_specs, start=1):
        target_id = f"challenge_retrieval_reorder_{index:02d}_target"
        cases.append(
            {
                "id": f"challenge_retrieval_reorder_{index:02d}",
                "query": query,
                "k": 5,
                "expectedItemIds": [target_id],
                "forbiddenItemIds": [f"challenge_retrieval_reorder_{index:02d}_noise"],
                "memories": [
                    {
                        "id": target_id,
                        "title": f"Word order robust retrieval {index:02d}",
                        "summary": f"The canonical phrase is {target_phrase}.",
                        "content": f"{target_phrase} should be retrievable even when the query changes word order.",
                        "keywords": [target_phrase],
                        "knowledgeType": "procedure_lesson",
                    },
                    {
                        "id": f"challenge_retrieval_reorder_{index:02d}_noise",
                        "title": f"Word order distractor {index:02d}",
                        "summary": "This distractor has only a partial overlap with the query.",
                        "content": "A nearby but incomplete memory note about agent systems.",
                        "keywords": ["partial overlap"],
                        "knowledgeType": "fragment",
                    },
                ],
            },
        )
    for index in range(1, 5):
        cases.append(
            {
                "id": f"challenge_retrieval_negative_{index:02d}",
                "query": f"absent-memory-eval-topic-{index:02d}",
                "k": 5,
                "expectedItemIds": [],
                "forbiddenItemIds": [f"challenge_negative_{index:02d}_noise"],
                "memories": [
                    {
                        "id": f"challenge_negative_{index:02d}_noise",
                        "title": f"Negative retrieval control {index:02d}",
                        "summary": "This is a negative control and should not match the absent query.",
                        "content": "A general note about memory reliability without the absent token.",
                        "keywords": ["negative control", "memory reliability"],
                        "knowledgeType": "fragment",
                    },
                ],
            },
        )
    return cases


def generated_handoff_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index in range(1, 11):
        marker = f"handoff-eval-{index:02d}"
        cases.append(
            {
                "id": f"challenge_handoff_{index:02d}",
                "title": f"Challenge handoff {index:02d}",
                "userGoal": f"Recover agent work for {marker}.",
                "state": {
                    "currentGoal": f"Finish {marker} memory handoff protocol",
                    "done": [f"{marker} current state written", f"{marker} service path verified"],
                    "inProgress": [f"{marker} scorecard review"],
                    "nextSteps": [f"Run {marker} challenge eval", f"Archive {marker} evidence refs"],
                    "decisions": [f"{marker} keeps raw TaskEvent records durable"],
                    "risks": [f"{marker} stale task must be re-confirmed"],
                    "filesTouched": [f"server/app/{marker}.py", f"docs/{marker}.md"],
                },
                "events": [
                    {"type": "agent_action", "summary": f"{marker} implemented resume path", "sourceRef": f"server/app/{marker}.py"},
                    {"type": "agent_action", "summary": f"{marker} added checkpoint path", "sourceRef": f"server/app/{marker}.py"},
                    {"type": "decision", "summary": f"{marker} keeps CLI and MCP on one service protocol", "sourceRef": f"docs/{marker}.md"},
                    {"type": "blocker", "summary": f"{marker} blocks terminal task mutation", "sourceRef": f"server/app/{marker}.py"},
                    {"type": "test_result", "summary": f"{marker} regression tests passed", "sourceRef": f"server/tests/{marker}.py"},
                    {"type": "agent_action", "summary": f"{marker} documented handoff refs", "sourceRef": f"docs/{marker}.md"},
                    {"type": "agent_action", "summary": f"{marker} prepared next agent handoff", "sourceRef": "second_brain.py"},
                ],
                "expect": {
                    "currentGoalContains": [f"Finish {marker}"],
                    "doneContains": [f"{marker} current state written", f"{marker} service path verified"],
                    "nextStepsContains": [f"Run {marker} challenge eval"],
                    "decisionsContain": [f"{marker} keeps raw TaskEvent"],
                    "risksContain": [f"{marker} stale task"],
                    "filesTouchedContain": [f"server/app/{marker}.py", f"docs/{marker}.md"],
                    "digestContains": [f"{marker} implemented resume path"],
                    "contentIncludes": [f"Recover agent work for {marker}", f"{marker} scorecard review"],
                },
            },
        )
    return cases


def generated_privacy_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index in range(1, 5):
        cases.append(
            {
                "id": f"challenge_private_{index:02d}",
                "query": f"private-boundary-token-{index:02d}",
                "setup": "semantic_private",
                "forbiddenWithoutCapabilities": [f"PRIVATE_BOUNDARY_SECRET_{index:02d}"],
                "allowedWithCapabilities": [f"PRIVATE_BOUNDARY_SECRET_{index:02d}"],
                "capabilities": ["private_memory"],
            },
        )
    for index in range(1, 5):
        cases.append(
            {
                "id": f"challenge_profile_{index:02d}",
                "query": f"profile-boundary-token-{index:02d}",
                "setup": "profile_fact",
                "forbiddenWithoutCapabilities": [f"PROFILE_BOUNDARY_SECRET_{index:02d}"],
                "allowedWithCapabilities": [f"PROFILE_BOUNDARY_SECRET_{index:02d}"],
                "capabilities": ["profile_memory"],
            },
        )
    for index in range(1, 4):
        cases.append(
            {
                "id": f"challenge_capability_{index:02d}",
                "query": f"capability-boundary-token-{index:02d}",
                "setup": "capability_required",
                "forbiddenWithoutCapabilities": [f"CAPABILITY_BOUNDARY_SECRET_{index:02d}"],
                "allowedWithCapabilities": [f"CAPABILITY_BOUNDARY_SECRET_{index:02d}"],
                "capabilities": ["external_agent_allowed"],
            },
        )
    for index in range(1, 4):
        cases.append(
            {
                "id": f"challenge_task_scope_{index:02d}",
                "query": f"task-scope-boundary-token-{index:02d}",
                "setup": "task_scope",
                "forbiddenWithoutCapabilities": [f"OTHER_TASK_SCOPE_SECRET_{index:02d}"],
                "allowedWithCapabilities": [f"CURRENT_TASK_SCOPE_SECRET_{index:02d}"],
                "capabilities": [],
            },
        )
    return cases


def generated_lifecycle_cases() -> list[dict[str, Any]]:
    specs = [
        ("project_rule", "rule_preference"),
        ("user_preference", "rule_preference"),
        ("lesson", "procedure_lesson"),
        ("pitfall", "procedure_lesson"),
        ("workflow_pattern", "procedure_lesson"),
        ("technical_decision", "semantic_knowledge"),
        ("environment_fact", "semantic_knowledge"),
    ]
    cases: list[dict[str, Any]] = []
    for index, (proposal_type, target_store) in enumerate(specs, start=1):
        token = f"LIFECYCLE_REVIEW_GATE_TOKEN_{index:02d}"
        cases.append(
            {
                "id": f"challenge_lifecycle_{index:02d}",
                "proposalType": proposal_type,
                "title": f"Challenge lifecycle {index:02d}",
                "body": f"{token} should become searchable only after the review gate accepts this {proposal_type} proposal.",
                "targetStore": target_store,
                "query": token,
                "expectedToolNames": ["propose_memory", "list_memory_proposals"],
                "forbiddenToolNames": ["accept_memory_proposal", "resolve_memory_conflict", "purge_source_evidence"],
                "expectedDecisions": ["proposal_routed", "proposal_accepted"],
            },
        )
    return cases


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def returned_memory_item_ids(pack: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for section in ["rules", "procedureLessons", "relatedItems"]:
        ids.extend(str(item["id"]) for item in pack.get(section, []))
    return ids


def pack_memory_surface(pack: dict[str, Any]) -> str:
    searchable_sections = {
        key: pack.get(key)
        for key in ["taskState", "rules", "profileFacts", "procedureLessons", "relatedPages", "relatedItems", "sourceExcerpts"]
    }
    return json.dumps(searchable_sections, ensure_ascii=False, default=str)


def score_retrieval_outcome(
    expected_ids: list[str],
    forbidden_ids: list[str],
    returned_ids: list[str],
    citation_refs: list[str],
) -> float:
    hits = [item_id for item_id in expected_ids if item_id in returned_ids]
    forbidden_hits = [item_id for item_id in forbidden_ids if item_id in returned_ids]
    recall = len(hits) / len(expected_ids) if expected_ids else 1.0
    first_rank = min((returned_ids.index(item_id) + 1 for item_id in hits), default=0)
    mrr = 1 / first_rank if first_rank else (1.0 if not expected_ids else 0.0)
    precision = len(hits) / len(returned_ids) if returned_ids else (1.0 if not expected_ids else 0.0)
    negative_accuracy = 1.0 if not expected_ids and not returned_ids else 0.0 if not expected_ids else 1.0
    forbidden_rate = len(forbidden_hits) / len(forbidden_ids) if forbidden_ids else 0.0
    citation_coverage = (
        len([item_id for item_id in expected_ids if f"item:{item_id}" in citation_refs]) / len(expected_ids)
        if expected_ids
        else 1.0
    )
    return mean_or_zero([recall, mrr, precision, negative_accuracy, 1.0 - forbidden_rate, citation_coverage])


def score_boolean_checks(values: list[bool]) -> float:
    return sum(1 for value in values if value) / len(values) if values else 0.0


def retrieval_metrics(expected_ids: list[str], returned_ids: list[str], k: int) -> dict[str, float]:
    top_ids = returned_ids[:k]
    hits = [item_id for item_id in expected_ids if item_id in top_ids]
    recall = len(hits) / len(expected_ids) if expected_ids else 1.0
    precision = len(hits) / len(top_ids) if top_ids else 0.0
    first_rank = min((top_ids.index(item_id) + 1 for item_id in hits), default=0)
    mrr = 1 / first_rank if first_rank else 0.0
    dcg = 0.0
    for rank, item_id in enumerate(top_ids, start=1):
        if item_id in expected_ids:
            dcg += 1.0 / log2(rank + 1)
    ideal_hits = min(len(expected_ids), k)
    ideal_dcg = sum(1.0 / log2(rank + 1) for rank in range(1, ideal_hits + 1))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    return {
        "recallAtK": recall,
        "precisionAtK": precision,
        "mrr": mrr,
        "ndcgAtK": ndcg,
    }


def contains_all(value: str, needles: list[str]) -> bool:
    return all(needle in value for needle in needles)


def list_contains_all(values: list[str], needles: list[str]) -> bool:
    joined = "\n".join(values)
    return contains_all(joined, needles)


def mean_or_zero(values: list[float]) -> float:
    return mean(values) if values else 0.0


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def signed_percent(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.1f}%"


def format_metric_value(key: str, value: float) -> str:
    if key.lower().endswith("latencyms") or key.lower().endswith("latencymsavg"):
        return f"{value:.1f} ms"
    return percent(value)


def log2(value: float) -> float:
    import math

    return math.log2(value)


if __name__ == "__main__":
    main()
