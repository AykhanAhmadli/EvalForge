from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
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


def claim_next_job(session: Session, *, worker_id: str, lease_seconds: int = 300) -> Job | None:
    now = utcnow()
    statement = (
        select(Job)
        .where(
            or_(
                and_(Job.status == JobStatus.queued.value, Job.run_after <= now),
                and_(Job.status == JobStatus.running.value, Job.lease_expires_at <= now),
            )
        )
        .order_by(Job.priority.desc(), Job.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = session.execute(statement).scalars().first()
    if job is None:
        return None

    job.status = JobStatus.running.value
    job.locked_by = worker_id
    job.locked_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.attempts += 1
    session.commit()
    session.refresh(job)
    return job


def complete_job(session: Session, job: Job) -> None:
    job.status = JobStatus.succeeded.value
    job.locked_by = None
    job.locked_at = None
    job.lease_expires_at = None
    job.last_error = None
    job.last_error_type = None
    job.completed_at = utcnow()
    session.commit()


def renew_job_lease(session: Session, job: Job, *, lease_seconds: int = 300) -> None:
    job.lease_expires_at = utcnow() + timedelta(seconds=lease_seconds)
    session.commit()


def fail_job(
    session: Session,
    job: Job,
    error: str,
    *,
    transient: bool = False,
    error_type: str | None = None,
) -> None:
    if transient and job.attempts < job.max_attempts:
        job.status = JobStatus.queued.value
        job.run_after = utcnow() + timedelta(seconds=min(60, 2**job.attempts))
    else:
        job.status = JobStatus.failed.value
    job.locked_by = None
    job.locked_at = None
    job.lease_expires_at = None
    job.last_error = error
    job.last_error_type = error_type
    if job.status == JobStatus.failed.value:
        job.failed_at = utcnow()
    session.commit()


def cancel_job(session: Session, job: Job) -> None:
    if job.status == JobStatus.queued.value:
        job.status = JobStatus.canceled.value
        job.completed_at = utcnow()
        session.commit()
