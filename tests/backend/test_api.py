from __future__ import annotations

from fastapi.testclient import TestClient

from evalforge_api.main import app

client = TestClient(app)


def test_live_health() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}


def test_lifecycle_metadata() -> None:
    response = client.get("/api/v1/lifecycle")

    assert response.status_code == 200
    assert "queued" in response.json()["evaluation_run_statuses"]
    assert "completed" in response.json()["evaluation_run_statuses"]


def test_metric_metadata_has_semantics() -> None:
    response = client.get("/api/v1/metrics")

    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics
    assert all(metric["semantics"] for metric in metrics)
