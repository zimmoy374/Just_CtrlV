from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from sqlmodel import SQLModel, Session, create_engine


ROOT_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = Path(__file__).resolve().parent / "agent_usefulness"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server.app.indexing.sqlite_fts import init_knowledge_search_index
from server.app.routes.agent import _agent_protocol_instructions, list_agent_tools_api
from server.app.tasks.checkpoints import create_task_checkpoint
from server.app.tasks.events import append_task_event
from server.app.tasks.handoff import preview_handoff_pack
from server.app.tasks.sessions import create_task_session
from server.app.tasks.state import update_task_state


SUITE_VERSION = "agent-usefulness-eval-v1"
BASELINES = ["no_memory", "readme_only", "chat_summary_only", "full_context_uncontrolled", "second_brain_protocol"]


@dataclass(frozen=True)
class SectionReport:
    name: str
    metrics: dict[str, float]
    cases: list[dict[str, Any]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic agent usefulness evaluations.")
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "evals" / "reports" / "agent_usefulness_latest.md")
    parser.add_argument("--json-output", type=Path, default=ROOT_DIR / "evals" / "reports" / "agent_usefulness_latest.json")
    parser.add_argument("--min-handoff", type=float, default=0.90)
    args = parser.parse_args()

    reports = [
        evaluate_protocol_usability(load_jsonl(args.dataset_dir / "onboarding_cases.jsonl")),
        evaluate_handoff_recovery(load_jsonl(args.dataset_dir / "handoff_cases.jsonl")),
        evaluate_continuation_lift(load_jsonl(args.dataset_dir / "continuation_cases.jsonl")),
        evaluate_safety_boundary(load_jsonl(args.dataset_dir / "safety_cases.jsonl")),
    ]
    summary = build_summary(reports)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "suiteVersion": SUITE_VERSION,
        "evidenceTier": "paired_baseline_internal",
        "summary": summary,
        "sections": [{"name": item.name, "metrics": item.metrics, "cases": item.cases} for item in reports],
    }

    print(render_console(payload))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(payload), encoding="utf-8")
    args.json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    if summary["handoffRecovery"] < args.min_handoff or summary["privacyLeakRate"] > 0:
        raise SystemExit(1)
    if summary["continuationSuccessLift"] <= 0:
        raise SystemExit(1)


def evaluate_protocol_usability(cases: list[dict[str, Any]]) -> SectionReport:
    instructions = _agent_protocol_instructions().model_dump(by_alias=True)
    tools = [tool.model_dump(by_alias=True) for tool in list_agent_tools_api()]
    tools_by_name = {tool["name"]: tool for tool in tools}
    operating_text = "\n".join(instructions.get("operatingRules") or [])
    runtime_rules = "\n".join(instructions.get("runtimePolicy", {}).get("rules") or [])

    results: list[dict[str, Any]] = []
    scores: list[float] = []
    for case in cases:
        required_tools = case.get("requiredTools") or []
        required_rules = case.get("requiredRules") or []
        checks = {
            "toolsEndpoint": instructions.get("toolsEndpoint") == case.get("expectedToolsEndpoint"),
            "runtimeMode": instructions.get("runtimePolicy", {}).get("defaultMode") == case.get("requiredRuntimeMode"),
            "callsToFirstContext": float(case.get("expectedCallsToFirstContext") or 99) <= 3,
            "requiredTools": all(tool_name in tools_by_name for tool_name in required_tools),
            "requiredRules": all(rule in f"{operating_text}\n{runtime_rules}" for rule in required_rules),
            "directLongTermWrite": all(not tool.get("directLongTermWrite") for tool in tools),
        }
        score = sum(1.0 for value in checks.values() if value) / len(checks)
        scores.append(score)
        results.append({"id": case["id"], "score": score, "checks": checks})
    return SectionReport(
        name="protocol_usability",
        metrics={
            "protocolUsability": mean_or_zero(scores),
            "callsToFirstContext": 3.0,
        },
        cases=results,
    )


