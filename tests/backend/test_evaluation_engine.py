from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from evalforge.db import database_ready, get_session_factory
from evalforge.enums import JobKind
from evalforge.models import Job
from evalforge.queue import claim_next_job
from evalforge_api.main import app
from evalforge_worker.main import Worker

pytestmark = pytest.mark.skipif(not database_ready(), reason="PostgreSQL is not running")
client = TestClient(app)


@pytest.fixture
def run_fixture() -> dict[str, str]:
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": "Engine Test Workspace", "slug": f"engine-{uuid4().hex[:12]}"},
    ).json()
    workspace_id = workspace["id"]
    dataset = client.post(
        f"/api/v1/workspaces/{workspace_id}/datasets", json={"name": "Engine Dataset"}
    ).json()
    version = client.post(
        f"/api/v1/datasets/{dataset['id']}/versions",
        json={
            "test_cases": [
                {"input": {"question": "hello"}, "expected_output": "hello"},
                {"input": {"question": "world"}, "expected_output": "world"},
            ]
        },
    ).json()
    prompt = client.post(
        f"/api/v1/workspaces/{workspace_id}/prompt-templates",
        json={"name": "Engine Prompt", "template": "{{ question }}"},
    ).json()
    model = client.post(
        f"/api/v1/workspaces/{workspace_id}/model-configurations",
        json={"name": "Engine Fake", "provider": "fake", "model_name": "evalforge-fake-v1"},
    ).json()
    yield {
        "workspace_id": workspace_id,
        "dataset_version_id": version["id"],
        "prompt_version_id": prompt["versions"][0]["id"],
        "model_configuration_id": model["id"],
    }
    response = client.delete(f"/api/v1/workspaces/{workspace_id}")
    assert response.status_code == 204, response.text


