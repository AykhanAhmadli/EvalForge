from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from evalforge.enums import EvaluationRunStatus
from evalforge.models import EvaluationRun
from evalforge_worker.main import Worker


def test_worker_does_not_complete_a_run_without_execution() -> None:
    run_id = uuid4()
    run = EvaluationRun(id=run_id, status=EvaluationRunStatus.queued.value)
    session = Mock()
    session.get.return_value = run
    job = SimpleNamespace(id=uuid4(), payload={"run_id": str(run_id)})

    Worker(worker_id="test-worker")._process_evaluation_run(session, job)

    assert run.status == EvaluationRunStatus.failed.value
    assert run.failure_reason == "Evaluation execution is not enabled in this release."
    session.flush.assert_called_once()
    session.commit.assert_called_once()
