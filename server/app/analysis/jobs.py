from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from .. import ai
from ..capture.cards_service import commit_card_knowledge_item, sync_card_source_item
from ..database import engine
from ..models import AnalysisJob, Card, utc_now


ANALYSIS_JOB_STATUSES = {"pending", "running", "succeeded", "failed", "canceled"}
RECOVERABLE_ANALYSIS_JOB_STATUSES = {"pending", "running"}


def enqueue_card_analysis(session: Session, card: Card, *, reason: str) -> AnalysisJob:
    job = AnalysisJob(
        id=str(uuid4()),
        card_id=card.id,
        status="pending",
        reason=reason,
        attempts=0,
    )
    card.ai_status = "pending"
    card.ai_error = None
    card.updated_at = utc_now()
    session.add(card)
    session.add(job)
    session.flush()
    return job


def run_analysis_job(job_id: str) -> None:
    with Session(engine) as session:
        job = session.get(AnalysisJob, job_id)
        if not job or job.status != "pending":
            return

        card = session.get(Card, job.card_id)
        if not card:
            _finish_job(job, "canceled", "卡片已不存在")
            session.add(job)
            session.commit()
            return

        _start_job(job)
        card.ai_status = "generating"
        card.ai_error = None
        card.updated_at = utc_now()
        session.add(job)
        session.add(card)
        session.commit()

        config_error = ai.get_ai_config_error()
        if config_error:
            _mark_card_failed(session, job, card, config_error)
            return

        try:
            payload = ai._analyze_with_provider(card)
            summary, keywords = ai._normalize_result(payload)
            if not summary and not keywords:
                raise ValueError("AI 返回为空")

            card = session.get(Card, job.card_id)
            if not card:
                _finish_job(job, "canceled", "卡片已不存在")
                session.add(job)
                session.commit()
                return

            card.summary = summary
            card.keywords = keywords
            card.ai_status = "done"
            card.ai_error = None
            card.updated_at = utc_now()
            session.add(card)
            commit_card_knowledge_item(session, card)
            _finish_job(job, "succeeded", None)
            session.add(job)
            session.commit()
        except Exception as exc:
            card = session.get(Card, job.card_id)
            if not card:
                _finish_job(job, "canceled", "卡片已不存在")
                session.add(job)
                session.commit()
                return
            _mark_card_failed(session, job, card, ai._friendly_ai_error(exc))


def run_card_analysis_now(card_id: str, *, reason: str = "manual") -> None:
    with Session(engine) as session:
        card = session.get(Card, card_id)
        if not card:
            return
        job = enqueue_card_analysis(session, card, reason=reason)
        session.commit()
        job_id = job.id
    run_analysis_job(job_id)


def recover_interrupted_analysis_jobs(session: Session) -> list[str]:
    jobs = session.exec(
        select(AnalysisJob).where(AnalysisJob.status.in_(RECOVERABLE_ANALYSIS_JOB_STATUSES)).order_by(AnalysisJob.created_at),
    ).all()
    recoverable_job_ids: list[str] = []
    for job in jobs:
        card = session.get(Card, job.card_id)
        if not card:
            _finish_job(job, "canceled", "卡片已不存在")
            session.add(job)
            continue
        if job.status == "running":
            job.status = "pending"
            job.updated_at = utc_now()
            job.error = "进程中断后自动恢复"
            card.ai_status = "pending"
            card.ai_error = None
            card.updated_at = utc_now()
            session.add(card)
            session.add(job)
        recoverable_job_ids.append(job.id)
    session.flush()
    return recoverable_job_ids


def run_recoverable_analysis_jobs(limit: int = 20) -> int:
    with Session(engine) as session:
        job_ids = recover_interrupted_analysis_jobs(session)
        session.commit()

    for job_id in job_ids[:limit]:
        run_analysis_job(job_id)
    return min(len(job_ids), limit)


def _start_job(job: AnalysisJob) -> None:
    now = utc_now()
    job.status = "running"
    job.attempts += 1
    job.started_at = now
    job.updated_at = now
    job.error = None


def _finish_job(job: AnalysisJob, status: str, error: str | None) -> None:
    if status not in ANALYSIS_JOB_STATUSES:
        raise ValueError(f"analysis job status 不支持：{status}")
    now = utc_now()
    job.status = status
    job.error = error
    job.updated_at = now
    job.finished_at = now


def _mark_card_failed(session: Session, job: AnalysisJob, card: Card, error: str) -> None:
    card.ai_status = "failed"
    card.ai_error = error
    card.updated_at = utc_now()
    session.add(card)
    sync_card_source_item(session, card)
    _finish_job(job, "failed", error)
    session.add(job)
    session.commit()