def _create_run(fixture: dict[str, str], metrics: list[str] | None = None) -> str:
    response = client.post(
        f"/api/v1/workspaces/{fixture['workspace_id']}/evaluation-runs",
        json={
            "dataset_version_id": fixture["dataset_version_id"],
            "prompt_version_id": fixture["prompt_version_id"],
            "model_configuration_id": fixture["model_configuration_id"],
            "metrics": metrics or ["exact_match"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_worker_persists_incremental_results_and_aggregates(run_fixture: dict[str, str]) -> None:
    run_id = _create_run(run_fixture, ["exact_match", "input_tokens"])
    assert Worker(worker_id=f"test-{uuid4()}").run_once() is True

    response = client.get(f"/api/v1/evaluation-runs/{run_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["completed_cases"] == 2
    assert any(item["scope_type"] == "tag" for item in payload["aggregates"]) is True
    results = client.get(f"/api/v1/evaluation-runs/{run_id}/results").json()
    assert len(results) == 2
    assert all(result["status"] == "completed" for result in results)
    assert all(result["token_usage"]["prompt_tokens"] >= 1 for result in results)


def test_two_workers_cannot_claim_the_same_job() -> None:
    factory = get_session_factory()
    job = Job(kind=JobKind.evaluation_run.value, payload={"run_id": str(uuid4())})
    with factory() as session:
        session.add(job)
        session.commit()
        job_id = job.id
    with factory() as first, factory() as second:
        assert claim_next_job(first, worker_id="one") is not None
        assert claim_next_job(second, worker_id="two") is None
    with factory() as session:
        session.delete(session.get(Job, job_id))
        session.commit()


def test_expired_worker_lease_can_be_reclaimed() -> None:
    factory = get_session_factory()
    job = Job(kind=JobKind.evaluation_run.value, payload={"run_id": str(uuid4())})
    with factory() as session:
        session.add(job)
        session.commit()
        job_id = job.id
        assert claim_next_job(session, worker_id="crashed", lease_seconds=300) is not None
        job.lease_expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
        session.commit()
    with factory() as session:
        reclaimed = claim_next_job(session, worker_id="replacement")
        assert reclaimed is not None
        assert reclaimed.id == job_id
        session.delete(reclaimed)
        session.commit()


def test_queued_run_can_be_cancelled_before_worker_claims(run_fixture: dict[str, str]) -> None:
    run_id = _create_run(run_fixture)
    response = client.post(f"/api/v1/evaluation-runs/{run_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert Worker(worker_id=f"test-{uuid4()}").run_once() is False


def test_running_run_honors_cancellation_request(run_fixture: dict[str, str]) -> None:
    run_id = _create_run(run_fixture)
    factory = get_session_factory()
    with factory() as session:
        job = session.scalar(select(Job).where(Job.payload["run_id"].as_string() == run_id))
        assert job is not None
        claimed = claim_next_job(session, worker_id="cancelling")
        assert claimed is not None
        claimed_id = claimed.id
    response = client.post(f"/api/v1/evaluation-runs/{run_id}/cancel")
    assert response.status_code == 200
    with factory() as session:
        claimed = session.get(Job, claimed_id)
        assert claimed is not None
        Worker(worker_id="cancelling")._process_claimed_job(session, claimed)
    assert client.get(f"/api/v1/evaluation-runs/{run_id}").json()["status"] == "cancelled"


def test_transient_provider_failure_retries_and_then_completes(
    run_fixture: dict[str, str],
) -> None:
    model_response = client.patch(
        f"/api/v1/model-configurations/{run_fixture['model_configuration_id']}",
        json={"parameters": {"transient_failures": 1}},
    )
    assert model_response.status_code == 200, model_response.text
    run_id = _create_run(run_fixture)
    worker = Worker(worker_id=f"test-{uuid4()}")
    assert worker.run_once() is True
    with get_session_factory()() as session:
        job = session.scalar(select(Job).where(Job.payload["run_id"].as_string() == run_id))
        assert job is not None
        job.run_after = datetime.now(tz=UTC) - timedelta(seconds=1)
        session.commit()
    assert worker.run_once() is True
    payload = client.get(f"/api/v1/evaluation-runs/{run_id}").json()
    assert payload["status"] == "completed"


def test_permanent_provider_failure_produces_partial_run(run_fixture: dict[str, str]) -> None:
    model_response = client.patch(
        f"/api/v1/model-configurations/{run_fixture['model_configuration_id']}",
        json={"parameters": {"permanent_failure_substrings": ["world"]}},
    )
    assert model_response.status_code == 200, model_response.text
    run_id = _create_run(run_fixture)
    assert Worker(worker_id=f"test-{uuid4()}").run_once() is True
    payload = client.get(f"/api/v1/evaluation-runs/{run_id}").json()
    assert payload["status"] == "partially_failed"
    assert payload["completed_cases"] == 1
    assert payload["failed_cases"] == 1


def test_deterministic_fake_provider_reproduces_results(run_fixture: dict[str, str]) -> None:
    first_id = _create_run(run_fixture, ["exact_match", "semantic_similarity"])
    second_id = _create_run(run_fixture, ["exact_match", "semantic_similarity"])
    worker = Worker(worker_id=f"test-{uuid4()}")
    assert worker.run_once() is True
    assert worker.run_once() is True
    first = client.get(f"/api/v1/evaluation-runs/{first_id}").json()
    second = client.get(f"/api/v1/evaluation-runs/{second_id}").json()
    first_results = client.get(f"/api/v1/evaluation-runs/{first_id}/results").json()
    second_results = client.get(f"/api/v1/evaluation-runs/{second_id}/results").json()
    assert [(row["output"], row["token_usage"]) for row in first_results] == [
        (row["output"], row["token_usage"]) for row in second_results
    ]
    assert [
        (row["scope_type"], row["metric_name"], row["value"]) for row in first["aggregates"]
    ] == [(row["scope_type"], row["metric_name"], row["value"]) for row in second["aggregates"]]
