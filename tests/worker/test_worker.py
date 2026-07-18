from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from evalforge.enums import EvaluationRunStatus, JobStatus
from evalforge.models import EvaluationRun
from evalforge.providers import TransientProviderError
from evalforge.queue import fail_job
from evalforge_worker.main import Worker


def test_transient_failure_requeues_job_and_run() -> None:
    run_id = uuid4()
    run = EvaluationRun(id=run_id, status=EvaluationRunStatus.running.value)
    job = SimpleNamespace(
        id=uuid4(),
        kind="evaluation.run",
        attempts=1,
        max_attempts=3,
        status=JobStatus.running.value,
        payload={"run_id": str(run_id)},
    )
    session = Mock()
    session.get.return_value = run
    worker = Worker(worker_id="test-worker")
    worker.engine.execute = Mock(side_effect=TransientProviderError("temporary"))

    worker._process_claimed_job(session, job)

    assert run.status == EvaluationRunStatus.queued.value
    session.commit.assert_called()


def test_missing_job_payload_fails_without_processing() -> None:
    session = Mock()
    job = SimpleNamespace(id=uuid4(), payload={})
    worker = Worker(worker_id="test-worker")

    with pytest.raises(ValueError, match="requires run_id"):
        worker._process_evaluation_run(session, job)


def test_permanent_job_failures_do_not_requeue() -> None:
    session = Mock()
    job = SimpleNamespace(
        status=JobStatus.running.value,
        attempts=1,
        max_attempts=3,
        locked_by="worker",
        locked_at=None,
        lease_expires_at=None,
        last_error=None,
        last_error_type=None,
        failed_at=None,
    )
    fail_job(session, job, "bad input", error_type="ValueError")
    assert job.status == JobStatus.failed.value
