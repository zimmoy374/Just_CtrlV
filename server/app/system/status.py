from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from ..models import (
    AnalysisJob,
    HandoffPack,
    MemoryProposal,
    ProvenanceEvent,
    SourceItem,
    TaskDigest,
    TaskEvent,
    TaskSession,
    utc_now,
)
from ..settings import settings
from ..tasks.state_machine import ACTIVE_TASK_SESSION_STATUSES


def collect_system_status(session: Session) -> dict[str, Any]:
    tasks = list(session.exec(select(TaskSession)).all())
    jobs = list(session.exec(select(AnalysisJob)).all())
    proposals = list(session.exec(select(MemoryProposal)).all())
    recent_events = list(
        session.exec(select(ProvenanceEvent).order_by(ProvenanceEvent.occurred_at.desc()).limit(10)).all(),
    )
    active_tasks = [task for task in tasks if task.status in ACTIVE_TASK_SESSION_STATUSES]
    failed_jobs = [job for job in jobs if job.status == "failed"]
    running_jobs = [job for job in jobs if job.status == "running"]
    pending_jobs = [job for job in jobs if job.status == "pending"]
    pending_proposals = [proposal for proposal in proposals if proposal.status == "pending"]

    data_dir = Path(settings.data_dir)
    upload_dir = Path(settings.upload_dir)
    return {
        "ok": True,
        "generatedAt": utc_now().isoformat(),
        "storage": {
            "dataDir": str(data_dir),
            "dataDirExists": data_dir.exists(),
            "uploadDir": str(upload_dir),
            "uploadDirExists": upload_dir.exists(),
            "databaseUrl": settings.database_url,
        },
        "tasks": {
            "total": len(tasks),
            "active": len(active_tasks),
            "byStatus": _count_by(tasks, "status"),
            "recentActive": [
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "activeAgent": task.active_agent,
                    "updatedAt": task.updated_at.isoformat(),
                }
                for task in sorted(active_tasks, key=lambda task: task.updated_at, reverse=True)[:5]
            ],
        },
        "analysisJobs": {
            "total": len(jobs),
            "pending": len(pending_jobs),
            "running": len(running_jobs),
            "failed": len(failed_jobs),
            "byStatus": _count_by(jobs, "status"),
        },
        "memory": {
            "sourceItems": len(session.exec(select(SourceItem.id)).all()),
            "pendingProposals": len(pending_proposals),
            "handoffPacks": len(session.exec(select(HandoffPack.id)).all()),
            "taskDigests": len(session.exec(select(TaskDigest.task_session_id)).all()),
        },
        "recentProvenance": [
            {
                "id": event.id,
                "type": event.event_type,
                "from": event.from_ref,
                "to": event.to_ref,
                "actor": event.actor,
                "occurredAt": event.occurred_at.isoformat(),
            }
            for event in recent_events
        ],
        "warnings": _status_warnings(active_tasks=active_tasks, failed_jobs=failed_jobs, pending_proposals=pending_proposals),
    }


def _count_by(items: list[Any], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(getattr(item, field_name, "") or "")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _status_warnings(
    *,
    active_tasks: list[TaskSession],
    failed_jobs: list[AnalysisJob],
    pending_proposals: list[MemoryProposal],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if len(active_tasks) > 3:
        warnings.append({"type": "many_active_tasks", "message": "活跃任务较多，建议归档或关闭已完成任务。"})
    if failed_jobs:
        warnings.append({"type": "failed_analysis_jobs", "message": f"存在 {len(failed_jobs)} 个失败分析任务。"})
    if len(pending_proposals) > 20:
        warnings.append({"type": "many_pending_proposals", "message": "待审记忆较多，建议进入记忆审查台处理。"})
    return warnings