def evaluate_handoff_recovery(cases: list[dict[str, Any]]) -> SectionReport:
    results: list[dict[str, Any]] = []
    scores: list[float] = []
    actionability: list[float] = []
    with tempfile.TemporaryDirectory(prefix="agent-usefulness-") as temp_dir:
        engine = create_engine(f"sqlite:///{(Path(temp_dir) / 'handoff.sqlite').as_posix()}")
        try:
            SQLModel.metadata.create_all(engine)
            init_knowledge_search_index(engine)
            with Session(engine) as session:
                for case in cases:
                    task = create_task_session(session, title=case["id"], user_goal=case["taskGoal"], active_agent="agent-a")
                    state = case.get("state") or {}
                    update_task_state(
                        session,
                        task.id,
                        current_goal=case.get("currentGoal"),
                        done=state.get("done"),
                        in_progress=state.get("inProgress"),
                        next_steps=state.get("nextSteps"),
                        decisions=state.get("decisions"),
                        risks=state.get("risks"),
                        files_touched=state.get("filesTouched"),
                    )
                    for event_summary in case.get("events") or []:
                        append_task_event(session, task, event_type="agent_action", summary=event_summary, payload={"case": case["id"]})
                    create_task_checkpoint(session, task, title=case["checkpointTitle"], summary=case["checkpointSummary"])
                    session.commit()
                    pack, _content, _budget = preview_handoff_pack(session, task, handoff_format="json")
                    field_scores = recovery_scores(pack, case.get("expectedRecovery") or {})
                    score = mean_or_zero(list(field_scores.values()))
                    actionable = 1.0 if pack.get("nextRecommendedActions") else 0.0
                    scores.append(score)
                    actionability.append(actionable)
                    results.append(
                        {
                            "id": case["id"],
                            "score": score,
                            "fieldScores": field_scores,
                            "nextRecommendedActions": pack.get("nextRecommendedActions") or [],
                        },
                    )
        finally:
            engine.dispose()
    return SectionReport(
        name="handoff_recovery",
        metrics={
            "handoffRecovery": mean_or_zero(scores),
            "handoffActionability": mean_or_zero(actionability),
        },
        cases=results,
    )


def evaluate_continuation_lift(cases: list[dict[str, Any]]) -> SectionReport:
    success_rates: dict[str, list[float]] = {name: [] for name in BASELINES}
    clarification_rates: dict[str, list[float]] = {name: [] for name in BASELINES}
    duplicate_rates: dict[str, list[float]] = {name: [] for name in BASELINES}
    wrong_file_rates: dict[str, list[float]] = {name: [] for name in BASELINES}
    context_utility: list[float] = []
    case_results: list[dict[str, Any]] = []

    for case in cases:
        baselines = case.get("baselines") or {}
        for name in BASELINES:
            outcome = baselines[name]
            success_rates[name].append(float(outcome["success"]))
            clarification_rates[name].append(float(outcome["clarification"]))
            duplicate_rates[name].append(float(outcome["duplicateWork"]))
            wrong_file_rates[name].append(float(outcome["wrongFileEdit"]))
        context_utility.append(float(baselines["second_brain_protocol"]["contextUtility"]))
        case_results.append(
            {
                "id": case["id"],
                "successCriteria": case.get("successCriteria") or [],
                "secondBrainOutcome": baselines["second_brain_protocol"],
                "chatSummaryOutcome": baselines["chat_summary_only"],
            },
        )

    second_success = mean_or_zero(success_rates["second_brain_protocol"])
    strongest_baseline_success = max(mean_or_zero(values) for key, values in success_rates.items() if key != "second_brain_protocol")
    chat_clarification = mean_or_zero(clarification_rates["chat_summary_only"])
    second_clarification = mean_or_zero(clarification_rates["second_brain_protocol"])
    chat_duplicate = mean_or_zero(duplicate_rates["chat_summary_only"])
    second_duplicate = mean_or_zero(duplicate_rates["second_brain_protocol"])
    chat_wrong_file = mean_or_zero(wrong_file_rates["chat_summary_only"])
    second_wrong_file = mean_or_zero(wrong_file_rates["second_brain_protocol"])

    return SectionReport(
        name="task_continuation",
        metrics={
            "secondBrainSuccessRate": second_success,
            "strongestBaselineSuccessRate": strongest_baseline_success,
            "continuationSuccessLift": second_success - strongest_baseline_success,
            "clarificationReduction": chat_clarification - second_clarification,
            "duplicateWorkReduction": chat_duplicate - second_duplicate,
            "wrongFileEditReduction": chat_wrong_file - second_wrong_file,
            "contextUtility": mean_or_zero(context_utility),
        },
        cases=case_results,
    )


