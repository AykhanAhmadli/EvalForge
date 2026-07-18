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
from evalforge.models import EvaluationRun, Job
from evalforge.queue import claim_next_job, complete_job, fail_job

logger = logging.getLogger("evalforge.worker")


class Worker:
    def __init__(self, worker_id: str, poll_interval_seconds: float = 2.0) -> None:
        self.worker_id = worker_id
        self.poll_interval_seconds = poll_interval_seconds
        self._shutdown_requested = False

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
                raise ValueError(f"Unsupported job kind: {job.kind}")
            complete_job(session, job)
        except Exception as exc:
            logger.exception("job failed", extra={"job_id": str(job.id)})
            fail_job(session, job, str(exc))

    def _process_evaluation_run(self, session: Session, job: Job) -> None:
        run_id = job.payload.get("run_id")
        if not run_id:
            raise ValueError("evaluation.run job payload requires run_id")

        run = session.get(EvaluationRun, uuid.UUID(str(run_id)))
        if run is None:
            raise ValueError(f"Evaluation run not found: {run_id}")

        # Do not mark an empty run as successful. The execution pipeline will
        # replace this branch once dataset rendering and provider calls exist.
        run.status = EvaluationRunStatus.provisioning.value
        session.flush()
        run.status = EvaluationRunStatus.failed.value
        run.failure_reason = "Evaluation execution is not enabled in this release."
        session.commit()
        logger.info(
            "evaluation execution unavailable",
            extra={"run_id": str(run.id), "job_id": str(job.id)},
        )


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
