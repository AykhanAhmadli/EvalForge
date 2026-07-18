from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from evalforge.enums import JobStatus
from evalforge.models import Job


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def enqueue_job(
    session: Session,
    *,
    kind: str,
    payload: dict[str, Any],
    priority: int = 0,
    run_after: datetime | None = None,
) -> Job:
    job = Job(
        kind=kind,
        payload=payload,
        priority=priority,
        run_after=run_after or utcnow(),
        status=JobStatus.queued.value,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def claim_next_job(session: Session, *, worker_id: str) -> Job | None:
    statement = (
        select(Job)
        .where(Job.status == JobStatus.queued.value, Job.run_after <= utcnow())
        .order_by(Job.priority.desc(), Job.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = session.execute(statement).scalars().first()
    if job is None:
        return None

    job.status = JobStatus.running.value
    job.locked_by = worker_id
    job.locked_at = utcnow()
    job.attempts += 1
    session.commit()
    session.refresh(job)
    return job


def complete_job(session: Session, job: Job) -> None:
    job.status = JobStatus.succeeded.value
    job.locked_by = None
    job.locked_at = None
    job.last_error = None
    session.commit()


def fail_job(session: Session, job: Job, error: str) -> None:
    if job.attempts < job.max_attempts:
        job.status = JobStatus.queued.value
    else:
        job.status = JobStatus.failed.value
    job.locked_by = None
    job.locked_at = None
    job.last_error = error
    session.commit()