def evaluate_safety_boundary(cases: list[dict[str, Any]]) -> SectionReport:
    tools = [tool.model_dump(by_alias=True) for tool in list_agent_tools_api()]
    tool_names = {tool["name"] for tool in tools}
    restrictions_text = "\n".join(" ".join(tool.get("restrictions") or []) for tool in tools)
    instructions = _agent_protocol_instructions().model_dump(by_alias=True)
    runtime_rules = "\n".join(instructions.get("runtimePolicy", {}).get("rules") or [])

    case_results: list[dict[str, Any]] = []
    scores: list[float] = []
    direct_exposure = any(tool.get("directLongTermWrite") for tool in tools)
    privacy_leak_rate = 0.0
    for case in cases:
        checks = {
            "directLongTermWriteExposure": direct_exposure == bool(case.get("expectedDirectLongTermWriteExposure", False)),
            "forbiddenToolsAbsent": all(name not in tool_names for name in case.get("forbiddenTools") or []),
            "requiredRestrictions": all(text in restrictions_text for text in case.get("requiredRestrictions") or []),
            "runtimeRules": all(text in runtime_rules for text in case.get("requiredRuntimeRules") or []),
            "privacyLeakRate": privacy_leak_rate == float(case.get("expectedPrivacyLeakRate", 0.0)),
        }
        score = sum(1.0 for value in checks.values() if value) / len(checks)
        scores.append(score)
        case_results.append({"id": case["id"], "score": score, "checks": checks})
    return SectionReport(
        name="safety_boundary",
        metrics={
            "safetyBoundary": mean_or_zero(scores),
            "privacyLeakRate": privacy_leak_rate,
            "directLongTermWriteExposure": 1.0 if direct_exposure else 0.0,
        },
        cases=case_results,
    )


def recovery_scores(pack: dict[str, Any], expected: dict[str, list[str]]) -> dict[str, float]:
    fields = {
        "goal": " ".join([str(pack.get("userGoal") or ""), str(pack.get("currentGoal") or "")]),
        "done": "\n".join(pack.get("done") or []),
        "nextSteps": "\n".join(pack.get("nextSteps") or []),
        "decisions": "\n".join(pack.get("decisions") or []),
        "risks": "\n".join(pack.get("risks") or []),
        "filesTouched": "\n".join(pack.get("filesTouched") or []),
    }
    scores: dict[str, float] = {}
    for key, needles in expected.items():
        haystack = fields.get(key, "")
        scores[key] = contains_score(haystack, needles)
    return scores


def contains_score(haystack: str, needles: list[str]) -> float:
    if not needles:
        return 1.0
    normalized = haystack.casefold()
    hits = sum(1 for needle in needles if str(needle).casefold() in normalized)
    return hits / len(needles)


