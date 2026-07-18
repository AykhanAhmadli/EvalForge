from __future__ import annotations

import logging
import os
import signal
import time
import uuid

from sqlalchemy.orm import Session

from evalforge.config import get_settings
from evalforge.db import get_session_factory
from evalforge.enums import EvaluationRunStatus, JobKind
from evalforge.evaluation_engine import EvaluationEngine, utcnow
from evalforge.models import EvaluationRun, Job
from evalforge.providers import TransientProviderError
from evalforge.queue import claim_next_job, complete_job, fail_job, renew_job_lease

logger = logging.getLogger("evalforge.worker")


class Worker:
    def __init__(self, worker_id: str, poll_interval_seconds: float = 2.0) -> None:
        self.worker_id = worker_id
        self.poll_interval_seconds = poll_interval_seconds
        self._shutdown_requested = False
        self.engine = EvaluationEngine(provider_seed=get_settings().fake_provider_seed)

    def request_shutdown(self, *_: object) -> None:
        self._shutdown_requested = True

    def run_forever(self) -> None:
        logger.info("worker started", extra={"worker_id": self.worker_id})
        while not self._shutdown_requested:
            processed = self.run_once()
            if not processed:
                time.sleep(self.poll_interval_seconds)
        logger.info("worker stopped", extra={"worker_id": self.worker_id})

    def run_once(self) -> bool:
        session_factory = get_session_factory()
        with session_factory() as session:
            job = claim_next_job(session, worker_id=self.worker_id)
            if job is None:
                return False
            self._process_claimed_job(session, job)
            return True

    def _process_claimed_job(self, session: Session, job: Job) -> None:
        try:
            logger.info("claimed job", extra={"job_id": str(job.id), "kind": job.kind})
            if job.kind == JobKind.evaluation_run.value:
                self._process_evaluation_run(session, job)
            else:
                raise ValueError(f"unsupported job kind: {job.kind}")
            complete_job(session, job)
        except TransientProviderError:
            run = self._run_for_job(session, job)
            if run is not None:
                if job.attempts < job.max_attempts:
                    run.status = EvaluationRunStatus.queued.value
                    run.failure_reason = "transient provider failure; retry scheduled"
                else:
                    run.status = EvaluationRunStatus.failed.value
                    run.failure_reason = "transient provider failure exhausted retries"
                    run.completed_at = utcnow()
                session.commit()
            fail_job(
                session,
                job,
                "transient provider failure",
                transient=True,
                error_type="transient_provider_error",
            )
        except Exception as exc:
            logger.error(
                "job failed",
                extra={"job_id": str(job.id), "error_type": type(exc).__name__},
            )
            run = self._run_for_job(session, job)
            if run is not None:
                run.status = EvaluationRunStatus.failed.value
                run.failure_reason = "evaluation job failed; inspect the stored error type"
                run.completed_at = utcnow()
                session.commit()
            fail_job(session, job, type(exc).__name__, error_type=type(exc).__name__)

    def _process_evaluation_run(self, session: Session, job: Job) -> None:
        run_id = job.payload.get("run_id")
        if not run_id:
            raise ValueError("evaluation.run job payload requires run_id")
        run = session.get(EvaluationRun, uuid.UUID(str(run_id)))
        if run is None:
            raise ValueError(f"evaluation run not found: {run_id}")
        self.engine.execute(
            session,
            run,
            job_attempt=job.attempts,
            lease_heartbeat=lambda: renew_job_lease(session, job),
        )
        logger.info(
            "evaluation run finished",
            extra={"run_id": str(run.id), "job_id": str(job.id), "status": run.status},
        )

    @staticmethod
    def _run_for_job(session: Session, job: Job) -> EvaluationRun | None:
        run_id = job.payload.get("run_id")
        if not run_id:
            return None
        return session.get(EvaluationRun, uuid.UUID(str(run_id)))


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    configure_logging()
    worker_id = os.getenv("WORKER_ID", f"worker-{uuid.uuid4()}")
    worker = Worker(worker_id=worker_id)
    signal.signal(signal.SIGTERM, worker.request_shutdown)
    signal.signal(signal.SIGINT, worker.request_shutdown)
    worker.run_forever()


if __name__ == "__main__":
    main()