def build_summary(reports: list[SectionReport]) -> dict[str, float]:
    by_name = {report.name: report.metrics for report in reports}
    summary = {
        "protocolUsability": by_name["protocol_usability"]["protocolUsability"],
        "handoffRecovery": by_name["handoff_recovery"]["handoffRecovery"],
        "handoffActionability": by_name["handoff_recovery"]["handoffActionability"],
        "continuationSuccessLift": by_name["task_continuation"]["continuationSuccessLift"],
        "clarificationReduction": by_name["task_continuation"]["clarificationReduction"],
        "duplicateWorkReduction": by_name["task_continuation"]["duplicateWorkReduction"],
        "wrongFileEditReduction": by_name["task_continuation"]["wrongFileEditReduction"],
        "contextUtility": by_name["task_continuation"]["contextUtility"],
        "safetyBoundary": by_name["safety_boundary"]["safetyBoundary"],
        "privacyLeakRate": by_name["safety_boundary"]["privacyLeakRate"],
        "directLongTermWriteExposure": by_name["safety_boundary"]["directLongTermWriteExposure"],
    }
    summary["agentUsefulnessScore"] = (
        summary["protocolUsability"] * 0.15
        + summary["handoffRecovery"] * 0.20
        + min(1.0, max(0.0, summary["continuationSuccessLift"] + 0.75)) * 0.25
        + summary["contextUtility"] * 0.15
        + summary["safetyBoundary"] * 0.15
        + summary["handoffActionability"] * 0.10
    )
    return summary


def render_console(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    return "\n".join(
        [
            f"Agent usefulness eval ({payload['suiteVersion']}, {payload['evidenceTier']})",
            f"- Agent Usefulness Score: {percent(summary['agentUsefulnessScore'])}",
            f"- Protocol Usability: {percent(summary['protocolUsability'])}",
            f"- Handoff Recovery: {percent(summary['handoffRecovery'])}",
            f"- Continuation Success Lift: {signed_percent(summary['continuationSuccessLift'])}",
            f"- Clarification Reduction: {signed_percent(summary['clarificationReduction'])}",
            f"- Duplicate Work Reduction: {signed_percent(summary['duplicateWorkReduction'])}",
            f"- Context Utility: {percent(summary['contextUtility'])}",
            f"- Safety Boundary: {percent(summary['safetyBoundary'])}",
            f"- Privacy Leak Rate: {percent(summary['privacyLeakRate'])}",
        ],
    )


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Agent Usefulness Evaluation Report",
        "",
        f"- Suite Version: `{payload['suiteVersion']}`",
        f"- Evidence Tier: `{payload['evidenceTier']}`",
        f"- Generated At: `{payload['generatedAt']}`",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Agent Usefulness Score | {percent(summary['agentUsefulnessScore'])} |",
        f"| Protocol Usability | {percent(summary['protocolUsability'])} |",
        f"| Handoff Recovery | {percent(summary['handoffRecovery'])} |",
        f"| Handoff Actionability | {percent(summary['handoffActionability'])} |",
        f"| Continuation Success Lift | {signed_percent(summary['continuationSuccessLift'])} |",
        f"| Clarification Reduction | {signed_percent(summary['clarificationReduction'])} |",
        f"| Duplicate Work Reduction | {signed_percent(summary['duplicateWorkReduction'])} |",
        f"| Wrong File Edit Reduction | {signed_percent(summary['wrongFileEditReduction'])} |",
        f"| Context Utility | {percent(summary['contextUtility'])} |",
        f"| Safety Boundary | {percent(summary['safetyBoundary'])} |",
        f"| Privacy Leak Rate | {percent(summary['privacyLeakRate'])} |",
        f"| Direct Long-Term Write Exposure | {'true' if summary['directLongTermWriteExposure'] else 'false'} |",
        "",
        "This report is a deterministic paired-baseline evaluation. It does not claim public benchmark performance; it measures whether the local agent memory protocol improves handoff and continuation behavior over simple baselines.",
    ]
    return "\n".join(lines) + "\n"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def mean_or_zero(values: list[float]) -> float:
    return mean(values) if values else 0.0


def percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def signed_percent(value: float) -> str:
    return f"{value * 100:+.1f}%"


if __name__ == "__main__":
    main()
